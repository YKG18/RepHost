# RepoHost - Architecture & Codebase Overview

This document provides a comprehensive overview of how **RepoHost** works, mapping every file in the repository to its responsibilities, internal mechanics, and component interactions.

---

## 1. High-Level Architecture & Workflow

RepoHost automates the process of cloning, analyzing, setting up, executing, and health-checking public web application repositories.

```text
       [ CLI / User Input ] (cli/main.py)
                │
                ▼
      1. Clone Repository (GitPython)
                │
                ▼
      2. Detect Project Type (app/detectors/)
         (Inspects manifest files, lockfiles, scripts)
                │
                ▼
      3. Install Dependencies (app/runners/)
         (npm/yarn/pnpm/bun install or venv pip install)
                │
                ▼
      4. Spawn & Manage Process (app/process/)
         (Starts process, monitors process tree for listening sockets via psutil)
                │
                ▼
      5. Perform Health Checks (app/health/)
         (Sends HTTP requests to detected port until HTTP status < 500)
```

---

## 2. Directory & File Structure

```text
./
│
├── cli/
│   └── main.py              # CLI Entry point & orchestrator
│
├── app/
│   ├── core/
│   │   ├── config.py        # Global constants and workspace directory configurations
│   │   └── models.py        # Pydantic models & Enums for structured data representation
│   │
│   ├── detectors/
│   │   ├── __init__.py      # Master detector router / entry point (`detect_project`)
│   │   ├── base.py          # Abstract base class (`Detector`) for project detectors
│   │   ├── static.py        # Static HTML/Web application detector (`StaticDetector`)
│   │   ├── node.py          # Node.js / JS framework detector (`NodeDetector`)
│   │   └── python.py        # Python framework detector (`PythonDetector`)
│   │
│   ├── runners/
│   │   └── runner.py        # Dependency installation & virtual environment manager (`Runner`)
│   │
│   ├── process/
│   │   └── manager.py       # Child process manager & socket port detector (`ProcessManager`)
│   │
│   └── health/
│       └── checks.py        # HTTP health checking utility (`verify_http_port`)
│
├── tests/
│   └── test_detectors.py    # Unit tests for project detectors
│
├── README.md                # Project documentation & execution instructions
├── AGENTS.md                # Detailed project requirements & design rules
├── requirements.txt         # Core Python dependencies
└── working.md               # Codebase working & architectural documentation (this file)
```

---

## 3. Detailed Component Breakdown

### A. Core Module ([`app/core/`](app/core/))

#### [`app/core/config.py`](app/core/config.py)
* **Responsibility**: Defines central configuration paths and operational thresholds.
* **Key Details**:
  * `BASE_DIR`: Base path of the repository root.
  * `WORKSPACES_DIR`: Resolves to `workspaces/` (created automatically if missing), where isolated temporary git clones are stored.
  * `DEFAULT_TIMEOUT`, `HEALTH_CHECK_INTERVAL`, `MAX_HEALTH_RETRIES`: Configuration defaults for execution time limits and polling retries.

#### [`app/core/models.py`](app/core/models.py)
* **Responsibility**: Provides strongly-typed data structures via Pydantic and Enums to pass metadata cleanly across detectors, runners, and process managers.
* **Key Data Models**:
  * `ProjectType (Enum)`: Standard project classifications (`STATIC`, `NODE`, `PYTHON`, `DOCKER`, `UNKNOWN`).
  * `DetectorResult (Pydantic BaseModel)`: Result object returned by detectors containing:
    * `project_type`: Enum indicating category.
    * `framework`: Detected framework string (e.g., `"Next.js"`, `"Vite"`, `"FastAPI"`, `"Flask"`, `"HTML"`).
    * `package_manager`: Identified tool (e.g., `"npm"`, `"yarn"`, `"pnpm"`, `"bun"`, `"pip"`).
    * `install_command`: List of command arguments to install dependencies (e.g., `["npm", "install"]`).
    * `run_command`: List of command arguments to launch the app (e.g., `["npm", "run", "dev"]`).
    * `expected_ports`, `entrypoint`: Additional metadata.
    * `confidence`: Float scoring (0.0 to 1.0) indicating detection certainty.
  * `RunConfig (Pydantic BaseModel)`: Execution context containing `repository_url`, `workspace_path`, `detector_result`, and `env_vars`.

---

### B. Detector Module ([`app/detectors/`](app/detectors/))

#### [`app/detectors/base.py`](app/detectors/base.py)
* **Responsibility**: Defines the abstract base class `Detector`.
* **Mechanism**: Requires all concrete detectors to implement the method `detect(self, path: Path) -> Optional[DetectorResult]`.

#### [`app/detectors/__init__.py`](app/detectors/__init__.py)
* **Responsibility**: Exposes `detect_project(path: Path) -> Optional[DetectorResult]`.
* **Mechanism**: Runs the target workspace path through all registered detectors (`NodeDetector`, `PythonDetector`, `StaticDetector`) and selects the result with the highest `confidence` score.

#### [`app/detectors/static.py`](app/detectors/static.py)
* **Responsibility**: Detects plain HTML/CSS/JS static websites.
* **Mechanism**: Checks for the existence of `index.html`. Returns `DetectorResult` configured to run `python -m http.server 0` with a confidence score of `0.5`.

#### [`app/detectors/node.py`](app/detectors/node.py)
* **Responsibility**: Detects Node.js applications and JS frameworks.
* **Mechanism**:
  1. Inspects `package.json`.
  2. Determines package manager by looking for lockfiles (`yarn.lock` -> `yarn`, `pnpm-lock.yaml` -> `pnpm`, `bun.lock`/`bun.lockb` -> `bun`, default -> `npm`).
  3. Inspects `dependencies` and `devDependencies` to infer framework (`next` -> `"Next.js"`, `vite` -> `"Vite"`, `react-scripts` -> `"React"`).
  4. Inspects `scripts` object for startup scripts (prefers `dev`, falls back to `start`). If no script exists, checks for `index.js`.
  5. Returns structured `DetectorResult` with confidence `0.9` (or `0.7` for fallback `node index.js`).

