import json
from pathlib import Path
from typing import Optional
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType

class NodeDetector(Detector):
    def detect(self, path: Path) -> Optional[DetectorResult]:
        package_json_path = path / "package.json"
        if not package_json_path.exists():
            return None
            
        try:
            with open(package_json_path, 'r', encoding='utf-8', errors='ignore') as f:
                package_data = json.load(f)
        except Exception:
            package_data = {}
            
        package_manager = "npm"
        if (path / "yarn.lock").exists():
            package_manager = "yarn"
        elif (path / "pnpm-lock.yaml").exists():
            package_manager = "pnpm"
        elif (path / "bun.lockb").exists() or (path / "bun.lock").exists():
            package_manager = "bun"
            
        deps = package_data.get("dependencies", {})
        dev_deps = package_data.get("devDependencies", {})
        all_deps = {**deps, **dev_deps}
        
        framework = "Node.js"
        if "next" in all_deps:
            framework = "Next.js"
        elif "vite" in all_deps:
            framework = "Vite"
        elif "react-scripts" in all_deps:
            framework = "React"
            
        available_scripts = package_data.get("scripts", {})
        
        run_script = None
        if "dev" in available_scripts:
            run_script = "dev"
        elif "start" in available_scripts:
            run_script = "start"
            
        if not run_script:
            if (path / "index.js").exists():
                return DetectorResult(
                    project_type=ProjectType.NODE,
                    framework=framework,
                    package_manager=package_manager,
                    install_command=[package_manager, "install"],
                    run_command=["node", "index.js"],
                    confidence=0.7
                )
            return None
            
        if package_manager == "npm":
            run_command = ["npm", "run", run_script]
        elif package_manager == "yarn":
            run_command = ["yarn", run_script]
        elif package_manager == "pnpm":
            run_command = ["pnpm", "run", run_script]
        elif package_manager == "bun":
            run_command = ["bun", "run", run_script]
            
        expected_ports = []
        if framework == "Vite":
            # Vite requires --host CLI flag to bind to 0.0.0.0 inside Docker.
            # ENV HOST does NOT work for Vite.
            if package_manager == "yarn":
                run_command.extend(["--host", "0.0.0.0"])
            else:
                run_command.extend(["--", "--host", "0.0.0.0"])
            expected_ports.append(5173)
        elif framework == "Next.js":
            if package_manager == "yarn":
                run_command.extend(["-H", "0.0.0.0"])
            else:
                run_command.extend(["--", "-H", "0.0.0.0"])
            expected_ports.append(3000)
            
        return DetectorResult(
            project_type=ProjectType.NODE,
            framework=framework,
            package_manager=package_manager,
            install_command=[package_manager, "install"],
            run_command=run_command,
            expected_ports=expected_ports,
            confidence=0.9
        )
