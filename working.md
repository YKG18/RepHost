# RepoHost - Architecture and Working

RepoHost is a developer CLI tool designed to take a public GitHub repository, detect its framework and language, containerize it dynamically using Docker, and serve it locally and publicly with zero configuration required from the user. It supports fullstack applications, multi-tier architectures (e.g., a React frontend and a Flask backend in the same repository), and **first-class backend-only API services**.

---

## 1. How the Project Works

The execution flow of RepoHost follows a strict, deterministic pipeline:

```text
User pastes: https://github.com/user/project
                      ↓
1. Pre-flight Docker Check & Auto-Start
   RepoHost verifies the Docker daemon is responding. If Docker Desktop is stopped,
   RepoHost automatically launches Docker Desktop and polls until ready.
                      ↓
2. Clone
   The repository is cloned into an isolated temporary workspace.
                      ↓
3. Multi-Framework & Backend API Detection
   Scans the repository (root and 1-level deep subdirectories) to identify
   runnable services across all major languages and frameworks.
   If the service is a backend API, routes and interactive docs (Swagger/OpenAPI)
   are extracted.
                      ↓
4. In-Container Dependency Resolution & Build
   When dependencies or runtimes (Java, Ruby, PHP, .NET, Node, Python) are
   not available on the host machine, RepoHost dynamically generates an
   optimized Dockerfile containing all required SDKs, compilers, and libraries,
   building them safely inside container layers.
                      ↓
5. Run & Port Mapping
   Containers are started with exposed ports mapped randomly to host interfaces (-P).
                      ↓
6. API-Aware Health Check
   Mapped ports are tested. For backend APIs, candidate routes and documentation
   endpoints (/docs, /swagger-ui, /api) are tested to confirm server health even
   if root (/) returns 404.
                      ↓
7. Public Tunnel & Interactive Live Summary
   Exposes the application via Cloudflare Tunnel.
   Displays Local URL, Public URL, interactive API Docs URL, and discovered endpoints.
   Opens the browser directly to the application (or interactive API Docs).
                      ↓
8. Ephemeral Lifecycle & Cleanup
   Upon session duration expiry or Ctrl+C, containers are stopped,
   tunnels closed, and temporary workspaces cleanly purged.
```

---

## 2. Supported Frameworks & Runtime Pipelines

RepoHost provides out-of-the-box support for all major modern web frameworks:

