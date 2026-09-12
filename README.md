# RepoHost

> **Zero-Configuration Repository Hosting & Public Tunneling**
>
> Turn any public GitHub repository into a locally running, publicly accessible web application in seconds.

---

## What is RepoHost?

RepoHost takes a public GitHub repository URL, automatically determines how the application should be built and executed, runs it in an isolated Docker container, and exposes it to the internet via a temporary public Cloudflare tunnel.

The user does not need to configure ports, open terminal windows, figure out package managers, install runtimes (Node, Python, Java, Ruby, Go, PHP, Rust, .NET), or configure tunnels.

```text
Paste GitHub URL
        ↓
RepoHost checks & auto-launches Docker Desktop (if needed)
        ↓
RepoHost clones repository into isolated workspace
        ↓
RepoHost detects project type & dependencies (deterministic)
        ↓
RepoHost starts backend services & runs migrations/seeds
        ↓
RepoHost bridges frontend to backend (port pinning / URL rewriting)
        ↓
RepoHost detects active listening ports & verifies HTTP health
        ↓
RepoHost creates public tunnel (Cloudflare)
        ↓
User receives Public URL & interactive API Docs (if backend API)
```

---

## Key Features

- **Zero Host Runtimes Required**: All builds and dependencies (Node, Python, Java 17, Ruby, PHP, Go, Rust, .NET 8) run inside isolated Docker container layers.
- **Docker Desktop Auto-Start**: Automatically verifies Docker daemon status before starting. If Docker Desktop is stopped, RepoHost finds the installation and launches it automatically.
- **Multi-Tier Frontend↔Backend Bridging**: Intelligently identifies repositories with separate frontend and backend tiers (e.g. React/Vite frontend and Flask backend), orchestrates backend startup first, pins host ports, rewrites hardcoded API URLs across frontend source code, and injects environment variables.
- **First-Class Backend API Support**: Identifies standalone APIs (FastAPI, Flask, Express, Spring Boot, etc.), extracts routes, identifies Swagger/OpenAPI documentation endpoints (`/docs`, `/swagger-ui`), and opens the browser directly to interactive documentation.
- **Automatic Error Recovery (Rule 11)**: When a repository ships a broken, unbuildable Dockerfile (e.g. referencing unbuilt build artifacts or missing files), RepoHost automatically catches the failure, generates a tailored Dockerfile, and retries the build automatically.
- **Automated Database Migrations & Seeding**:
  - **Django**: Runs `migrate --noinput` and seeds an admin superuser (`admin` / `admin123`).
  - **Flask**: Runs `flask db upgrade` and `seed.py` if present.
  - **Node/Prisma**: Runs `npx prisma generate` and `npx prisma db push` if Prisma schemas exist.
- **Permissive CORS & Auth Secret Injection**: Automatically configures permissive CORS origins and injects default development secrets (`JWT_SECRET_KEY`, `SECRET_KEY`, `SESSION_SECRET`) to prevent HTTP 500 crashes on authentication routes.
- **Ephemeral Sessions & Graceful Cleanup**: Configurable session timeouts (default 5 hours). Automatically terminates containers, closes tunnels, and cleans temporary workspaces upon expiration or `Ctrl+C`.
- **Portable & Standalone**: Fully relative paths with zero hardcoded filesystem dependencies. Can be compiled into a single-file portable executable (`RepoHost.exe`) with PyInstaller.

---

## Supported Frameworks & Runtimes

