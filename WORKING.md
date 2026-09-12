# RepoHost — How It Works

RepoHost takes a public GitHub repo URL, figures out (deterministically, no LLM)
what kind of project it is, installs its dependencies, starts it, finds the
port it's actually listening on, health-checks it, and reports a local URL.
This doc walks through every file and then shows how `cli/main.py` wires them
together into one end-to-end run.

## File-by-file

### `cli/main.py` — the entrypoint / orchestrator
This is the only file that calls everything else, in order. It's a Typer CLI
with one command, `main(repo_url)`, that:
1. Fixes stdout buffering (`sys.stdout.reconfigure(line_buffering=True)`) so
   progress prints immediately instead of appearing to hang, especially under
   Windows/Git Bash pseudo-terminals.
2. Creates a temp directory under `workspaces/` and `git.Repo.clone_from()`s
   the repo into it with `--depth=1` (shallow clone, since only the current
   state of the code is needed).
3. Calls `detect_project()` to figure out what the repo is. If nothing is
   detected, it prints a detailed explanation of every location it checked
   (via `describe_scan()`) instead of a bare "failed" message.
4. Wraps the detection result plus the repo URL/workspace path into a
   `RunConfig` (the shared object passed to every later stage).
5. Calls `Runner.install_dependencies(config)` to install/build.
6. Starts the app via `ProcessManager(config).start()`, and spins up a
   background thread (`_tail_process_output`) that continuously drains the
   child process's stdout into a rolling `deque` (`log_buffer`), so logs are
   available for printing even if the process crashes or the health check
   fails.
7. Calls `manager.get_listening_ports()` to find the real port the app bound
   to (never assumed).
8. Calls `verify_http_port()` to confirm the app actually answers HTTP, not
   just that the process exists.
9. On success, prints the local URL and blocks (`while True: sleep(1)`),
   polling `manager.process.poll()` so it notices if the app crashes later.
   `Ctrl+C` breaks the loop.
10. In a `finally` block, always stops the process (`manager.stop()`) and
    deletes the temp workspace (`shutil.rmtree(..., onerror=remove_readonly)`,
    which clears Windows' read-only bit on `.git` files that would otherwise
    block deletion) — so cleanup runs on success, failure, or Ctrl+C alike.

Note: the README/CLI output mention a "PUBLIC URL" (tunnel) step, but the code
literally prints `"(Not implemented in Phase 1)"` there — tunneling is planned
architecture (see `AGENTS.md`) but not yet built. This build only implements
through local hosting + health checks.

### `app/core/models.py` — the shared data contract
Defines the two Pydantic models that flow through the whole pipeline:
- `ProjectType` (enum): `static`, `node`, `python`, `docker`, `unknown`.
- `DetectorResult`: everything a detector figured out — project type,
  framework name, package manager, `install_command`/`run_command` as arg
  lists (never raw shell strings, to avoid injection), `working_dir` (for
  monorepo subfolders), `env` vars the detector thinks are needed,
  `matched_path`/`secondary_services` (informational, for reporting
  monorepo splits), and a `confidence` float used to rank competing matches.
- `RunConfig`: the object actually passed around at runtime — repo URL,
  cloned workspace path, the chosen `DetectorResult`, and merged `env_vars`.

### `app/core/config.py` — static settings
Computes `BASE_DIR`/`WORKSPACES_DIR` (creating `workspaces/` if missing) and
defines constants (`DEFAULT_TIMEOUT`, `HEALTH_CHECK_INTERVAL`,
`MAX_HEALTH_RETRIES`). Currently only `WORKSPACES_DIR` is actually imported
elsewhere; the other constants are declared for future use.

### `app/detectors/` — figuring out what the repo is
This is the "brain" of the project. `base.py` defines the `Detector`
abstract base class with one method, `detect(path) -> Optional[DetectorResult]`.
Each concrete detector implements it independently — no giant if/else chain.

