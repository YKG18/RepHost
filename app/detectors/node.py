import json
from pathlib import Path
from typing import Optional, List
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType
from app.detectors.api_inspector import ApiInspector


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
        # Backend frameworks
        if "@nestjs/core" in all_deps:
            framework = "NestJS"
        elif "express" in all_deps:
            framework = "Express"
        elif "fastify" in all_deps:
            framework = "Fastify"
        elif "koa" in all_deps:
            framework = "Koa"
        elif "hono" in all_deps:
            framework = "Hono"
        # Frontend / Fullstack frameworks
        elif "next" in all_deps:
            framework = "Next.js"
        elif "nuxt" in all_deps:
            framework = "Nuxt"
        elif "@sveltejs/kit" in all_deps or "svelte" in all_deps:
            framework = "SvelteKit" if "@sveltejs/kit" in all_deps else "Svelte"
        elif "astro" in all_deps:
            framework = "Astro"
        elif "@remix-run/react" in all_deps or "@remix-run/node" in all_deps:
            framework = "Remix"
        elif "@angular/core" in all_deps:
            framework = "Angular"
        elif "vite" in all_deps:
            framework = "Vite"
        elif "react-scripts" in all_deps:
            framework = "React"
            
        available_scripts = package_data.get("scripts", {})
        
        run_script = None
        # Priority order of scripts to run
        for script_candidate in ["dev", "start", "serve", "preview"]:
            if script_candidate in available_scripts:
                run_script = script_candidate
                break
            
        expected_ports: List[int] = []
        is_api, docs_url, api_endpoints = ApiInspector.inspect(path, framework)

        if not run_script:
            for entry_file in ["index.js", "server.js", "app.js", "main.js", "src/index.js", "src/server.js", "src/app.js", "src/main.js"]:
                if (path / entry_file).exists():
                    return DetectorResult(
                        project_type=ProjectType.NODE,
                        framework=framework,
                        package_manager=package_manager,
                        install_command=[package_manager, "install"],
                        run_command=["node", entry_file],
                        expected_ports=[3000, 8000, 5000],
                        confidence=0.75,
                        is_backend_api=is_api,
                        docs_url=docs_url,
                        api_endpoints=api_endpoints
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
        else:
            run_command = ["npm", "run", run_script]
            
        # Bind flags for frameworks that bind to localhost by default
        if framework in ("Vite", "Svelte", "SvelteKit"):
            if package_manager == "yarn":
                run_command.extend(["--host", "0.0.0.0"])
            else:
                run_command.extend(["--", "--host", "0.0.0.0"])
            expected_ports = [5173, 3000]
        elif framework == "Next.js":
            if package_manager == "yarn":
                run_command.extend(["-H", "0.0.0.0"])
            else:
                run_command.extend(["--", "-H", "0.0.0.0"])
            expected_ports = [3000]
        elif framework == "Nuxt":
            if package_manager == "yarn":
                run_command.extend(["--host", "0.0.0.0"])
            else:
                run_command.extend(["--", "--host", "0.0.0.0"])
            expected_ports = [3000]
        elif framework == "Astro":
            if package_manager == "yarn":
                run_command.extend(["--host", "0.0.0.0"])
            else:
                run_command.extend(["--", "--host", "0.0.0.0"])
            expected_ports = [4321, 3000]
        elif framework == "Angular":
            if package_manager == "yarn":
                run_command.extend(["--host", "0.0.0.0"])
            else:
                run_command.extend(["--", "--host", "0.0.0.0"])
            expected_ports = [4200]
        elif framework in ("Express", "NestJS", "Fastify", "Koa", "Hono"):
            expected_ports = [3000, 8000, 5000, 8080]
        else:
            expected_ports = [3000, 5173, 8080]
            
        return DetectorResult(
            project_type=ProjectType.NODE,
            framework=framework,
            package_manager=package_manager,
            install_command=[package_manager, "install"],
            run_command=run_command,
            expected_ports=expected_ports,
            confidence=0.9,
            is_backend_api=is_api,
            docs_url=docs_url,
            api_endpoints=api_endpoints
        )
