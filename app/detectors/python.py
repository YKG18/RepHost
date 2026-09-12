import os
import re
from pathlib import Path
from typing import Optional, Tuple, List
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType

FLASK_PATTERN = re.compile(r'^(\w+)\s*=\s*Flask\(', re.MULTILINE)
FASTAPI_PATTERN = re.compile(r'^(\w+)\s*=\s*FastAPI\(', re.MULTILINE)
# A module-level variable literally named `app`/`application`, regardless
# of its right-hand side. This is what Flask's own CLI looks for first
# (before trying a factory function), so a file like:
#   from myapp import create_app
#   app = create_app()
# is a perfectly valid entrypoint even though it never calls Flask(...)
# itself. Deliberately looser than FLASK_PATTERN - only used as a
# lower-priority fallback signal when FLASK_PATTERN doesn't match.
APP_VAR_PATTERN = re.compile(r'^(app|application)\s*=\s*\S', re.MULTILINE)
# App-factory functions (`def create_app(): ... return app`). Flask's own
# CLI auto-detects and calls these when pointed at the containing module,
# so a file matching this - even with no `app`/`application` variable or
# literal `Flask(...)` call visible at module level - is still a valid
# entrypoint, just a weaker signal than the two above.
FACTORY_PATTERN = re.compile(r'^def\s+(?:create_app|make_app)\s*\(', re.MULTILINE)

IGNORED_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build", "migrations"}
# Conventional entrypoint filenames, most-preferred first. "application.py"
# and "wsgi.py" are common for Flask apps built around an app factory
# (`app = create_app()`) rather than a direct `Flask(...)` call.
PREFERRED_NAMES = {"app.py", "application.py", "main.py", "wsgi.py", "asgi.py", "server.py", "run.py"}
MAX_SCAN_DEPTH = 4


def _read_requirements(path: Path) -> str:
    requirements = path / "requirements.txt"
    if not requirements.exists():
        return ""
    for encoding in ("utf-8", "utf-16"):
        try:
            with open(requirements, "r", encoding=encoding) as f:
                return f.read().lower()
        except UnicodeDecodeError:
            continue
        except Exception:
            return ""
    return ""


