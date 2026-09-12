import re
from pathlib import Path
from typing import Optional, List
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType


class GoDetector(Detector):
    def detect(self, path: Path) -> Optional[DetectorResult]:
        go_mod = path / "go.mod"
        has_main = (path / "main.go").exists()
        
        if not go_mod.exists() and not has_main:
            return None
            
        framework = "Go"
        mod_content = ""
        if go_mod.exists():
            try:
                mod_content = go_mod.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass

        # Framework detection from go.mod or imports
        if "github.com/gin-gonic/gin" in mod_content:
            framework = "Gin"
        elif "github.com/labstack/echo" in mod_content:
            framework = "Echo"
        elif "github.com/gofiber/fiber" in mod_content:
            framework = "Fiber"
        elif "github.com/go-chi/chi" in mod_content:
            framework = "Chi"

        run_command = ["go", "run", "."] if (path / "main.go").exists() or go_mod.exists() else ["go", "run", "main.go"]
        install_command = ["go", "mod", "download"] if go_mod.exists() else None

        # Inspect basic endpoints from .go files
        endpoints = set()
        docs_url = None
        for p in path.rglob("*.go"):
            if any(part.startswith((".", "_")) or part in ("vendor",) for part in p.parts):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                matches = re.findall(r"\.(GET|POST|PUT|DELETE|Patch)\(\s*['\"]([^'\"]+)['\"]", content, re.IGNORECASE)
                for meth, route in matches:
                    clean = route if route.startswith("/") else f"/{route}"
                    endpoints.add(f"{meth.upper():<6} {clean}")
                if "swagger" in content.lower() and not docs_url:
                    docs_url = "/swagger/index.html"
            except Exception:
                continue

        is_backend_api = bool(endpoints or framework in ("Gin", "Echo", "Fiber", "Chi"))

        return DetectorResult(
            project_type=ProjectType.GO,
            framework=framework,
            package_manager="go",
            install_command=install_command,
            run_command=run_command,
            expected_ports=[8080, 3000, 8000],
            confidence=0.85,
            is_backend_api=is_backend_api,
            docs_url=docs_url,
            api_endpoints=sorted(list(endpoints))[:20]
        )
