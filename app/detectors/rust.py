import re
from pathlib import Path
from typing import Optional
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType


class RustDetector(Detector):
    def detect(self, path: Path) -> Optional[DetectorResult]:
        cargo_toml = path / "Cargo.toml"
        if not cargo_toml.exists():
            return None
            
        framework = "Rust"
        cargo_content = ""
        try:
            cargo_content = cargo_toml.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass

        if "actix-web" in cargo_content:
            framework = "Actix-web"
        elif "axum" in cargo_content:
            framework = "Axum"
        elif "rocket" in cargo_content:
            framework = "Rocket"
        elif "warp" in cargo_content:
            framework = "Warp"

        endpoints = set()
        docs_url = None
        for p in path.rglob("*.rs"):
            if any(part.startswith((".", "_")) or part in ("target",) for part in p.parts):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                # Actix: #[get("/path")] or Axum: .route("/path", get(...))
                matches = re.findall(r'#\[(get|post|put|delete)\(\s*["\']([^"\']+)["\']\s*\)\]', content, re.IGNORECASE)
                for meth, route in matches:
                    clean = route if route.startswith("/") else f"/{route}"
                    endpoints.add(f"{meth.upper():<6} {clean}")
                axum_matches = re.findall(r'\.route\(\s*["\']([^"\']+)["\']\s*,\s*(get|post|put|delete)', content, re.IGNORECASE)
                for route, meth in axum_matches:
                    clean = route if route.startswith("/") else f"/{route}"
                    endpoints.add(f"{meth.upper():<6} {clean}")
                if "utoipa" in content or "swagger" in content.lower():
                    docs_url = "/swagger-ui"
            except Exception:
                continue

        is_backend_api = bool(endpoints or framework in ("Actix-web", "Axum", "Rocket", "Warp"))

        return DetectorResult(
            project_type=ProjectType.RUST,
            framework=framework,
            package_manager="cargo",
            install_command=["cargo", "build"],
            run_command=["cargo", "run"],
            expected_ports=[8080, 3000, 8000],
            confidence=0.85,
            is_backend_api=is_backend_api,
            docs_url=docs_url,
            api_endpoints=sorted(list(endpoints))[:20]
        )
