import json
from pathlib import Path
from typing import Optional
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType

# Preferred dev/run scripts, in priority order. "dev" first because it runs
# without requiring a separate build step (best fit for "just make it work").
SCRIPT_PRIORITY = ["dev", "develop", "start", "serve", "preview"]

# Common entrypoint filenames to fall back to when package.json has no
# usable script at all.
ENTRY_FALLBACKS = [
    "server.js", "index.js", "app.js", "main.js",
    "src/index.js", "src/server.js", "src/app.js", "src/main.js",
    "bin/www",
]


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

        deps = package_data.get("dependencies", {}) or {}
        dev_deps = package_data.get("devDependencies", {}) or {}
        all_deps = {**deps, **dev_deps}

        framework = "Node.js"
        if "next" in all_deps:
            framework = "Next.js"
        elif "nuxt" in all_deps or "nuxt3" in all_deps:
            framework = "Nuxt"
        elif "@sveltejs/kit" in all_deps:
            framework = "SvelteKit"
        elif "svelte" in all_deps:
            framework = "Svelte"
        elif "vue" in all_deps:
            framework = "Vue"
        elif "@angular/core" in all_deps:
            framework = "Angular"
        elif "astro" in all_deps:
            framework = "Astro"
        elif "vite" in all_deps:
            framework = "Vite"
        elif "react-scripts" in all_deps:
            framework = "React"
        elif "express" in all_deps:
            framework = "Express"
        elif "@nestjs/core" in all_deps:
            framework = "NestJS"

        install_command = [package_manager, "install"]
        available_scripts = package_data.get("scripts", {}) or {}

        run_script = next((s for s in SCRIPT_PRIORITY if s in available_scripts), None)

        if run_script:
            if package_manager == "npm":
                run_command = ["npm", "run", run_script]
            elif package_manager == "yarn":
                run_command = ["yarn", run_script]
            elif package_manager == "pnpm":
                run_command = ["pnpm", "run", run_script]
            else:  # bun
                run_command = ["bun", "run", run_script]

            return DetectorResult(
                project_type=ProjectType.NODE,
                framework=framework,
                package_manager=package_manager,
                install_command=install_command,
                run_command=run_command,
                confidence=0.9,
            )

        # No usable script. Fall back to the package.json "main" field, then
        # a list of conventional entrypoint filenames.
        candidates = []
        main_field = package_data.get("main")
        if main_field:
            candidates.append(main_field)
        candidates.extend(ENTRY_FALLBACKS)

        entry = next((c for c in candidates if (path / c).exists()), None)
        if entry:
            return DetectorResult(
                project_type=ProjectType.NODE,
                framework=framework,
                package_manager=package_manager,
                install_command=install_command,
                run_command=["node", entry],
                confidence=0.65,
            )

        return None
