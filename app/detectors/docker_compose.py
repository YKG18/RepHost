from pathlib import Path
from typing import Optional
from .base import Detector
from app.core.models import ProjectType, DetectorResult

class DockerComposeDetector(Detector):
    def detect(self, path: Path) -> Optional[DetectorResult]:
        compose_files = [
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml"
        ]
        
        for compose_file in compose_files:
            if (path / compose_file).is_file():
                return DetectorResult(
                    project_type=ProjectType.DOCKER_COMPOSE,
                    framework="Docker Compose",
                    package_manager=None,
                    install_command=None,
                    run_command=["docker-compose", "up", "-d", "--build"],
                    expected_ports=[],
                    confidence=1.0
                )
        
        return None