| Framework / Language | Markers & Manifests | Package Manager | Default Ports | Special Capabilities |
| :--- | :--- | :--- | :--- | :--- |
| **Django** (Python) | `manage.py`, `wsgi.py` | `pip` | 8000 | Auto-migrates DB, seeds admin user, sets tunnel allowed hosts |
| **FastAPI** (Python) | `fastapi`, `uvicorn` | `pip` | 8000 | Discovers routes, tests `/docs` OpenAPI, auto-opens Swagger |
| **Flask / FlaskAPI** | `app.py`, `Flask(` | `pip` | 5000, 8000 | Injects auth secrets, runs migrations & seeds, tests `/docs` |
| **Spring Boot** (Java) | `pom.xml`, `build.gradle` | `mvn` / `gradle` | 8080 | Java 17 container build, detects Spring endpoints |
| **Ruby on Rails** | `Gemfile`, `routes.rb` | `bundle` | 3000 | Prepares DB, inspects routes, exposes port 3000 |
| **PHP / Laravel** | `composer.json`, `artisan` | `composer` | 8000 | Auto-generates app key, inspects API routes |
| **ASP.NET Core** (C#) | `*.csproj`, `Program.cs` | `dotnet` | 5000, 8080 | SDK 8.0 build, Minimal APIs & Swagger detection |
| **Node.js Fullstack** | Vite, Next.js, Nuxt, Astro, Svelte | `npm` / `pnpm` / `yarn` / `bun` | 3000, 5173, 4200, 4321 | Injects host bindings (`--host 0.0.0.0`), auto-connects to backend |
| **Node.js Backend** | Express, NestJS, Fastify, Koa | `npm` / `pnpm` / `yarn` | 3000, 8000, 8080 | Prisma client generation, route discovery |
| **Go** | `go.mod`, `main.go` | `go` | 8080, 8000 | Alpine build, Gin/Fiber/Echo detection |
| **Rust** | `Cargo.toml` | `cargo` | 8080, 8000 | Cargo build, Actix/Axum/Rocket detection |
| **Static Sites** | `index.html` | None | 8000 | Isolated Python static HTTP server |
| **Docker Compose** | `docker-compose.yml`, `compose.yaml` | Docker | Dynamic | Native multi-container composition |

---

## Quick Start

### Windows (Batch Script)

```powershell
# Run using the bundled batch script
.\repohost.bat https://github.com/user/project
```

### Python Virtual Environment

```powershell
# 1. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate # Linux / macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the CLI
python -m cli.main https://github.com/user/project
```

---

## CLI Options

```text
Usage: python -m cli.main [OPTIONS] REPO_URL

Arguments:
  REPO_URL                Public GitHub repository URL or local repository path. [required]

Options:
  --duration TEXT         Session duration (e.g., 30m, 1h, 3h, 5h). [default: 5h]
  --port INTEGER          Override candidate port for the service.
  --no-tunnel             Disable public Cloudflare tunnel (localhost only).
  --no-open               Disable automatic browser opening.
  --help                  Show help message and exit.
```

### Examples

```powershell
# Host a multi-tier app for 1 hour without opening the browser
.\repohost.bat https://github.com/Remy349/todo-app-flask-reactjs --duration 1h --no-open

# Host a FastAPI backend API locally without a public tunnel
.\repohost.bat https://github.com/zhanymkanov/fastapi-best-practices --no-tunnel

# Host a Django web application
.\repohost.bat https://github.com/fidanazhan/django-social-media-clone
```

---

## Verified Repositories to Test

Test RepoHost immediately with these verified, public repositories:

| Architecture | Repository URL | Verified Behavior |
| :--- | :--- | :--- |
| **Multi-Tier Fullstack (React + Flask)** | `https://github.com/Remy349/todo-app-flask-reactjs` | Starts Flask on port 5000, runs migrations, connects Vite frontend on 5173, pins host port, exposes both services with working auth & CRUD |
| **Fullstack Django (SSR)** | `https://github.com/fidanazhan/django-social-media-clone` | Auto-migrates SQLite, creates default superuser `admin` / `admin123`, sets allowed hosts for tunnels, opens homepage |
| **FastAPI Backend + Swagger** | `https://github.com/zhanymkanov/fastapi-best-practices` | Runs Uvicorn, detects port 8000, auto-opens interactive Swagger docs at `/docs` |
| **Node.js Express REST API** | `https://github.com/CornflourBlue/node-mongo-signup-verification-api` | Runs Express with SQLite/in-memory fallback, discovers API routes, verifies port health |
| **Static HTML5 / JS App** | `https://github.com/gabrielecirulli/2048` | Detects static structure, spins up HTTP static server, exposes playable 2048 game |
| **Java Spring Boot** | `https://github.com/spring-projects/spring-petclinic` | Runs Maven container, compiles Java 17 app, exposes port 8080 |

---

## Building a Standalone Executable (.exe)

RepoHost can be compiled into a single portable binary using **PyInstaller**:

```powershell
# 1. Install PyInstaller
pip install pyinstaller

# 2. Compile into a single executable
pyinstaller --name RepoHost --onefile --add-data "bin;bin" cli/main.py   # Windows
# pyinstaller --name RepoHost --onefile --add-data "bin:bin" cli/main.py # Linux / macOS
```

The compiled binary will be placed at `dist/RepoHost.exe`. You can drop this executable into any directory or your system `PATH` and run:

```powershell
RepoHost.exe https://github.com/user/project
```

No Python installation is required on the host machine.

---

## Architecture

```text
repohost/
├── app/
│   ├── core/           # Configuration, models, and path management
│   ├── detectors/      # Deterministic framework & language detectors
│   │   ├── api_inspector.py     # Backend route & OpenAPI/Swagger inspector
│   │   ├── connection_bridge.py # Multi-tier frontend↔backend correlation & bridging
│   │   ├── node.py              # Node.js / Vite / Next.js / Express detector
│   │   ├── python.py            # Django / FastAPI / Flask / Streamlit detector
│   │   ├── java.py              # Spring Boot (Maven / Gradle) detector
│   │   ├── ruby.py              # Ruby on Rails detector
│   │   ├── php.py               # PHP / Laravel detector
│   │   ├── dotnet.py            # ASP.NET Core detector
│   │   ├── go.py                # Go (Gin, Fiber, Echo) detector
│   │   ├── rust.py              # Rust (Actix, Axum, Rocket) detector
│   │   ├── static.py            # Static HTML5 detector
│   │   └── docker_compose.py    # Docker Compose detector
│   ├── sandbox/        # Container isolation & Dockerfile generation
│   │   ├── docker_checker.py    # Docker Desktop auto-detection & auto-start
│   │   └── dockerfile_generator.py # Dynamic container builder & patching
│   ├── runners/        # Container lifecycle & automatic build recovery
│   ├── health/         # HTTP and API endpoint health checks
│   └── tunnel/         # Ephemeral Cloudflare tunnel manager
├── cli/
│   └── main.py         # Multi-tier orchestrator & interactive CLI
├── tests/              # Automated unit and integration test suite
├── working.md          # Comprehensive technical architecture & design document
├── repohost.bat        # Windows launcher script
└── requirements.txt    # Host Python dependencies
```
