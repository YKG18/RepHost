# AGENTS.md

## Project: RepoHost

Build a polished local application called **RepoHost**.

RepoHost takes a public GitHub repository URL, automatically determines how the repository should be run, launches it locally, exposes the running application through a temporary public tunnel, and provides the user with a shareable URL.

The primary goal is NOT to build an AI agent.

The primary goal is:

> Given a normal public GitHub repository containing a runnable web application, RepoHost should require as close to zero configuration as possible to get that application running locally and publicly accessible.

The system should feel like a serious developer tool, not a hackathon proof-of-concept held together with shell commands.

---

# 1. Core User Experience

The user should be able to do:

```text
Paste GitHub URL
        ↓
Click "Host"
        ↓
RepoHost analyzes repository
        ↓
RepoHost installs dependencies
        ↓
RepoHost starts application
        ↓
RepoHost detects the actual listening port
        ↓
RepoHost performs health checks
        ↓
RepoHost creates public tunnel
        ↓
User receives public URL
```

Example:

```text
https://github.com/user/project
```

should result in something similar to:

```text
Repository
  user/project

✓ Repository cloned
✓ Node.js project detected
✓ Package manager: npm
✓ Dependencies installed
✓ Application started
✓ Port 5173 detected
✓ Application responding
✓ Public tunnel established

PUBLIC URL
https://random-name.trycloudflare.com

Running locally:
http://localhost:5173

Expires:
04:59:32
```

The user should not need to manually open a terminal and determine the framework themselves.

---

# 2. DO NOT OVERUSE AI

Do NOT introduce an LLM merely because the project sounds like an "agent".

Most repository detection should be deterministic.

Use:

- filesystem inspection
- manifest detection
- lockfile detection
- package metadata
- Docker metadata
- framework conventions
- process inspection
- HTTP health checks

Only consider an LLM/AI fallback if deterministic detection genuinely cannot determine how to run the project.

The architecture should work perfectly without an API key.

AI must NEVER be a hard dependency for the core product.

---

# 3. Repository Detection

After cloning a repository, inspect its structure.

Support at minimum:

### Static websites

Detect:

```text
index.html
```

Possible execution:

```text
python -m http.server PORT
```

or another reliable local static server.

---

### Node.js

Detect:

```text
package.json
```

Inspect:

```text
package.json
package-lock.json
yarn.lock
pnpm-lock.yaml
bun.lock
bun.lockb
```

Determine package manager automatically.

Support:

```text
npm
yarn
pnpm
bun
```

Inspect the `scripts` section of `package.json`.

Prefer appropriate development/start scripts.

Examples:

```text
npm run dev
npm start
yarn dev
pnpm dev
bun run dev
```

Do NOT blindly assume `npm start`.

Determine the most appropriate command based on the repository.

Recognize common frameworks including:

```text
React
Vite
Next.js
Nuxt
Vue
Angular
Svelte
SvelteKit
Express
NestJS
Astro
Remix
```

---

### Python

Detect:

```text
requirements.txt
pyproject.toml
Pipfile
poetry.lock
```

Recognize common web frameworks:

```text
Flask
FastAPI
Django
Streamlit
```

Determine the appropriate execution command.

Examples:

```text
flask run
uvicorn main:app
python manage.py runserver
streamlit run app.py
```

Do not hardcode only one filename.

Search the repository intelligently for likely application entrypoints.

---

### Docker

Detect:

```text
Dockerfile
docker-compose.yml
docker-compose.yaml
compose.yml
compose.yaml
```

If a Docker configuration exists and is clearly intended to run the application, prefer the Docker-based execution path.

Support multi-container applications where practical.

---

### Other Projects

Create an extensible detector architecture.

Do not put every framework in one giant `if/else` block.

Use something conceptually similar to:

```text
Detector
├── StaticDetector
├── NodeDetector
├── PythonDetector
├── DockerDetector
└── Future detectors
```

Each detector should return structured information describing:

```text
project_type
framework
package_manager
install_command
run_command
expected_ports
entrypoint
confidence
```

---

# 4. Repository Analysis

Before executing arbitrary commands, inspect the repository.

Collect:

```text
language
framework
package manager
lockfile
runtime requirements
entrypoint
available scripts
Docker configuration
environment variable references
likely ports
database dependencies
```

Show this information in the UI.

Example:

```text
Detected Project

Framework       Next.js
Language        TypeScript
Package Manager pnpm
Node Version    20
Start Command   pnpm dev
Port            3000
Environment     3 variables detected
```

---

# 5. Environment Variables

Inspect files such as:

```text
.env.example
.env.sample
README.md
package.json
pyproject.toml
Docker configuration
```

Detect likely required environment variables.

Never fabricate secrets.

If required variables are missing, clearly report them.

Example:

```text
This project appears to require:

DATABASE_URL
NEXTAUTH_SECRET
STRIPE_SECRET_KEY

RepoHost cannot safely invent these values.

[Configure variables]
```

For repositories that work without environment variables, continue automatically.

---

# 6. Dependency Installation

Dependency installation must be handled automatically.

Examples:

Node:

```text
npm install
npm ci
yarn install
pnpm install
bun install
```

Prefer lockfile-respecting installation when possible.

Python:

Create an isolated virtual environment.

Example:

```text
.venv/
```

Then install dependencies.

Do not pollute the user's global Python environment.

---

# 7. Runtime Isolation

Do NOT execute arbitrary repositories directly in the user's primary environment whenever avoidable.

Prefer Docker for isolation when Docker is available.

The architecture should allow:

```text
GitHub Repository
        ↓
Temporary workspace
        ↓
Sandbox / container
        ↓
Application
```

The application should have access only to what it needs.

Never expose the user's entire filesystem to the repository.

Never execute:

```text
rm -rf /
```

or equivalent destructive commands.

Treat repository contents as untrusted input.

---

# 8. Process Management

RepoHost must manage the application process itself.

It should:

- start the process
- capture stdout
- capture stderr
- detect crashes
- detect restart loops
- detect listening ports
- terminate processes cleanly
- clean up child processes
- clean up containers
- clean up tunnels

Do NOT simply launch a shell command and forget about it.

Create a proper process manager abstraction.

Example:

```text
ProcessManager
├── start()
├── stop()
├── restart()
├── status()
├── logs()
└── cleanup()
```

---

# 9. Port Detection

Do NOT assume that every application uses port 3000.

The system should:

1. inspect framework defaults
2. inspect package configuration
3. inspect environment variables
4. inspect command arguments
5. monitor listening sockets
6. detect newly opened local ports
7. test candidate ports with HTTP requests

For example:

```text
Starting application...

Detected listening ports:

3000
5173

Testing...

5173 → HTTP 200
3000 → connection refused

Selected:
http://localhost:5173
```

If necessary, support dynamically assigning a free port.

---

# 10. Health Checks

Starting a process is NOT equivalent to successfully running an application.

After launching:

1. wait for startup
2. monitor logs
3. detect listening port
4. send HTTP requests
5. follow redirects
6. verify a successful response
7. retry with exponential backoff
8. report useful errors if startup fails

Example:

```text
Starting...
Waiting for server...
Waiting for server...
HTTP server detected
Health check passed
```

Do not mark the project as "running" merely because the process exists.

---

# 11. Automatic Recovery

If the first startup command fails:

Analyze the failure.

Examples:

```text
npm start failed
```

Try a reasonable alternative:

```text
npm run dev
```

or another detected script.

If the application crashes because the selected port is occupied, automatically select another port.

If dependencies are missing, install them.

If a known framework requires a particular startup procedure, adapt accordingly.

Do NOT blindly execute hundreds of commands.

Use bounded recovery attempts.

For example:

```text
Maximum automatic recovery attempts: 3
```

After that, provide the user with the actual error and logs.

---

# 12. Tunnel Integration

Use a pluggable tunnel architecture.

Support Cloudflare Tunnel first.

Optionally support:

```text
LocalTunnel
ngrok
```

The tunnel manager should conceptually expose:

```text
TunnelManager
├── start(port)
├── stop()
├── status()
└── public_url()
```

Do not tightly couple the entire application to Cloudflare.

The application should only care that it receives:

```text
localhost_port
public_url
tunnel_status
```