def _find_python_entrypoint(root: Path, pattern: "re.Pattern") -> Optional[Tuple[Path, str]]:
    """Search the repo for a file with a module-level instantiation of the
    given framework (e.g. `app = Flask(...)`) and return (file_path,
    variable_name). The pattern is anchored to the start of a line, so an
    assignment indented inside a function body - typically a local
    variable inside an app-factory function, not an importable module
    attribute - is deliberately not matched here."""
    candidates: List[Tuple[Path, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        if len(rel.parts) > MAX_SCAN_DEPTH:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            fp = Path(dirpath) / fn
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            m = pattern.search(text)
            if m:
                candidates.append((fp, m.group(1)))

    if not candidates:
        return None

    def sort_key(item: Tuple[Path, str]):
        fp, _ = item
        rel_parts = fp.relative_to(root).parts
        priority = 0 if fp.name in PREFERRED_NAMES else 1
        return (priority, len(rel_parts))

    candidates.sort(key=sort_key)
    return candidates[0]


def _find_flask_entrypoint(root: Path) -> Optional[Tuple[Path, Optional[str]]]:
    """Flask-specific entrypoint search. Three things count as a valid
    match, checked together in one pass and ranked by how confidently they
    identify a real entrypoint (mirroring Flask's own CLI resolution
    order: explicit app object, then `app`/`application` by convention,
    then an app-factory function):

      1. A module-level `x = Flask(...)` assignment - returns (path, "x").
      2. A module-level `app = ...` / `application = ...` assignment with
         any right-hand side - returns (path, "app") or (path,
         "application"). Covers factory-based files like:
             from myapp import create_app
             app = create_app()
         which never call Flask(...) directly but are still exactly what
         Flask's CLI looks for by default.
      3. A module-level `def create_app(...)` / `def make_app(...)`
         factory function with no `app`/`application` variable in the same
         file - returns (path, None), meaning "just point --app at this
         file and let Flask auto-call the factory".

    Preferred conventional filenames (app.py, application.py, wsgi.py, ...)
    win regardless of which signal matched, since they're the unambiguous,
    well-known convention; among equally-preferred (or equally-unpreferred)
    files, a stronger signal and shallower path win.
    """
    candidates: List[Tuple[Path, Optional[str], int]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        if len(rel.parts) > MAX_SCAN_DEPTH:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            fp = Path(dirpath) / fn
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            m = FLASK_PATTERN.search(text)
            if m:
                candidates.append((fp, m.group(1), 0))
                continue
            m = APP_VAR_PATTERN.search(text)
            if m:
                candidates.append((fp, m.group(1), 1))
                continue
            if FACTORY_PATTERN.search(text):
                candidates.append((fp, None, 2))

    if not candidates:
        return None

    def sort_key(item: Tuple[Path, Optional[str], int]):
        fp, _, kind_priority = item
        rel_parts = fp.relative_to(root).parts
        name_priority = 0 if fp.name in PREFERRED_NAMES else 1
        return (name_priority, kind_priority, len(rel_parts))

    candidates.sort(key=sort_key)
    fp, var, _ = candidates[0]
    return fp, var


class PythonDetector(Detector):
    def detect(self, path: Path) -> Optional[DetectorResult]:
        requirements = path / "requirements.txt"
        has_reqs = requirements.exists()
        has_pyproject = (path / "pyproject.toml").exists()
        has_manage = (path / "manage.py").exists()
        has_main = (path / "main.py").exists()
        has_app = (path / "app.py").exists()

        req_content = _read_requirements(path)

        pyproject_content = ""
        if has_pyproject:
            try:
                pyproject_content = (path / "pyproject.toml").read_text(encoding="utf-8", errors="ignore").lower()
            except Exception:
                pyproject_content = ""

        deps_text = req_content + pyproject_content

        if not any([has_reqs, has_pyproject, has_manage, has_main, has_app]):
            return None

        install_cmd: List[str] = []
        if has_reqs:
            install_cmd = ["pip", "install", "-r", "requirements.txt"]
        elif has_pyproject:
            install_cmd = ["pip", "install", "."]

        # --- Django -------------------------------------------------------
        if has_manage or "django" in deps_text:
            manage_path = path / "manage.py"
            if manage_path.exists():
                return DetectorResult(
                    project_type=ProjectType.PYTHON,
                    framework="Django",
                    package_manager="pip",
                    install_command=install_cmd,
                    run_command=["python", "manage.py", "runserver", "0.0.0.0:0"],
                    confidence=0.85,
                )
            # requirements mention django but no manage.py found at root -
            # look one level down for it (some repos nest the Django project).
            found_manage = next(path.glob("*/manage.py"), None)
            if found_manage:
                rel_dir = str(found_manage.parent.relative_to(path))
                return DetectorResult(
                    project_type=ProjectType.PYTHON,
                    framework="Django",
                    package_manager="pip",
                    install_command=install_cmd,
                    run_command=["python", "manage.py", "runserver", "0.0.0.0:0"],
                    working_dir=rel_dir,
                    confidence=0.85,
                )

        # --- FastAPI --------------------------------------------------------
        if "fastapi" in deps_text or "uvicorn" in deps_text:
            found = _find_python_entrypoint(path, FASTAPI_PATTERN)
            if found:
                fp, var = found
                module_name = fp.stem
                app_ref = f"{module_name}:{var}"
                working_dir = str(fp.parent.relative_to(path))
                return DetectorResult(
                    project_type=ProjectType.PYTHON,
                    framework="FastAPI",
                    package_manager="pip",
                    install_command=install_cmd,
                    run_command=["uvicorn", app_ref, "--host", "0.0.0.0", "--port", "0"],
                    working_dir=working_dir if working_dir != "." else None,
                    confidence=0.9,
                )
            # No FastAPI() found via scan, but the dependency is declared and
            # a conventional entrypoint exists - guess main:app / app:app.
            if has_main:
                return DetectorResult(
                    project_type=ProjectType.PYTHON, framework="FastAPI", package_manager="pip",
                    install_command=install_cmd,
                    run_command=["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "0"],
                    confidence=0.6,
                )
            if has_app:
                return DetectorResult(
                    project_type=ProjectType.PYTHON, framework="FastAPI", package_manager="pip",
                    install_command=install_cmd,
                    run_command=["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "0"],
                    confidence=0.6,
                )

        # --- Flask ----------------------------------------------------------
        if "flask" in deps_text:
            found = _find_flask_entrypoint(path)
            if found:
                fp, var = found
                rel = fp.relative_to(path).as_posix()
                if var is None:
                    # App-factory file (e.g. `app = create_app()`) with no
                    # module-level Flask(...) call - point --app at the
                    # file itself and let Flask's CLI auto-detect the
                    # `app`/`application` variable or factory function.
                    app_arg = rel
                else:
                    app_arg = rel if var == "app" else f"{rel}:{var}"
                return DetectorResult(
                    project_type=ProjectType.PYTHON,
                    framework="Flask",
                    package_manager="pip",
                    install_command=install_cmd,
                    run_command=["python", "-m", "flask", "--app", app_arg, "run",
                                  "--host", "0.0.0.0", "--port", "0"],
                    confidence=0.9,
                )
            # Fall back to Flask's own auto-discovery, which only works if
            # app.py or wsgi.py exists at the run directory.
            if has_app or (path / "wsgi.py").exists():
                return DetectorResult(
                    project_type=ProjectType.PYTHON, framework="Flask", package_manager="pip",
                    install_command=install_cmd,
                    run_command=["python", "-m", "flask", "run", "--host", "0.0.0.0", "--port", "0"],
                    confidence=0.7,
                )

        # --- Streamlit --------------------------------------------------------
        if "streamlit" in deps_text:
            entry = "app.py" if has_app else ("main.py" if has_main else None)
            if not entry:
                # look for any file that calls streamlit
                for candidate in path.glob("*.py"):
                    try:
                        if "streamlit" in candidate.read_text(encoding="utf-8", errors="ignore").lower():
                            entry = candidate.name
                            break
                    except Exception:
                        continue
            if entry:
                return DetectorResult(
                    project_type=ProjectType.PYTHON, framework="Streamlit", package_manager="pip",
                    install_command=install_cmd,
                    run_command=["streamlit", "run", entry, "--server.port", "0", "--server.headless", "true"],
                    confidence=0.85,
                )

        # --- Generic fallback -------------------------------------------------
        if has_main:
            return DetectorResult(
                project_type=ProjectType.PYTHON, framework="Python", package_manager="pip",
                install_command=install_cmd, run_command=["python", "main.py"], confidence=0.5,
            )
        if has_app:
            return DetectorResult(
                project_type=ProjectType.PYTHON, framework="Python", package_manager="pip",
                install_command=install_cmd, run_command=["python", "app.py"], confidence=0.5,
            )

        return None