- **`static.py` (`StaticDetector`)** — looks for `index.html` (and common
  case variants like `Index.html`) in the root or common static-output dirs
  (`public`, `dist`, `build`, `docs`, `site`, `www`, `out`, `static`, `src`),
  root scoring higher confidence. If no canonical index file exists anywhere,
  it falls back to walking the tree (2 levels deep) for whichever directory
  has the most `.html` files, at low confidence, rather than giving up.
  Run command: `python -m http.server 0 --directory <dir>` (port `0` = pick
  a free port).

- **`node.py` (`NodeDetector`)** — requires `package.json`. Picks the package
  manager from lockfiles (`yarn.lock`→yarn, `pnpm-lock.yaml`→pnpm,
  `bun.lock(b)`→bun, else npm). Infers the framework name by scanning
  `dependencies`/`devDependencies` for known packages (next, nuxt,
  @sveltejs/kit, svelte, vue, @angular/core, astro, vite, react-scripts,
  express, @nestjs/core). Picks a run script by priority
  (`dev` > `develop` > `start` > `serve` > `preview`) from `package.json`'s
  `scripts`, rather than always assuming `npm start`. If no usable script
  exists, falls back to the `main` field or a list of conventional entry
  filenames (`server.js`, `index.js`, etc.) run directly with `node`.

- **`python.py` (`PythonDetector`)** — requires one of
  `requirements.txt`/`pyproject.toml`/`manage.py`/`main.py`/`app.py`. Reads
  `requirements.txt` (trying utf-8 then utf-16) and `pyproject.toml` into one
  lowercase blob to check for framework names, then branches:
  - **Django**: if `manage.py` exists at root or one level down, runs
    `python manage.py runserver 0.0.0.0:0`.
  - **FastAPI**: searches all `.py` files (depth-limited to 4) for a
    module-level `x = FastAPI(...)` via regex, ranks candidates by
    preferred filename then shallowest path, and runs
    `uvicorn <module>:<var> --host 0.0.0.0 --port 0`. Falls back to guessing
    `main:app` or `app:app` if no literal match is found but `main.py`/`app.py`
    exists.
  - **Flask**: similar file scan, but layered — a literal `x = Flask(...)`
    beats a bare `app =`/`application =` assignment (covers app-factory
    re-exports like `app = create_app()`), which beats a bare
    `def create_app()` factory function with no variable at all (Flask's own
    CLI auto-calls factories). Conventional filenames
    (`app.py`, `application.py`, `wsgi.py`, etc.) always win ties. Runs
    `python -m flask --app <ref> run --host 0.0.0.0 --port 0`.
  - **Streamlit**: finds `app.py`/`main.py` or any `.py` file mentioning
    "streamlit", runs `streamlit run <file> --server.port 0 --server.headless true`.
  - **Generic fallback**: if none of the above match but `main.py` or
    `app.py` exists, just runs `python main.py` / `python app.py` directly.

- **`docker.py` (`DockerDetector`)** — lowest-priority detector (confidence
  0.5–0.55), intentionally, so a plain Node/Python project with an incidental
  Dockerfile still runs the fast native way instead of going through Docker.
  Detects `docker-compose.yml`/`compose.yml` (runs `docker compose up`) or a
  bare `Dockerfile` (parses an `EXPOSE <port>` line via regex, defaulting to
  8080, then runs `docker build` + `docker run --name repohost-app-run -p <port>`).

- **`__init__.py` (the aggregator)** — this is where "extensible architecture"
  actually resolves to one answer:
  - `_best_of(path)` runs *every* detector against one directory and returns
    whichever result has the highest `confidence`.
  - `detect_project(path)` first calls `_best_of(root)`. It also always
    tries `_detect_split_layout(path)`, which checks known monorepo pairs
    (`backend/`+`frontend/`, `server/`+`client/`, `api/`+`web/`, `api/`+`ui/`)
    one level deep, running `_best_of()` on each side. If a split layout
    exists and its confidence is ≥ the root match's (e.g. a root
    `package.json` that's just shared lint config), the split result wins —
    it runs the backend and records the frontend as a `secondary_services`
    entry rather than silently ignoring it or crashing.
  - If neither the root nor a split layout matched, `_detect_in_subdirs()`
    does a generic one-level-deep scan of every subdirectory (skipping
    `.git`, `node_modules`, `.venv`, `dist`, etc.) and returns the
    highest-confidence match found there, tagging `matched_path`/
    `working_dir` so later stages know to `cd` into it.
  - `describe_scan(path)` produces a human-readable list of exactly what was
    checked (root name, any split-layout candidates present, subdirectories
    scanned) — used only when detection fails completely, so the CLI's
    failure message is specific rather than "could not detect project."