---

# 13. Temporary Hosting

The hosting session should be ephemeral.

The user can choose a duration such as:

```text
30 minutes
1 hour
3 hours
5 hours
Until stopped
```

Default:

```text
5 hours
```

Show a countdown.

Example:

```text
LIVE

https://example.trycloudflare.com

Expires in:
04:37:19
```

When the timer expires:

```text
Stop application
↓
Close tunnel
↓
Destroy container
↓
Delete temporary workspace
```

Cleanup must happen even if the UI is closed.

---

# 14. Public URL

The public URL must only expose the selected application port.

Never expose:

```text
SSH
filesystem
Docker daemon
database ports
other localhost services
```

The tunnel should point only to the intended application.

---

# 15. UI

Build a polished desktop/web interface.

The UI should NOT look like a generic admin dashboard.

Primary screen:

```text
┌──────────────────────────────────────────────┐
│ RepoHost                                     │
│                                              │
│ Turn any GitHub repository into a temporary  │
│ public application.                          │
│                                              │
│ ┌──────────────────────────────────────────┐ │
│ │ https://github.com/user/project          │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ Duration: [ 5 hours ▼ ]                      │
│                                              │
│             [ HOST REPOSITORY ]              │
│                                              │
└──────────────────────────────────────────────┘
```

During startup:

```text
Analyzing repository...
        ✓
Installing dependencies...
        ✓
Starting application...
        ✓
Detecting port...
        ✓
Creating tunnel...
        ✓
```

Once live:

```text
┌──────────────────────────────────────────────┐
│ ● LIVE                                       │
│                                              │
│ https://random-url.trycloudflare.com         │
│                                              │
│ Local    localhost:5173                      │
│ Runtime  Node.js                              │
│ Framework Vite                                │
│                                              │
│ Expires in 04:52:11                          │
│                                              │
│ [ COPY URL ]       [ STOP HOSTING ]          │
└──────────────────────────────────────────────┘
```

Include useful logs in an expandable panel.

---

# 16. Error UX

Errors must be understandable.

Bad:

```text
Process exited with code 1
```

Good:

```text
The application failed to start.

Reason:
DATABASE_URL is required but was not provided.

The repository declares this variable in .env.example.

[Configure Environment]
```

Show raw logs underneath for debugging.

---

# 17. CLI

Also provide a CLI.

Example:

```bash
repohost https://github.com/user/project
```

Expected output:

```text
RepoHost

→ Cloning repository
✓ Done

→ Detecting project
✓ Next.js / pnpm

→ Installing dependencies
✓ Done

→ Starting application
✓ Listening on port 3000

→ Creating public tunnel
✓ Tunnel established

PUBLIC URL
https://random.trycloudflare.com

Local URL
http://localhost:3000

Expires in 5 hours.
```

Support:

```bash
repohost <github-url>
repohost <github-url> --duration 1h
repohost <github-url> --port 3000
repohost <github-url> --no-tunnel
repohost stop
repohost logs
```

---

# 18. Architecture

Keep the project modular.

Recommended structure:

```text
repohost/
│
├── app/
│   ├── detectors/
│   ├── runners/
│   ├── sandbox/
│   ├── process/
│   ├── tunnel/
│   ├── health/
│   ├── environment/
│   ├── cleanup/
│   └── core/
│
├── cli/
│
├── ui/
│
├── tests/
│
├── workspaces/
│
├── AGENTS.md
├── README.md
└── requirements.txt
```

Do not put the entire implementation in one Python file.

---

# 19. Technology Choices

Use Python for the orchestration/backend layer.

Prefer well-maintained standard or common libraries.

Possible technologies:

```text
Python
FastAPI
Typer
Pydantic
httpx
psutil
GitPython or subprocess Git
Docker SDK
```

For the UI, choose a practical technology that can produce a polished interface quickly.

Do not introduce unnecessary infrastructure.

No database is required for the MVP.

Use a lightweight local state mechanism.

---

# 20. First-Class Supported Targets

The FIRST working implementation must prioritize these:

### Tier 1

```text
Static HTML
Vite + React
Node.js / Express
Next.js
Flask
FastAPI
```

