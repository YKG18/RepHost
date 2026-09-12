import json
from pathlib import Path
from typing import Optional, List
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType
from app.detectors.api_inspector import ApiInspector


class PhpDetector(Detector):
    def detect(self, path: Path) -> Optional[DetectorResult]:
        composer_json = path / "composer.json"
        has_artisan = (path / "artisan").exists()
        has_index_php = (path / "index.php").exists() or (path / "public" / "index.php").exists()

        if not composer_json.exists() and not has_artisan and not has_index_php:
            return None

        framework = "PHP"
        package_manager = "composer"
        composer_data = {}

        if composer_json.exists():
            try:
                with open(composer_json, "r", encoding="utf-8", errors="ignore") as f:
                    composer_data = json.load(f)
            except Exception:
                composer_data = {}

        reqs = composer_data.get("require", {})
        
        if has_artisan or "laravel/framework" in reqs:
            framework = "Laravel"
            run_command = ["php", "artisan", "serve", "--host=0.0.0.0", "--port=8000"]
        elif "symfony/framework-bundle" in reqs:
            framework = "Symfony"
            doc_root = "public" if (path / "public").is_dir() else "."
            run_command = ["php", "-S", "0.0.0.0:8000", "-t", doc_root]
        elif "slim/slim" in reqs:
            framework = "Slim"
            doc_root = "public" if (path / "public").is_dir() else "."
            run_command = ["php", "-S", "0.0.0.0:8000", "-t", doc_root]
        else:
            doc_root = "public" if (path / "public").is_dir() else "."
            run_command = ["php", "-S", "0.0.0.0:8000", "-t", doc_root]

        install_command = ["composer", "install", "--no-interaction"] if composer_json.exists() else None

        is_api, docs_url, api_endpoints = ApiInspector.inspect(path, framework)

        return DetectorResult(
            project_type=ProjectType.PHP,
            framework=framework,
            package_manager=package_manager,
            install_command=install_command,
            run_command=run_command,
            expected_ports=[8000, 8080],
            confidence=0.88,
            is_backend_api=is_api,
            docs_url=docs_url,
            api_endpoints=api_endpoints
        )