| Framework / Language | Manifest / Markers | Package Manager | Container Base Image | Default Ports | API / Docs Support |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Django** (Python) | `manage.py`, `wsgi.py`, `django` in requirements | `pip` | `python:3.11-slim` + system DB libs | 8000 | Auto-migrates DB, detects routes & `/admin/` |
| **FastAPI** (Python) | `fastapi`, `uvicorn`, `main.py` | `pip` | `python:3.11-slim` | 8000 | `/docs`, `/redoc`, `/openapi.json`, route parsing |
| **Flask / FlaskAPI** | `app.py`, `Flask(`, `.flaskenv` | `pip` | `python:3.11-slim` | 5000, 8000 | `/swagger-ui`, `/apidocs`, `/docs`, route parsing |
| **Spring Boot** (Java) | `pom.xml`, `build.gradle`, `build.gradle.kts` | `maven` / `gradle` | `maven:3.9-eclipse-temurin-17` / `gradle:8.5-jdk17` | 8080 | `@RestController`, `@GetMapping`, `/swagger-ui/index.html` |
| **Ruby on Rails** | `Gemfile`, `config/routes.rb`, `bin/rails` | `bundle` | `ruby:3.2-slim` + build-essential | 3000 | Auto-prepares DB, parses `routes.rb`, `/api-docs` |
| **PHP / Laravel** | `composer.json`, `artisan`, `index.php` | `composer` | `php:8.2-cli` + PDO extensions | 8000 | Auto-generates key, parses `routes/api.php`, `/api/documentation` |
| **ASP.NET Core** (C#) | `*.csproj`, `*.sln`, `Program.cs` | `dotnet` | `mcr.microsoft.com/dotnet/sdk:8.0` | 5000, 8080 | `[HttpGet]`, minimal APIs `app.MapGet`, `/swagger/index.html` |
| **Node.js / Fullstack** | `package.json` (Vite, Next.js, Nuxt, Astro, Svelte) | `npm` / `pnpm` / `yarn` / `bun` | `node:18-slim` | 3000, 5173, 4200, 4321 | Injects host bindings (`--host 0.0.0.0`) |
| **Node.js / Backend** | Express, NestJS, Fastify, Koa, Hono | `npm` / `pnpm` / `yarn` | `node:18-slim` | 3000, 8000, 8080 | Route parsing, `@Get()`, `/api-docs`, `/docs` |
| **Go** | `go.mod`, `main.go` (Gin, Fiber, Echo, Chi) | `go` | `golang:1.21-alpine` + build-base | 8080, 8000 | Route inspection, `/swagger/index.html` |
| **Rust** | `Cargo.toml` (Actix, Axum, Rocket, Warp) | `cargo` | `rust:1.75-slim` + build-essential | 8080, 8000 | Route inspection, `/swagger-ui` |
| **Static Websites** | `index.html` | None | `python:3.11-slim` | 8000 | Serves static HTML/JS/CSS assets |
| **Docker Compose** | `docker-compose.yml`, `compose.yaml` | Docker | Multi-container native engine | Dynamic | Full multi-container service orchestration |

---

## 3. Key Architectural Features

### 3.1 Docker Desktop Auto-Detection & Auto-Start
- Located in `app/sandbox/docker_checker.py`.
- Before any cloning or building starts, RepoHost checks `docker info`.
- If the Docker daemon is not active, RepoHost detects the Docker Desktop installation path across standard system paths (e.g. `%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe` or `C:\Program Files\Docker\Docker\Docker Desktop.exe`) and launches it automatically.
- Polls the daemon until ready with progress feedback.

### 3.2 In-Container Dependency Resolution & AST-Based Dependency Inference
- Zero local dependencies required on the host: the host machine does not need Java, Ruby, PHP, .NET, Node, or Go installed.
- All builds, package downloads, and runtime executions occur inside containerized Docker environments.
- **AST-Based Dependency Inference**: When a repository lacks a package manifest (e.g. no `requirements.txt`, `Pipfile`, or `pyproject.toml`), RepoHost scans all `.py` files using Python's Abstract Syntax Tree (AST), identifies third-party imports, filters out local modules and the standard library, and maps import symbols to their PyPI package distributions (e.g. `mptt` → `django-mptt`, `PIL` / `ImageField` → `Pillow`, `shortuuid` → `shortuuid`, `rest_framework` → `djangorestframework`).
- Python packages with C-extensions (like MySQL, Postgres, SQLite drivers) automatically include required apt build headers.
- Django migrations (`migrate --noinput`) and Laravel key generations (`artisan key:generate`) run automatically during container startup.
- **Template Directory Protection**: Directories named `templates`, `views`, `static`, etc., containing server-side template tags (`{% extends %}`, `{% load %}`, `{{ }}`) are prevented from being mistakenly classified as standalone static sites, preventing unrendered template code from being served directly.
- **Django Tunnel & Static Asset Optimization**: Django containers automatically append `ALLOWED_HOSTS = ["*"]` and `CSRF_TRUSTED_ORIGINS` to allow Cloudflare tunnel URLs and form submissions without HTTP 400 DisallowedHost or CSRF errors, and launch with `--insecure` to ensure static assets (CSS/JS) are served seamlessly.

### 3.3 First-Class Backend-Only Repositories
- Located in `app/detectors/api_inspector.py` and `app/health/checks.py`.
- Repositories without frontend templates are marked as `(Backend API)`.
- Scans source code to discover defined routes (e.g. `GET /api/v1/users`, `POST /items`).
- Identifies Swagger UI, ReDoc, and OpenAPI documentation endpoints (`/docs`, `/swagger-ui/index.html`, `/swagger/`, etc.).
- Probes candidate endpoints during health check so APIs that return 404 on root `/` pass health checks immediately.
- Displays interactive documentation links in the live CLI summary for both local and public tunnel access.
- When opening the default browser (`--open`), RepoHost automatically opens the interactive API documentation page.

### 3.4 Relative and Portable Path Resolution
- Centralized in `app/core/config.py` via `get_base_path()` and `get_workspaces_dir()`.
- Supports both normal execution and PyInstaller's extracted `sys._MEIPASS` environment.
- In `app/tunnel/manager.py`, Cloudflared binary search uses `get_base_path() / "bin"` and falls back to writable paths when frozen, ensuring zero absolute hardcoded paths.

### 3.5 Multi-Tier Architecture & Connection Bridge
- **Framework-Aware Connection Discovery** (`app/detectors/connection_bridge.py`):
  When a repository contains both frontend and backend services, RepoHost automatically analyzes the frontend source code to discover *how* it references the backend:
  - **Hardcoded URLs**: Scans `.ts`, `.tsx`, `.js`, `.jsx`, `.vue`, `.svelte`, `.html`, `.json`, `.env*` files for patterns like `http://localhost:5000/api/v1/...` or `http://127.0.0.1:5000`
  - **Environment Variables**: Detects usage of `VITE_API_URL`, `REACT_APP_API_URL`, `NEXT_PUBLIC_API_URL`, `API_URL`, `BACKEND_URL`, etc. in source and `.env` files
  - **Proxy Configurations**: Reads `vite.config.ts` `server.proxy`, `package.json` `proxy` field, `next.config.js` `rewrites`, and Angular `proxyConfig`

- **Bridging Strategies** (applied in priority order):

  | Strategy | When Applied | Result |
  |---|---|---|
  | **Port Pinning** | Frontend hardcodes `localhost:<port>` and that port is available on host | Backend container is mapped directly to that exact host port (`-p 5000:5000`). Zero code changes needed. |
  | **Env-Var Injection** | Frontend reads API URL from environment variables | Injects discovered and standard env vars pointing to `http://localhost:<actual_backend_port>` |
  | **Source Rewriting** | Frontend hardcodes URLs and target port is occupied (or backend running on another port) | Regex `sed` replaces both `http://localhost:<old_port>` and `http://127.0.0.1:<old_port>` with the actual backend host port across all frontend source files at Docker build time |
  | **Generic Fallback** | No specific pattern detected | Standard env vars (`VITE_API_URL`, `REACT_APP_API_URL`, `NEXT_PUBLIC_API_URL`, etc.) sprayed as fallback |

- **Strict Backend-First Startup Ordering**:
  Backends build, start, and pass health checks *first*. Once the actual host listening port is verified, frontends are wired with the running backend's exact host port before the frontend Docker image is built.
- **Universal Permissive CORS**:
  - Injected via environment variables (`CORS_ORIGIN=*`, `CORS_ORIGINS=*`, `CORS_ALLOW_ALL_ORIGINS=True`, `ALLOWED_HOSTS=*`).
  - Container-level regex patching replaces hardcoded backend CORS origin restrictions (e.g. `origins: "http://localhost:5173"`) with wildcard `'*'`, allowing frontend apps to connect without CORS errors regardless of port or Cloudflare tunnel.
- **Automatic Auth Development Secrets**:
  Injects default development secret keys (`JWT_SECRET_KEY`, `SECRET_KEY`, `SESSION_SECRET`, `FLASK_SECRET_KEY`) into backend environments, preventing HTTP 500 crashes on authentication routes.
- **Automatic Database Migrations & Seeding**:
  - **Django**: Executes `python manage.py migrate --noinput` and automatically seeds an admin superuser (`admin` / `admin123`), displayed in the live CLI banner.
  - **Flask**: Runs `flask db upgrade || true` and `python seed.py || true` if migrations or seed files are present.
  - **Node**: Executes `find /app -name "schema.prisma" -exec npx prisma generate ...` and `npx prisma db push || true` if Prisma schemas exist.
- **Fullstack Monolith vs Backend API Heuristics**:
  Projects with server-side templates (Django MVT, Flask Jinja, Rails ERB, Laravel Blade) are recognized as fullstack applications, opening the homepage `/` in the browser. Only dedicated API services open interactive `/docs` documentation.
- **Windows Terminal & Encoding Resilience**:
  Stdout and stderr are reconfigured to UTF-8 to prevent `charmap` codec crashes on Windows consoles. Non-ASCII output characters are protected.

### 3.6 Automatic Dockerfile Fallback Recovery (AGENTS.md Rule 11)
- Located in `app/runners/runner.py`.
- Many public repositories ship broken, unbuildable Dockerfiles (e.g. monorepos with uncompiled build outputs like `COPY dist/api api` or referencing missing base images).
- When a repository's committed Dockerfile fails during `docker build`, RepoHost catches the failure automatically:
  ```text
  [!] Repository's own Dockerfile failed to build.
  [!] Attempting automatic recovery with RepoHost generated Dockerfile...
  [+] Automatic recovery succeeded with generated Dockerfile.
  ```
- RepoHost regenerates a tailored Dockerfile via `DockerfileGenerator` and retries the build automatically without requiring any manual intervention.

---

## 4. How to Bundle into a Standalone Executable (.exe)

RepoHost can be compiled into a single, portable executable (`RepoHost.exe`) using **PyInstaller**.

### Step 1: Install PyInstaller
Inside your Python virtual environment:
```powershell
pip install pyinstaller
```

### Step 2: Build the Standalone Executable

Run the following simple PyInstaller command from the project root:

#### On Windows:
```powershell
pyinstaller --name RepoHost --onefile --add-data "bin;bin" cli/main.py
```

#### On Linux / macOS:
```bash
pyinstaller --name RepoHost --onefile --add-data "bin:bin" cli/main.py
```

### Explanation of the Command:
- `--name RepoHost`: Names the compiled binary `RepoHost.exe`.
- `--onefile`: Packages the entire application, Python runtime, and all third-party dependencies (`typer`, `pydantic`, `httpx`, `gitpython`, etc.) into a single executable file.
- `--add-data "bin;bin"`: Bundles the `bin/` folder (which contains `cloudflared.exe`) directly into the executable so public tunnels work immediately without any manual downloads.
- `cli/main.py`: The entrypoint of the application.

### Output
The compiled binary will be located at:
```text
dist/RepoHost.exe
```

### Running the Executable
Drop `RepoHost.exe` into any folder or add it to your `PATH`, then run:
```powershell
RepoHost.exe https://github.com/user/project
```
No Python installation is required on the host machine. The executable will check if Docker Desktop is running (starting it if needed), clone the repo, containerize it, and expose the public URL!

---

## 5. Verified Repositories Matrix

The following real, public repositories have been tested and verified across all target architectures:

| Architecture / Framework | Verified Repository URL | What RepoHost Performs |
| :--- | :--- | :--- |
| **Multi-Tier Fullstack (React + Flask)** | `https://github.com/Remy349/todo-app-flask-reactjs` | Starts Flask on 5000, runs DB migrations/seed, connects Vite frontend on 5173, pins port, exposes via Cloudflare tunnels with auth |
| **Fullstack Django (SSR)** | `https://github.com/fidanazhan/django-social-media-clone` | Auto-migrates DB, seeds superuser (`admin` / `admin123`), sets tunnel allowed hosts, serves homepage |
| **FastAPI Backend + Swagger** | `https://github.com/zhanymkanov/fastapi-best-practices` | Runs Uvicorn, detects port 8000, auto-opens interactive Swagger docs at `/docs` |
| **Node.js Express REST API** | `https://github.com/CornflourBlue/node-mongo-signup-verification-api` | Runs Express with SQLite/in-memory fallback, discovers API routes, verifies port health |
| **Static HTML5 / JS App** | `https://github.com/gabrielecirulli/2048` | Detects static structure, spins up optimized HTTP static server, exposes playable 2048 game |
| **Java Spring Boot** | `https://github.com/spring-projects/spring-petclinic` | Runs Maven container, compiles Java 17 app, exposes port 8080 with Spring Actuator health check |

