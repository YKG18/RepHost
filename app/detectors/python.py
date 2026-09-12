from pathlib import Path
from typing import Optional, Dict, Tuple
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType


class PythonDetector(Detector):

    def detect(self, path: Path) -> Optional[DetectorResult]:
        requirements = path / "requirements.txt"
        pipfile = path / "Pipfile"

        has_reqs = requirements.exists()
        has_pipfile = pipfile.exists()
        has_pyproject = (path / "pyproject.toml").exists()
        has_main = (path / "main.py").exists()
        has_app = (path / "app.py").exists()
        has_manage = (path / "manage.py").exists()
        has_wsgi = (path / "wsgi.py").exists()

        if not any([has_reqs, has_pipfile, has_pyproject, has_main, has_app]):
            # No obvious root markers — deep-scan for Python files with
            # known framework imports before giving up
            return self._deep_scan(path)

        # ── Read requirements content ───────────────────────────────
        req_content = self._read_file_safe(requirements) if has_reqs else ""

        # ── Read dotenv files (.flaskenv, .env) for env vars ────────
        env_vars = {}
        for env_file in [".flaskenv", ".env"]:
            env_path = path / env_file
            if env_path.exists():
                env_vars.update(self._parse_dotenv(env_path))

        # ── Determine install command ───────────────────────────────
        install_cmd = []
        if has_reqs:
            install_cmd = ["pip", "install", "-r", "requirements.txt"]
        elif has_pipfile:
            install_cmd = ["pip", "install", "-r", "requirements.txt"]
            # We'll rely on the runner to handle Pipfile if no requirements.txt

        # ── Determine framework and run command ─────────────────────
        framework, run_cmd = self._detect_framework(
            path, req_content, env_vars,
            has_main=has_main, has_app=has_app,
            has_manage=has_manage, has_wsgi=has_wsgi,
        )

        if not run_cmd:
            return None

        return DetectorResult(
            project_type=ProjectType.PYTHON,
            framework=framework,
            package_manager="pip",
            install_command=install_cmd,
            run_command=run_cmd,
            env_vars=env_vars,
            confidence=0.8,
        )

    # ── Framework detection ─────────────────────────────────────────

    @staticmethod
    def _detect_framework(
        path: Path,
        req_content: str,
        env_vars: Dict[str, str],
        *,
        has_main: bool,
        has_app: bool,
        has_manage: bool,
        has_wsgi: bool,
    ) -> Tuple[str, Optional[list]]:
        """Return (framework_name, run_command) based on project contents."""

        # -- Django --
        if has_manage or "django" in req_content:
            return "Django", ["python", "manage.py", "runserver", "0.0.0.0:0"]

        # -- FastAPI / Uvicorn --
        if "fastapi" in req_content or "uvicorn" in req_content:
            entrypoint = PythonDetector._find_fastapi_entrypoint(path, has_main, has_app)
            if entrypoint:
                return "FastAPI", [
                    "python", "-m", "uvicorn", entrypoint,
                    "--host", "0.0.0.0", "--port", "0",
                ]

        # -- Flask --
        if "flask" in req_content:
            flask_app = env_vars.get("FLASK_APP")
            if not flask_app:
                # Try to find it ourselves
                flask_app = PythonDetector._find_flask_app(path, has_app)
            return "Flask", ["python", "-m", "flask", "run", "--host", "0.0.0.0", "--port", "0"]

        # -- Streamlit --
        if "streamlit" in req_content:
            entry = "app.py" if has_app else PythonDetector._find_streamlit_entry(path)
            if entry:
                return "Streamlit", ["streamlit", "run", entry, "--server.port", "0"]

        # -- Generic Python --
        if has_main:
            return "Python", ["python", "main.py"]
        if has_app:
            return "Python", ["python", "app.py"]
        if has_wsgi:
            return "Python", ["python", "wsgi.py"]

        return "Python", None

    @staticmethod
    def _find_fastapi_entrypoint(path: Path, has_main: bool, has_app: bool) -> Optional[str]:
        """Find the module:variable string for uvicorn."""
        # Check common files for a FastAPI() instance
        candidates = []
        if has_main:
            candidates.append(("main", path / "main.py"))
        if has_app:
            candidates.append(("app", path / "app.py"))

        # Also check for server.py, api.py
        for name in ["server", "api"]:
            p = path / f"{name}.py"
            if p.exists():
                candidates.append((name, p))

        for module, filepath in candidates:
            content = PythonDetector._read_file_safe(filepath)
            if "FastAPI" in content or "fastapi" in content.lower():
                # Look for the variable name (usually `app`)
                import re
                match = re.search(r"(\w+)\s*=\s*FastAPI\(", content)
                var = match.group(1) if match else "app"
                return f"{module}:{var}"

        # Default fallbacks
        if has_main:
            return "main:app"
        if has_app:
            return "app:app"
        return None

    @staticmethod
    def _find_flask_app(path: Path, has_app: bool) -> Optional[str]:
        """Try to find what module contains the Flask app."""
        if has_app:
            return "app"
        # Check for common patterns
        for name in ["wsgi", "server", "run"]:
            if (path / f"{name}.py").exists():
                return name
        # Check subdirectories for __init__.py with Flask
        for child in path.iterdir():
            if child.is_dir() and (child / "__init__.py").exists():
                content = PythonDetector._read_file_safe(child / "__init__.py")
                if "Flask" in content:
                    return child.name
        return None

    @staticmethod
    def _find_streamlit_entry(path: Path) -> Optional[str]:
        """Find the most likely Streamlit entry file."""
        for name in ["app.py", "main.py", "streamlit_app.py", "Home.py"]:
            if (path / name).exists():
                return name
        return None

    # ── Utility ─────────────────────────────────────────────────────

    @staticmethod
    def _read_file_safe(filepath: Path) -> str:
        """Read a text file, trying utf-8 then utf-16, returning '' on failure."""
        for enc in ("utf-8", "utf-16"):
            try:
                return filepath.read_text(encoding=enc)
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception:
                return ""
        return ""

    @staticmethod
    def _parse_dotenv(filepath: Path) -> Dict[str, str]:
        """Parse a simple .env / .flaskenv file into a dict."""
        result = {}
        content = PythonDetector._read_file_safe(filepath)
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                result[key] = value
        return result

    def _deep_scan(self, path: Path) -> Optional[DetectorResult]:
        """Scan all .py files in the repo looking for known framework imports.
        Used as a last resort when no root-level markers exist."""
        import re as _re
        import sys as _sys

        framework_imports = {
            "streamlit": "Streamlit",
            "flask": "Flask",
            "fastapi": "FastAPI",
            "django": "Django",
        }

        # Collect .py files (skip hidden dirs and __pycache__)
        py_files = []
        for p in path.rglob("*.py"):
            parts = p.relative_to(path).parts
            if any(part.startswith(".") or part == "__pycache__" for part in parts):
                continue
            py_files.append(p)

        if not py_files:
            return None

        # Scan for framework imports
        found_framework = None
        found_file = None
        for py_file in py_files:
            content = self._read_file_safe(py_file)
            for imp, fw_name in framework_imports.items():
                if f"import {imp}" in content or f"from {imp}" in content:
                    found_framework = fw_name
                    found_file = py_file
                    break
            if found_framework:
                break

        if not found_framework or not found_file:
            return None

        rel = str(found_file.relative_to(path)).replace("\\", "/")

        # Collect third-party imports to auto-generate install list
        all_imports = set()
        for py_file in py_files:
            content = self._read_file_safe(py_file)
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("import "):
                    mod = line.split()[1].split(".")[0]
                    all_imports.add(mod)
                elif line.startswith("from ") and " import " in line:
                    mod = line.split()[1].split(".")[0]
                    all_imports.add(mod)

        stdlib = set(_sys.stdlib_module_names) if hasattr(_sys, "stdlib_module_names") else set()
        raw_third_party = sorted(all_imports - stdlib - {"__future__"})
        
        # Map common import names to actual PyPI package names
        pypi_map = {
            "PIL": "Pillow",
            "bs4": "beautifulsoup4",
            "sklearn": "scikit-learn",
            "yaml": "PyYAML",
            "cv2": "opencv-python",
            "dotenv": "python-dotenv",
        }
        
        third_party = [pypi_map.get(pkg, pkg) for pkg in raw_third_party]
        install_cmd = ["pip", "install"] + third_party if third_party else []

        if found_framework == "Streamlit":
            run_cmd = ["streamlit", "run", rel, "--server.port", "0", "--server.headless", "true"]
        elif found_framework == "Flask":
            run_cmd = ["python", rel]
        elif found_framework == "FastAPI":
            module = rel.replace("/", ".").replace(".py", "")
            run_cmd = ["python", "-m", "uvicorn", f"{module}:app", "--host", "0.0.0.0", "--port", "0"]
        else:
            run_cmd = ["python", rel]

        return DetectorResult(
            project_type=ProjectType.PYTHON,
            framework=found_framework,
            package_manager="pip",
            install_command=install_cmd,
            run_command=run_cmd,
            confidence=0.5,
        )
