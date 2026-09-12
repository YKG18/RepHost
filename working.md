# RepoHost - Architecture and Working

RepoHost is a CLI tool designed to take a public GitHub repository, detect its framework/language, containerize it dynamically using Docker, and serve it locally with zero configuration required from the user. It supports multi-tier applications (e.g., a React frontend and a Flask backend in the same repository).

This document explains the internal working of the project, what each file does, and provides a roadmap for bundling the application into a standalone executable (`.exe`).

## 1. How the Project Works

The execution flow of RepoHost follows a strict pipeline:
1. **Clone**: The repository is cloned into a temporary workspace.
2. **Detect**: The workspace is scanned (recursively) to identify sub-projects (e.g., Node.js, Python, Static).
3. **Configure**: Environment variables are detected, and the user is prompted to fill in missing values.
4. **Build**: A `Dockerfile` is dynamically generated in memory for each sub-project and built via the Docker CLI.
5. **Run & Map**: Containers are started with exposed ports mapped randomly to the host.
6. **Health Check**: The mapped ports are aggressively tested until the correct HTTP port is locked onto.
7. **Serve**: The application is kept alive and local URLs are presented.
8. **Cleanup**: Upon termination, containers are killed, and the temporary workspace is deleted.

---

## 2. File Directory Breakdown

### `cli/main.py`
**Purpose**: The main entrypoint and orchestrator of the CLI.
**How it works**:
- Uses `typer` to parse command-line arguments (the GitHub URL).
- Creates a temporary directory using `tempfile`.
- Uses `git.Repo.clone_from` to download the repository.
- Calls the detector module to find sub-projects.
- Prompts the user via CLI for any environment variables identified by the detectors.
- Orchestrates the `Runner` (to build images) and `ProcessManager` (to run containers).
- Ensures safe cleanup of Docker containers and temporary folders in a `finally` block when the user exits (Ctrl+C).

### `app/core/models.py` & `app/core/config.py`
**Purpose**: Define the data structures and global configuration.
**How it works**:
- Contains `enum`s for `ProjectType` (NODE, PYTHON, STATIC).
- Defines `DetectorResult` (holds framework, run commands, extracted env vars).
- Defines `RunConfig` (pairs a detector result with a specific workspace path).
- `config.py` defines constants like `WORKSPACES_DIR`.

### `app/detectors/`
**Purpose**: Heuristics to identify what a repository contains.
**How it works**:
- **`__init__.py`**: Recursively walks the cloned repository up to a depth of 2. It runs all available detectors on each directory to find independent services (enabling multi-tier support).
- **`base.py`**: The abstract base class that all detectors inherit from.
- **`node.py`**: Looks for `package.json`. Identifies `npm`, `yarn`, `pnpm`, or `bun`. Detects `Vite`, `Next.js`, or generic React. Crucially, it injects host binding flags (`--host 0.0.0.0` or `-H 0.0.0.0`) so the dev servers expose themselves to the Docker bridge.
- **`python.py`**: Looks for `requirements.txt`. Detects `Flask`, `FastAPI`, etc. Uses AST/regex to parse `.env` or `.flaskenv` files to find required environment variables (like `FLASK_APP`).
- **`static.py`**: Fallback detector that looks for `index.html` and serves it via Python's `http.server`.

### `app/sandbox/dockerfile_generator.py`
**Purpose**: Dynamically generates Dockerfiles without relying on static templates.
**How it works**:
- Based on the `ProjectType`, it generates a standard multi-line string representing a Dockerfile.
- For Python: Uses `python:3.11-slim`, installs GCC/make, runs `pip install`, and exposes `3000 5000 8000 8080`.
- For Node: Uses `node:18-alpine`, copies package manifests, uses the correct package manager to install dependencies, copies source, and exposes `3000 4000 5173 8080`.
- These Dockerfiles are generated in memory and never written directly to the user's disk.

### `app/runners/runner.py`
**Purpose**: Builds the Docker images.
**How it works**:
- Calls `dockerfile_generator.py` to get the Dockerfile string.
- Uses `subprocess.run` to call `docker build -t <image_name> -`.
- Pipes the Dockerfile string directly into Docker's `stdin` (`input=dockerfile_content`). This cleanly isolates the build process.

### `app/process/manager.py`
**Purpose**: Manages the runtime lifecycle of the containers.
**How it works**:
- Generates a unique container name (`repohost-run-<hash>`).
- Runs `docker run -d -P` (daemon mode, publish all exposed ports randomly).
- Mounts the sub-project directory into the container so local files are available.
- Injects `HOST=0.0.0.0` and any user-provided environment variables into the container.
- Uses `docker port` to extract the random host ports that Docker assigned to the exposed container ports.
- Provides a `.stop()` method to forcefully kill and remove the container during cleanup.

### `app/health/checks.py`
**Purpose**: Validates that the container is actually serving web traffic.
**How it works**:
- Because Docker exposes multiple ports randomly, `verify_http_ports` takes a list of all mapped host ports.
- It rapidly iterates (round-robin) through all possible ports using `httpx.get(url, timeout=1.0)`.
- The moment it receives an HTTP response (status 200-499), it locks onto that port and returns it to `main.py` as the true application port.

---

## 3. Roadmap to Bundle as an EXE

To distribute RepoHost as a standalone executable (`RepoHost.exe`) that users can run without installing Python, you can use **PyInstaller**.

### Prerequisites
1. The host machine running the executable **must have Docker Desktop (or Docker Engine) installed and running**. The EXE encapsulates the Python logic, but it relies on `subprocess` to call the `docker` CLI.
2. Install PyInstaller in your virtual environment:
   ```bash
   pip install pyinstaller
   ```

### Step 1: Handling Hidden Imports
Since RepoHost relies heavily on dynamic execution and specific third-party libraries, PyInstaller needs to know exactly what to bundle.
Libraries like `typer`, `httpx`, `gitpython` (and its underlying `git` binaries/dependencies) must be included.

### Step 2: Modifying Paths
Currently, RepoHost relies on `__file__` to resolve relative paths (e.g., if you add binaries or static templates later).
In a PyInstaller EXE, the application runs from a temporary extracted folder (accessed via `sys._MEIPASS`).
You will need to update path resolutions (like `WORKSPACES_DIR`) to handle the PyInstaller environment:
```python
import sys
import os

def get_base_path():
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS)
    return os.path.dirname(os.path.abspath(__file__))
```

### Step 3: Creating the Build Spec
Generate a `.spec` file to control the build process:
```bash
pyi-makespec --name RepoHost --onefile cli/main.py
```
You can edit `RepoHost.spec` to include additional non-Python files (if any are added later, like a `bin/` directory for Cloudflared).

### Step 4: Compiling the Executable
Run PyInstaller using the spec file:
```bash
pyinstaller RepoHost.spec --clean
```

### Files and Folders Included in the EXE
- **Included**: All Python source code (`cli/`, `app/core/`, `app/detectors/`, `app/runners/`, `app/process/`, `app/health/`).
- **Included**: All `pip` dependencies (Typer, httpx, GitPython, colorama, etc.).
- **Excluded**: The actual `docker` binary. The EXE will assume `docker` is available in the user's system `PATH`.
- **Excluded**: The cloned GitHub repositories. These will still be cloned dynamically at runtime to the user's `%TEMP%` folder.

### Step 5: Distribution
The final `dist/RepoHost.exe` will be a single file (~15-30MB depending on dependencies). A user simply drops it in their terminal and runs:
```cmd
RepoHost.exe https://github.com/user/repo
```
