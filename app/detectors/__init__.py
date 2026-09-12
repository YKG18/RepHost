from .base import Detector
from .static import StaticDetector
from .node import NodeDetector
from .python import PythonDetector
from .docker import DockerDetector
from typing import List, Optional
from pathlib import Path
from app.core.models import DetectorResult

# Common split-service monorepo layouts, checked in priority order. Each
# tuple is (backend_dir, frontend_dir). We prefer to run the backend side
# since it's the side most likely to "just work" without a separate build
# step, and report the frontend as present-but-not-started rather than
# silently ignoring it.
SPLIT_LAYOUTS = [
    ("backend", "frontend"),
    ("server", "client"),
    ("api", "web"),
    ("api", "ui"),
]

# Directories never worth descending into when looking for a runnable
# project one level down.
IGNORED_SCAN_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__",
    "dist", "build", "vendor", ".idea", ".vscode", "migrations",
}

_DETECTOR_CLASSES = [NodeDetector, PythonDetector, DockerDetector, StaticDetector]


def _build_detectors() -> List[Detector]:
    return [cls() for cls in _DETECTOR_CLASSES]


def _best_of(path: Path) -> Optional[DetectorResult]:
    """Run every detector against a single directory and return the
    highest-confidence match, if any."""
    best_result = None
    best_confidence = -1.0
    for detector in _build_detectors():
        result = detector.detect(path)
        if result and result.confidence > best_confidence:
            best_result = result
            best_confidence = result.confidence
    return best_result


def _candidate_subdirs(path: Path) -> List[Path]:
    try:
        return sorted(
            d for d in path.iterdir()
            if d.is_dir() and d.name not in IGNORED_SCAN_DIRS and not d.name.startswith(".")
        )
    except OSError:
        return []


def _detect_split_layout(path: Path) -> Optional[DetectorResult]:
    """Look for common backend+frontend (or equivalent) split-repo layouts
    one level deep. Runs the backend side and reports the frontend as an
    unstarted secondary service rather than returning nothing."""
    for backend_name, frontend_name in SPLIT_LAYOUTS:
        backend_dir = path / backend_name
        frontend_dir = path / frontend_name
        if not (backend_dir.is_dir() and frontend_dir.is_dir()):
            continue

        backend_result = _best_of(backend_dir)
        frontend_result = _best_of(frontend_dir)

        if backend_result is None and frontend_result is None:
            continue

        if backend_result is not None:
            primary, primary_dir = backend_result, backend_name
            secondary, secondary_dir = frontend_result, frontend_name
        else:
            # Backend side had nothing detectable - fall back to running the
            # frontend alone rather than reporting total failure.
            primary, primary_dir = frontend_result, frontend_name
            secondary, secondary_dir = None, None

        result = primary.model_copy(deep=True)
        result.working_dir = primary_dir
        result.matched_path = primary_dir

        secondary_services = list(result.secondary_services)
        if secondary is not None:
            secondary_services.append({
                "path": secondary_dir,
                "type": secondary.project_type.value,
                "framework": secondary.framework or "",
            })
        elif primary_dir == backend_name and (path / frontend_name).is_dir():
            # A frontend dir exists but nothing recognizable was found in
            # it - still worth surfacing so the user isn't left guessing.
            secondary_services.append({
                "path": frontend_name,
                "type": "unknown",
                "framework": "",
            })
        result.secondary_services = secondary_services

        return result

    return None


def _detect_in_subdirs(path: Path) -> Optional[DetectorResult]:
    """Generic one-level-deep fallback: if nothing was detected at the repo
    root and no known split layout matched, try every detector against
    every immediate subdirectory and report which one matched. This ensures
    we never silently return None just because the runnable project lives
    one directory down from a monorepo root (docs/, tooling configs, etc.
    at the top level)."""
    best_result = None
    best_confidence = -1.0
    best_dir = None

    for subdir in _candidate_subdirs(path):
        result = _best_of(subdir)
        if result and result.confidence > best_confidence:
            best_result = result
            best_confidence = result.confidence
            best_dir = subdir.name

    if best_result is None:
        return None

    result = best_result.model_copy(deep=True)
    result.working_dir = best_dir
    result.matched_path = best_dir
    return result


def detect_project(path: Path) -> Optional[DetectorResult]:
    root_result = _best_of(path)

    # A split backend+frontend layout takes priority over a root match when
    # the root match is weak (e.g. a root package.json that's just shared
    # lint/format tooling for the monorepo, not an app itself).
    split_result = _detect_split_layout(path)
    if split_result and (root_result is None or split_result.confidence >= root_result.confidence):
        return split_result

    if root_result:
        return root_result

    return _detect_in_subdirs(path)


def describe_scan(path: Path) -> List[str]:
    """Human-readable summary of what detect_project looked at, for use when
    detection fails completely. Keeps failures actionable instead of a bare
    'could not detect' with no context."""
    lines = [f"repo root ({path.name})"]

    split_dirs_present = [
        (b, f) for b, f in SPLIT_LAYOUTS
        if (path / b).is_dir() and (path / f).is_dir()
    ]
    if split_dirs_present:
        for b, f in split_dirs_present:
            lines.append(f"split layout candidate: {b}/ + {f}/")

    subdirs = _candidate_subdirs(path)
    if subdirs:
        shown = ", ".join(d.name for d in subdirs[:10])
        more = f" (+{len(subdirs) - 10} more)" if len(subdirs) > 10 else ""
        lines.append(f"subdirectories checked one level deep: {shown}{more}")
    else:
        lines.append("no subdirectories to check one level deep")

    return lines