### Tier 2

```text
Vue
Svelte
Angular
Django
Streamlit
Dockerized applications
```

The architecture must make adding more runtimes easy.

---

# 21. IMPORTANT: Real Repository Testing

Do NOT consider the project complete because the UI works.

The most important acceptance test is:

> Give RepoHost a real, previously unseen public GitHub repository and successfully launch it.

Create automated/integration tests using several real repositories representing different stacks.

Test at minimum:

```text
static HTML
React/Vite
Node
Next.js
Flask
FastAPI
Docker
```

Test repositories must be ordinary public repositories.

The system must:

```text
clone
detect
install
start
detect port
health-check
tunnel
serve
cleanup
```

Do not fake these stages in the UI.

Every green checkmark must correspond to an actual successful operation.

---

# 22. Failure Is Better Than Fake Success

NEVER fake successful deployment.

If something fails:

```text
✓ Clone
✓ Detect
✓ Install
✗ Start
```

Show the actual reason.

Do not display:

```text
✓ Application running
```

when it is not running.

---

# 23. Security

Assume GitHub repositories are untrusted.

At minimum:

- never run repositories as administrator/root unnecessarily
- isolate temporary workspaces
- prefer containers
- restrict exposed ports
- never expose the Docker socket to the application
- never expose the user's home directory
- sanitize repository URLs
- prevent path traversal
- prevent command injection
- never interpolate untrusted strings directly into shell commands
- use subprocess argument arrays where possible
- implement timeouts
- enforce resource limits where practical
- clean up after failures

The application should never assume a README or repository file is trustworthy.

---

# 24. No Magic

Do not write code such as:

```python
if github_url == "some-known-repo":
    ...
```

The system must generalize.

Do not hardcode a single demonstration repository.

The demo repository should be interchangeable with another repository without changing application code.

---

# 25. Development Strategy

Build incrementally.

### Phase 1

Implement:

```text
GitHub clone
↓
Static/Node/Python detection
↓
Dependency installation
↓
Application startup
↓
Port detection
↓
Health check
```

Do not build the UI first.

Make the execution engine reliable first.

### Phase 2

Implement:

```text
Tunnel manager
↓
Public URL
↓
Cleanup
↓
Expiration
```

### Phase 3

Implement the polished UI.

### Phase 4

Add Docker isolation.

### Phase 5

Add more framework detectors and intelligent fallback behavior.

---

# 26. Development Rule

After every significant implementation step:

1. Run the application.
2. Test the actual behavior.
3. Inspect logs.
4. Fix failures.
5. Add a regression test.
6. Continue.

Do not accumulate untested code.

---

# 27. Definition of Done

RepoHost is considered MVP-complete only when this works:

```text
User pastes:

https://github.com/<some-public-repository>

↓

RepoHost clones it.

↓

RepoHost determines what it is.

↓

RepoHost determines how to install it.

↓

RepoHost determines how to run it.

↓

RepoHost starts it.

↓

RepoHost finds the correct port.

↓

RepoHost confirms the application responds.

↓

RepoHost exposes ONLY that application through a tunnel.

↓

User receives a public URL.

↓

Another device can open that URL.

↓

The application remains accessible while the local process is running.

↓

User presses STOP.

↓

Application terminates.

↓

Tunnel terminates.

↓

Temporary resources are cleaned up.
```

That entire flow must be real.

---

# 28. Do Not Stop at Scaffolding

This is extremely important.

Do not respond with a plan and stop.

Do not create empty modules merely to satisfy the architecture.

Do not build placeholder buttons.

Do not mock deployment results.

Do not assume commands work without testing them.

If a dependency is missing, install it or clearly explain the blocker.

If a framework detector fails, improve it.

If a test repository fails, debug it.

Keep iterating until the complete end-to-end flow works for real repositories.

The objective is a working developer tool, not a prototype screenshot.

---

# Final Product Principle

RepoHost should feel like:

> "Give me a GitHub repository. I'll figure out how to run it, run it locally, and temporarily put it on the internet."

The implementation should be deterministic wherever possible, robust rather than clever, modular rather than monolithic, and honest about failures.

Build the boring engineering extremely well.