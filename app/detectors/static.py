from pathlib import Path
from typing import Optional
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType

class StaticDetector(Detector):
    def detect(self, path: Path) -> Optional[DetectorResult]:
        if (path / "index.html").exists():
            return DetectorResult(
                project_type=ProjectType.STATIC,
                framework="HTML",
                install_command=[],
                run_command=["python", "-m", "http.server", "0"],
                confidence=0.5
            )
        return None
