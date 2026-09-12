import re
from pathlib import Path
from typing import Optional
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType

COMPOSE_FILES = ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]
EXPOSE_RE = re.compile(r'^\s*EXPOSE\s+(\d+)', re.IGNORECASE | re.MULTILINE)


class DockerDetector(Detector):
    """Last-resort detector for repos whose only runnable manifest is
    Docker-based. Kept at lower confidence than direct Node/Python detection
    so a plain `npm install && npm run dev` project with an incidental
    Dockerfile still runs the fast, native way."""

    def detect(self, path: Path) -> Optional[DetectorResult]:
        compose_file = next((f for f in COMPOSE_FILES if (path / f).exists()), None)
        dockerfile = path / "Dockerfile"

        if compose_file:
            return DetectorResult(
                project_type=ProjectType.DOCKER,
                framework="Docker Compose",
                install_command=["docker", "compose", "build"],
                run_command=["docker", "compose", "up"],
                confidence=0.55,
            )

        if dockerfile.exists():
            container_port = 8080
            try:
                text = dockerfile.read_text(encoding="utf-8", errors="ignore")
                m = EXPOSE_RE.search(text)
                if m:
                    container_port = int(m.group(1))
            except Exception:
                pass

            return DetectorResult(
                project_type=ProjectType.DOCKER,
                framework="Dockerfile",
                install_command=["docker", "build", "-t", "repohost-app", "."],
                run_command=["docker", "run", "--rm", "--name", "repohost-app-run", "-p", str(container_port)],
                expected_ports=[container_port],
                confidence=0.5,
            )

        return None
