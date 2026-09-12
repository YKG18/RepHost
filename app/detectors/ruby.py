import re
from pathlib import Path
from typing import Optional, List
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType
from app.detectors.api_inspector import ApiInspector


class RubyDetector(Detector):
    def detect(self, path: Path) -> Optional[DetectorResult]:
        gemfile = path / "Gemfile"
        has_routes = (path / "config" / "routes.rb").exists()
        has_bin_rails = (path / "bin" / "rails").exists()
        has_config_ru = (path / "config.ru").exists()

        if not gemfile.exists() and not has_routes and not has_bin_rails and not has_config_ru:
            return None

        framework = "Ruby"
        gemfile_content = ""
        if gemfile.exists():
            try:
                gemfile_content = gemfile.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass

        if "rails" in gemfile_content.lower() or has_routes or has_bin_rails:
            framework = "Ruby on Rails"
            run_command = ["bundle", "exec", "rails", "server", "-b", "0.0.0.0", "-p", "3000"]
            expected_ports = [3000]
        elif "sinatra" in gemfile_content.lower():
            framework = "Sinatra"
            entry = "app.rb" if (path / "app.rb").exists() else ("main.rb" if (path / "main.rb").exists() else "server.rb")
            run_command = ["bundle", "exec", "ruby", entry, "-o", "0.0.0.0", "-p", "4567"]
            expected_ports = [4567, 3000]
        else:
            run_command = ["bundle", "exec", "rackup", "-o", "0.0.0.0", "-p", "9292"] if has_config_ru else ["ruby", "main.rb"]
            expected_ports = [9292, 3000]

        install_command = ["bundle", "install"]

        is_api, docs_url, api_endpoints = ApiInspector.inspect(path, framework)

        return DetectorResult(
            project_type=ProjectType.RUBY,
            framework=framework,
            package_manager="bundle",
            install_command=install_command,
            run_command=run_command,
            expected_ports=expected_ports,
            confidence=0.9,
            is_backend_api=is_api,
            docs_url=docs_url,
            api_endpoints=api_endpoints
        )
