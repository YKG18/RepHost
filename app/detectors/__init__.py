from .base import Detector
from .static import StaticDetector
from .node import NodeDetector
from .python import PythonDetector
from .java import JavaDetector
from .ruby import RubyDetector
from .php import PhpDetector
from .dotnet import DotnetDetector
from .docker_compose import DockerComposeDetector
from .go import GoDetector
from .rust import RustDetector
from typing import List, Optional
from pathlib import Path
from app.core.models import DetectorResult

def _detect_single_path(path: Path, detectors: List[Detector]) -> Optional[DetectorResult]:
    from .environment import detect_environment_variables
    best_result = None
    best_confidence = -1.0
    
    for detector in detectors:
        result = detector.detect(path)
        if result and result.confidence > best_confidence:
            best_result = result
            best_confidence = result.confidence
            
    if best_result:
        env_vars = detect_environment_variables(path)
        if env_vars:
            best_result.env_vars.update(env_vars)
            
    return best_result

def detect_project(root_path: Path) -> List[DetectorResult]:
    """
    Scans the repository and returns a list of detected projects.
    Supports multi-tier architectures (e.g. backend/ and frontend/ folders).
    """
    detectors: List[Detector] = [
        DockerComposeDetector(),
        NodeDetector(),
        PythonDetector(),
        JavaDetector(),
        RubyDetector(),
        PhpDetector(),
        DotnetDetector(),
        GoDetector(),
        RustDetector(),
        StaticDetector()
    ]
    
    results = []
    
    # 1. Check root first
    root_result = _detect_single_path(root_path, detectors)
    from app.core.models import ProjectType
    if root_result and root_result.project_type == ProjectType.DOCKER_COMPOSE:
        root_result.sub_path = "."
        return [root_result]

    # 2. Check 1-level deep subdirectories for distinct projects
    sub_results = []
    manifests = [
        "package.json", "requirements.txt", "Pipfile", "pyproject.toml",
        "setup.py", "manage.py", "pom.xml", "build.gradle", "build.gradle.kts",
        "Gemfile", "Cargo.toml", "go.mod", "composer.json", "Dockerfile"
    ]
    ignored_subdirs = {
        "node_modules", "venv", ".venv", "__pycache__", "scratch", "target",
        "build", "dist", "templates", "template", "views", "static", "media",
        "assets", "public", "tests", "test", "spec", "migrations", "fixtures",
        "locale", "locales", "config", "logs", "scripts", "docs", "documentation",
        ".git", ".github", ".vscode", ".idea"
    }

    for child in root_path.iterdir():
        if child.is_dir() and not child.name.startswith(".") and child.name.lower() not in ignored_subdirs:
            child_result = _detect_single_path(child, detectors)
            if child_result and child_result.confidence >= 0.7:
                # If root was already detected with high confidence (e.g. Django, Rails, Next.js root),
                # only accept a subfolder if it has its own explicit project manifest
                # or is an explicit frontend directory (e.g. frontend/, client/, ui/, web/)
                if root_result and root_result.confidence >= 0.8:
                    has_own_manifest = any((child / m).exists() for m in manifests)
                    is_known_frontend_dir = child.name.lower() in ("frontend", "client", "ui", "web", "app")
                    if not (has_own_manifest or is_known_frontend_dir):
                        continue

                child_result.sub_path = child.name
                sub_results.append(child_result)

    # 3. Combine: If subprojects exist, root is only included if root itself has an explicit manifest
    if sub_results:
        root_has_manifest = any((root_path / m).exists() for m in manifests)
        if root_result and root_result.confidence >= 0.8 and root_has_manifest:
            root_result.sub_path = "."
            return [root_result] + sub_results
        return sub_results

    # 4. Fallback: If no subprojects found, use root_result if available
    if root_result:
        root_result.sub_path = "."
        return [root_result]

    return []
