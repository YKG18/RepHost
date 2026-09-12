from pathlib import Path
from typing import Optional
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType

class StaticDetector(Detector):
    def detect(self, path: Path) -> Optional[DetectorResult]:
        # High confidence if index.html is at the root
        if (path / "index.html").exists():
            return DetectorResult(
                project_type=ProjectType.STATIC,
                framework="HTML",
                install_command=[],
                run_command=["python", "-m", "http.server", "0"],
                confidence=0.8
            )
            
        # Fallback: If there are ANY html files in the repository,
        # we can still serve the directory as a generic static file server.
        # But use low confidence so Node/Python detectors take precedence if present.
        try:
            if next(path.rglob("*.html"), None):
                return DetectorResult(
                    project_type=ProjectType.STATIC,
                    framework="HTML (Static Directory)",
                    install_command=[],
                    run_command=["python", "-m", "http.server", "0"],
                    confidence=0.2
                )
        except StopIteration:
            pass
            
        return None
