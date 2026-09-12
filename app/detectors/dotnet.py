import re
from pathlib import Path
from typing import Optional, List
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType
from app.detectors.api_inspector import ApiInspector


class DotnetDetector(Detector):
    def detect(self, path: Path) -> Optional[DetectorResult]:
        has_csproj = any(path.glob("*.csproj")) or any(path.glob("*/*.csproj"))
        has_sln = any(path.glob("*.sln"))
        has_program_cs = (path / "Program.cs").exists()

        if not has_csproj and not has_sln and not has_program_cs:
            return None

        framework = "ASP.NET Core"
        package_manager = "dotnet"

        install_command = ["dotnet", "restore"]
        run_command = ["dotnet", "run", "--urls", "http://0.0.0.0:5000"]

        is_api, docs_url, api_endpoints = ApiInspector.inspect(path, framework)

        # Default Swagger UI for ASP.NET Core if endpoints exist
        if not docs_url and is_api:
            docs_url = "/swagger/index.html"

        return DetectorResult(
            project_type=ProjectType.DOTNET,
            framework=framework,
            package_manager=package_manager,
            install_command=install_command,
            run_command=run_command,
            expected_ports=[5000, 8080],
            confidence=0.88,
            is_backend_api=is_api,
            docs_url=docs_url,
            api_endpoints=api_endpoints
        )
