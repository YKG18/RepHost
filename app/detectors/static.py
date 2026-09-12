from pathlib import Path
from typing import Optional
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType

class StaticDetector(Detector):
    def detect(self, path: Path) -> Optional[DetectorResult]:
        # Server-side template directories must never be classified as static sites
        if path.name.lower() in ("templates", "template", "views", "pages", "partials", "components"):
            return None

        # High confidence if index.html is at the root
        index_file = path / "index.html"
        if index_file.exists():
            try:
                content = index_file.read_text(encoding="utf-8", errors="ignore")[:4096]
                # If it contains server-side template tags, it is a template, not a static HTML app
                if any(tag in content for tag in ("{% extends", "{% load", "{% block", "{% if", "{% for", "{% csrf_token", "{{", "<%=", "<?php", "th:")):
                    return None
            except Exception:
                pass

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
            for html_file in path.rglob("*.html"):
                if any(part in ("venv", ".venv", "__pycache__", "templates", "template", "views", "pages", "scratch", "node_modules") for part in html_file.parts):
                    continue
                try:
                    c = html_file.read_text(encoding="utf-8", errors="ignore")[:2048]
                    if any(tag in c for tag in ("{% extends", "{% load", "{% block", "{% if", "{% for", "{% csrf_token", "{{", "<%=", "<?php", "th:")):
                        continue
                except Exception:
                    pass
                return DetectorResult(
                    project_type=ProjectType.STATIC,
                    framework="HTML (Static Directory)",
                    install_command=[],
                    run_command=["python", "-m", "http.server", "0"],
                    confidence=0.2
                )
        except Exception:
            pass
            
        return None
