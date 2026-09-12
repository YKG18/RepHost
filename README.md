# Rephost — Layer 9: Database-Aware Multi-Service

Builds on Layers 1–8. Layer 9 keeps Docker Compose support and adds dependency readiness checks so database-backed projects are not declared ready merely because a frontend port is open. Rephost checks Compose service state/health before checking the browser-facing HTTP service.

Supported database containers are handled through the project's existing Compose configuration; Rephost does not replace or hard-code database credentials, schemas, or migrations.

Host requirements: Git, Docker.

Layer 8 real test remains valid: React + FastAPI + PostgreSQL projects can be run through their own Compose configuration.