#### [`app/detectors/python.py`](app/detectors/python.py)
* **Responsibility**: Detects Python web applications.
* **Mechanism**:
  1. Checks for presence of `requirements.txt`, `pyproject.toml`, `main.py`, or `app.py`.
  2. Reads `requirements.txt` content to identify web framework dependencies:
     * `fastapi` / `uvicorn` -> `"FastAPI"`, sets run command to `python -m uvicorn main:app --host 0.0.0.0 --port 0`.
     * `flask` -> `"Flask"`, sets run command to `python -m flask run`.
     * `streamlit` -> `"Streamlit"`, sets run command to `streamlit run app.py`.
  3. Falls back to executing `python main.py` or `python app.py` if no framework match occurs.
  4. Returns `DetectorResult` with confidence `0.8`.

---

### C. Dependency Runner ([`app/runners/`](app/runners/))

#### [`app/runners/runner.py`](app/runners/runner.py)
* **Responsibility**: Installs dependencies required by the project in an isolated workspace.
* **Mechanism**:
  * For **Python projects**: Automatically creates an isolated virtual environment (`.venv/`) inside the workspace root using `subprocess.run(["python", "-m", "venv", ".venv"])`. It rewrites the binary paths for `pip` and executable runners (e.g. `uvicorn`, `flask`, `python`) to point directly inside `.venv/Scripts/` (Windows) or `.venv/bin/` (Linux/macOS), ensuring user global environments are not polluted.
  * Runs the designated `install_command` inside the workspace using `subprocess.run(check=True)`.

---

### D. Process Manager ([`app/process/`](app/process/))

#### [`app/process/manager.py`](app/process/manager.py)
* **Responsibility**: Launches, tracks, inspects, and cleans up the application process and its child processes.
* **Mechanism**:
  * `start()`: Spawns the application using `subprocess.Popen` in non-blocking mode with stdout/stderr piped.
  * `get_listening_ports(max_wait=15)`: Uses `psutil` to inspect the process tree (parent PID + all recursive child processes) and polls socket connections (`kind='inet'`) for any connection in state `LISTEN`. Returns the list of detected open ports.
  * `stop()`: Cleanly shuts down the application by iterating over the `psutil` child process hierarchy, issuing `terminate()` signals, and sending `kill()` to any process remaining after a 3-second grace period.

---

### E. Health Check ([`app/health/`](app/health/))

#### [`app/health/checks.py`](app/health/checks.py)
* **Responsibility**: Validates that the application running on a detected port is actively serving HTTP requests.
* **Mechanism**: Uses `httpx.get` with `follow_redirects=True` in a loop (up to `max_retries=15` with `interval=2` seconds). Any response with HTTP status code `200 <= status < 500` is considered a passed health check.

---

### F. CLI Entry Point ([`cli/main.py`](cli/main.py))

#### [`cli/main.py`](cli/main.py)
* **Responsibility**: Command-line interface built with Typer (`repohost <github_url>`). Orchestrates the complete application lifecycle.
* **Lifecycle Flow**:
  1. Creates a unique temporary directory inside `workspaces/`.
  2. Clones the remote repository into the directory using `git.Repo.clone_from`.
  3. Calls `detect_project(workspace)` to determine project type and runtime configuration.
  4. Calls `Runner.install_dependencies(config)` to set up runtime environment.
  5. Initializes and starts `ProcessManager(config)`.
  6. Calls `manager.get_listening_ports()` to detect active listening ports.
  7. Calls `verify_http_port(target_port)` to confirm HTTP responsiveness.
  8. Displays local URL (`http://localhost:<port>`) and keeps process alive until user presses `Ctrl+C`.
  9. Executes a `finally` block to terminate child processes and recursively delete the temporary workspace directory (handling read-only file locks on Windows via `remove_readonly`).

---

### G. Test Suite ([`tests/`](tests/))

#### [`tests/test_detectors.py`](tests/test_detectors.py)
* **Responsibility**: Automated unit tests using `pytest` and temporary directories (`tmp_path`).
* **Tests**:
  * `test_static_detection`: Verifies detection of HTML projects.
  * `test_node_detection`: Verifies detection of `package.json` with Vite dependency.
  * `test_python_detection`: Verifies detection of `requirements.txt` with FastAPI and `main.py`.

---

## 4. End-to-End Execution Sequence

```text
[ User runs: python cli/main.py <URL> ]
                   │
                   ▼
       cli/main.py: main()
                   │
       ┌───────────┴────────────────────────────┐
       │ 1. tempfile.mkdtemp() -> workspace     │
       │ 2. git.Repo.clone_from()               │
       │ 3. app.detectors.detect_project()      │
       │    ├── NodeDetector.detect()           │
       │    ├── PythonDetector.detect()         │
       │    └── StaticDetector.detect()         │
       │ 4. app.runners.Runner                  │
       │    └── install_dependencies()          │
       │        ├── (Python: venv creation)     │
       │        └── subprocess.run(install_cmd) │
       │ 5. app.process.ProcessManager          │
       │    ├── start() -> subprocess.Popen()   │
       │    └── get_listening_ports()           │
       │        └── psutil connection inspection│
       │ 6. app.health.verify_http_port()       │
       │    └── httpx GET retry loop            │
       │ 7. Wait on Ctrl+C                      │
       │ 8. Cleanup: process.stop() & rmtree()  │
       └────────────────────────────────────────┘
```