### `app/runners/runner.py` — installing dependencies
`Runner.install_dependencies(config)` branches on `project_type`:
- **Docker** → delegates to `_docker_build()`, which runs the detector's
  `install_command` (a `docker build`/`docker compose build`) directly.
- **Python** → creates an isolated `.venv` inside the (possibly monorepo
  subfolder) working directory via `python -m venv .venv` if one doesn't
  exist yet, then rewrites `pip` in `install_command` — and any of
  `python`/`flask`/`uvicorn`/`streamlit` in `run_command` — to point at the
  venv's own `bin/`(or `Scripts/` on Windows) copy, so the app never touches
  the user's global Python environment.
- **Node/others** → resolves the install binary's real path via
  `resolve_executable()` (needed because tools installed by npm/nvm on
  Windows are often `.cmd`/`.bat` shims that plain `Popen([...])` without
  `shell=True` won't find), then runs it.

`_run_install()` actually executes the command and distinguishes "the
install command doesn't exist at all" (`FileNotFoundError`, an *essential*
failure that's unrecoverable) from "it exists but exited non-zero"
(non-essential — logged, but not fatal). If a non-essential failure happens,
`_permissive_fallback()` retries once with a looser flag appropriate to the
tool (`npm install --no-optional --legacy-peer-deps`, `yarn
--ignore-optional`, `pnpm --no-optional`, `pip --no-deps`). If that also
fails non-essentially, the code deliberately still returns `True` and moves
on — the philosophy encoded in the comments is that the real test of success
is whether the app actually starts and answers HTTP later, not whether the
install step's exit code was zero.

The Windows-compatibility helpers in this file
(`_msys_to_windows_path`, `_split_path_env`, `_windows_which_fallback`,
`resolve_executable`) exist because Git Bash/MINGW64 can hand a native
Windows Python process a Unix-style `PATH` (colon-separated, `/c/...`
entries). `shutil.which()` alone would then silently find nothing even
though the binary is genuinely installed, so `resolve_executable()` falls
back to a manual PATH/PATHEXT search after normalizing each entry to a
Windows path.

### `app/process/manager.py` — running and watching the process
`ProcessManager` wraps the actual OS process:
- `start()` builds the environment (copies `os.environ`, sets
  `PYTHONUNBUFFERED=1` so the child doesn't block-buffer its own output,
  merges in the detector's/config's env vars), resolves the executable if
  needed, and launches it with `subprocess.Popen(..., stdout=PIPE,
  stderr=STDOUT, text=True)` from the correct working directory
  (`_run_dir()`, which respects `working_dir` for monorepo subfolders).
- `get_listening_ports()` — for non-Docker apps, uses `psutil` to walk the
  started process *and all its children* (important because e.g. `npm run
  dev` spawns a child that's the actual listener) and collects any socket in
  `LISTEN` state, polling every second up to `max_wait` seconds. It bails
  early if the process has already exited. For Docker, `_get_docker_ports()`
  instead shells out to `docker port repohost-app-run` and regex-parses the
  `container_port/tcp -> 0.0.0.0:hostport` lines to get the *host* port
  Docker actually mapped.
- `stop()` terminates the process tree cleanly: for Docker, `docker stop`s
  the named container first; for everything else, it walks
  `psutil.Process(pid).children(recursive=True)`, terminates each child then
  the parent, waits up to 3 seconds, and `kill()`s anything still alive.

### `app/health/checks.py` — confirming it's actually working
`verify_http_port(port)` polls `http://127.0.0.1:<port>/` with `httpx`,
retrying every `interval` seconds up to `max_retries` times. A response with
status `200 <= code < 500` counts as success — deliberately including things
like 404/401 — because many real apps (REST APIs, SPAs with client-side
routing) have nothing mounted at `/` at all; that's not the same as the
server being down. `probe_alternate_paths()` is a UX nicety used only when
the root path returned a non-2xx code: it checks a handful of common paths
(`/docs`, `/api`, `/health`, etc.) so the CLI can tell the user "try
`/docs`" instead of leaving them looking at a bare error body.

### `requirements.txt`
Pins the runtime dependencies actually imported by the code: `typer` (CLI
framework), `pydantic` (the models), `psutil` (process/port introspection),
`httpx` (health-check HTTP client), `GitPython` (cloning), `pytest` (tests).

### `tests/test_detectors.py` and `tests/test_runner.py`
Exercise the two riskiest parts of the system directly:
- `test_detectors.py` builds tiny synthetic repos in `tmp_path` (a bare
  `index.html`, a `package.json` with a `dev` script, a FastAPI/Flask/Django
  file, a monorepo `backend/`+`frontend/` split, a project only detectable
  one level deep, a totally undetectable repo) and asserts `detect_project()`
  picks the right `ProjectType`/`framework`/`run_command`/`working_dir` in
  each case — including the specific factory-function edge cases described
  in the Flask docstrings.
- `test_runner.py` unit-tests the Windows PATH-compatibility helpers in
  isolation (MSYS path conversion, PATH splitting, the manual PATHEXT
  fallback search, and `resolve_executable()` falling back correctly when
  `shutil.which()` is mocked to fail).

### `README.md` / `AGENTS.md`
`README.md` is the short, user-facing quickstart. `AGENTS.md` is the original
design brief this codebase was built against — it specifies the full,
eventual RepoHost (tunneling, a polished UI, Docker-first isolation,
ephemeral hosting with expiry, a richer CLI with `--duration`/`--port`/
`--no-tunnel`/`stop`/`logs`). The code in this zip implements **Phase 1**
only (clone → detect → install → start → find port → health-check → print
local URL); tunneling, the UI, and expiry/cleanup timers from later phases
aren't built yet.

## How it all comes together (the flow inside `cli/main.py`)

```
repo_url
   │
   ▼
git.Repo.clone_from()                     → shallow-clone into workspaces/<tmp>/
   │
   ▼
detect_project(workspace)                 → app/detectors/__init__.py
   │   picks best DetectorResult across root / split-layout / one-level-deep
   ▼
RunConfig(repo_url, workspace, detector_result, env_vars)
   │                                         → app/core/models.py
   ▼
Runner.install_dependencies(config)       → app/runners/runner.py
   │   (venv + pip, or npm/yarn/pnpm/bun install, or docker build)
   ▼
ProcessManager(config).start()            → app/process/manager.py
   │   (subprocess.Popen from the right working_dir, with merged env)
   ▼
manager.get_listening_ports()             → psutil scan of process + children
   │                                         (or `docker port` for Docker)
   ▼
verify_http_port(port)                    → app/health/checks.py
   │   (poll until real HTTP response, 200–499 counts as "alive")
   ▼
print local URL, block until Ctrl+C or crash
   │
   ▼
finally: manager.stop() + shutil.rmtree(workspace)   → always cleans up
```

Every stage hands a small, well-typed piece of data to the next
(`DetectorResult` → `RunConfig` → `ProcessManager`/`Runner`), and every
"success" the CLI prints corresponds to something it actually verified
(a real subprocess, a real open socket, a real HTTP response) rather than an
assumed or faked result — matching the "failure is better than fake success"
principle in `AGENTS.md`. The one piece of `AGENTS.md`'s scope not yet
implemented here is the public tunnel step (Cloudflare/ngrok/LocalTunnel);
the code path for it exists as a placeholder print statement only.
