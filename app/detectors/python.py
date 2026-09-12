import os
import re
import sys
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType
from app.detectors.api_inspector import ApiInspector


class PythonDetector(Detector):

    def detect(self, path: Path) -> Optional[DetectorResult]:
        requirements = path / "requirements.txt"
        pipfile = path / "Pipfile"
        pyproject = path / "pyproject.toml"
        setup_py = path / "setup.py"

        has_reqs = requirements.exists()
        has_pipfile = pipfile.exists()
        has_pyproject = pyproject.exists()
        has_setup = setup_py.exists()
        
        has_main = (path / "main.py").exists()
        has_app = (path / "app.py").exists()
        has_application = (path / "application.py").exists()
        has_manage = (path / "manage.py").exists()
        has_wsgi = (path / "wsgi.py").exists()
        has_run = (path / "run.py").exists()
        has_server = (path / "server.py").exists()

        if not any([has_reqs, has_pipfile, has_pyproject, has_setup, has_main, has_app, has_application, has_manage, has_wsgi, has_run, has_server]):
            # No obvious root markers — deep-scan for Python files with known framework imports
            return self._deep_scan(path)

        # ── Aggregate requirements content from all manifest files ──
        req_content = ""
        if has_reqs:
            req_content += " " + self._read_file_safe(requirements).lower()
        # Check requirements/ dir if it exists
        reqs_dir = path / "requirements"
        if reqs_dir.is_dir():
            for req_f in reqs_dir.glob("*.txt"):
                req_content += " " + self._read_file_safe(req_f).lower()
        if has_pipfile:
            req_content += " " + self._read_file_safe(pipfile).lower()
        if has_pyproject:
            req_content += " " + self._read_file_safe(pyproject).lower()
        if has_setup:
            req_content += " " + self._read_file_safe(setup_py).lower()

        # ── Read dotenv files (.flaskenv, .env) for env vars ────────
        env_vars: Dict[str, str] = {}
        for env_file in [".flaskenv", ".env", ".env.example"]:
            env_path = path / env_file
            if env_path.exists():
                parsed = self._parse_dotenv(env_path)
                # Don't overwrite actual values with examples
                for k, v in parsed.items():
                    if k not in env_vars:
                        env_vars[k] = v

        # ── Determine install command ───────────────────────────────
        install_cmd = []
        if has_reqs:
            install_cmd = ["pip", "install", "-r", "requirements.txt"]
        elif reqs_dir.is_dir() and any(reqs_dir.glob("*.txt")):
            txt_files = list(reqs_dir.glob("*.txt"))
            # Prefer dev.txt, prod.txt, base.txt, or first found
            chosen = next((f for f in txt_files if f.stem in ("dev", "prod", "base", "common")), txt_files[0])
            install_cmd = ["pip", "install", "-r", f"requirements/{chosen.name}"]
        elif has_pipfile:
            install_cmd = ["pip", "install", "-r", "requirements.txt"] # Runner handles pipenv
        elif has_pyproject or has_setup:
            install_cmd = ["pip", "install", "."]

        # ── Determine framework and run command ─────────────────────
        framework, run_cmd, expected_ports = self._detect_framework(
            path, req_content, env_vars,
            has_main=has_main, has_app=has_app,
            has_application=has_application,
            has_manage=has_manage, has_wsgi=has_wsgi,
            has_run=has_run, has_server=has_server
        )

        if not run_cmd:
            return None

        # If no manifest provided install command, infer required dependencies from source
        if not install_cmd:
            inferred = self._infer_dependencies(path, framework)
            if inferred:
                install_cmd = ["pip", "install"] + inferred

        # Inspect API endpoints and docs
        is_api, docs_url, api_endpoints = ApiInspector.inspect(path, framework)

        # Set default Python environment variables
        env_vars.setdefault("PYTHONUNBUFFERED", "1")
        if framework == "Flask":
            flask_port = str(expected_ports[0]) if expected_ports else "5000"
            env_vars.setdefault("FLASK_RUN_HOST", "0.0.0.0")
            env_vars.setdefault("FLASK_RUN_PORT", flask_port)

        return DetectorResult(
            project_type=ProjectType.PYTHON,
            framework=framework,
            package_manager="pip",
            install_command=install_cmd,
            run_command=run_cmd,
            expected_ports=expected_ports,
            env_vars=env_vars,
            confidence=0.85,
            is_backend_api=is_api,
            docs_url=docs_url,
            api_endpoints=api_endpoints
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
        has_application: bool,
        has_manage: bool,
        has_wsgi: bool,
        has_run: bool,
        has_server: bool
    ) -> Tuple[str, Optional[list], List[int]]:
        """Return (framework_name, run_command, expected_ports) based on project contents."""

        # 1. Django
        if has_manage or "django" in req_content:
            return "Django", ["python", "manage.py", "runserver", "0.0.0.0:8000"], [8000]

        # 2. FastAPI / Uvicorn
        if "fastapi" in req_content or "uvicorn" in req_content:
            entrypoint = PythonDetector._find_fastapi_entrypoint(path, has_main, has_app, has_server)
            if entrypoint:
                return "FastAPI", [
                    "python", "-m", "uvicorn", entrypoint,
                    "--host", "0.0.0.0", "--port", "8000",
                ], [8000]

        # 3. Streamlit
        if "streamlit" in req_content:
            entry = "app.py" if has_app else PythonDetector._find_streamlit_entry(path)
            if entry:
                return "Streamlit", [
                    "streamlit", "run", entry,
                    "--server.port", "8501",
                    "--server.headless", "true",
                    "--server.address", "0.0.0.0"
                ], [8501]

        # 4. Flask
        # Check if flask is explicitly in requirements or if files import Flask
        flask_detected = "flask" in req_content
        if not flask_detected:
            for check_file in ["app.py", "application.py", "main.py", "run.py", "server.py", "wsgi.py"]:
                p = path / check_file
                if p.exists() and ("Flask(" in PythonDetector._read_file_safe(p) or "create_app(" in PythonDetector._read_file_safe(p)):
                    flask_detected = True
                    break

        if flask_detected:
            flask_app = env_vars.get("FLASK_APP")
            if not flask_app:
                flask_app = PythonDetector._find_flask_app(
                    path, has_app=has_app, has_application=has_application,
                    has_run=has_run, has_server=has_server, has_main=has_main, has_wsgi=has_wsgi
                )

            flask_port = env_vars.get("FLASK_RUN_PORT", "5000")
            try:
                f_port = int(flask_port)
            except ValueError:
                f_port = 5000

            expected_ports = [f_port]
            if 5000 not in expected_ports:
                expected_ports.append(5000)
            if 8000 not in expected_ports:
                expected_ports.append(8000)

            if flask_app:
                cmd = ["python", "-m", "flask", "--app", flask_app, "run", "--host", "0.0.0.0", "--port", str(f_port)]
            else:
                cmd = ["python", "-m", "flask", "run", "--host", "0.0.0.0", "--port", str(f_port)]
                
            return "Flask", cmd, expected_ports

        # 5. Sanic
        if "sanic" in req_content:
            entry = "main:app" if has_main else ("app:app" if has_app else "server:app")
            return "Sanic", ["sanic", entry, "--host", "0.0.0.0", "--port", "8000"], [8000]

        # 6. Tornado
        if "tornado" in req_content:
            entry = "main.py" if has_main else ("app.py" if has_app else "server.py")
            return "Tornado", ["python", entry], [8888, 8000]

        # 7. Generic Python web or script
        if has_application:
            return "Python", ["python", "application.py"], [8000, 5000]
        if has_main:
            return "Python", ["python", "main.py"], [8000, 5000]
        if has_app:
            return "Python", ["python", "app.py"], [8000, 5000]
        if has_server:
            return "Python", ["python", "server.py"], [8000, 5000]
        if has_run:
            return "Python", ["python", "run.py"], [8000, 5000]
        if has_wsgi:
            return "Python", ["python", "wsgi.py"], [8000, 5000]

        return "Python", None, []

    @staticmethod
    def _find_fastapi_entrypoint(path: Path, has_main: bool, has_app: bool, has_server: bool = False) -> Optional[str]:
        """Find the module:variable string for uvicorn."""
        candidates = []
        if has_main:
            candidates.append(("main", path / "main.py"))
        if has_app:
            candidates.append(("app", path / "app.py"))
        if has_server:
            candidates.append(("server", path / "server.py"))

        for name in ["api", "service", "entrypoint"]:
            p = path / f"{name}.py"
            if p.exists():
                candidates.append((name, p))

        # Check src/ and app/ subdirectories for main.py, app.py
        for sub in ["src", "app", "api"]:
            sub_dir = path / sub
            if sub_dir.is_dir():
                for sub_name in ["main", "app", "server", "api"]:
                    p = sub_dir / f"{sub_name}.py"
                    if p.exists():
                        candidates.append((f"{sub}.{sub_name}", p))

        for module, filepath in candidates:
            content = PythonDetector._read_file_safe(filepath)
            if "FastAPI" in content or "fastapi" in content.lower():
                match = re.search(r"(\w+)\s*=\s*FastAPI\(", content)
                var = match.group(1) if match else "app"
                return f"{module}:{var}"

        if has_main:
            return "main:app"
        if has_app:
            return "app:app"
        if candidates:
            return f"{candidates[0][0]}:app"
        return None

    @staticmethod
    def _find_flask_app(
        path: Path,
        has_app: bool = False,
        has_application: bool = False,
        has_run: bool = False,
        has_server: bool = False,
        has_main: bool = False,
        has_wsgi: bool = False,
    ) -> Optional[str]:
        """
        Determine the Flask module / variable target for `flask --app <target> run`.
        Handles:
          - application.py (AWS Elastic Beanstalk standard: application = Flask(...) or app)
          - app.py (standard Flask: app = Flask(...) or create_app)
          - wsgi.py, run.py, server.py, main.py
          - Package application factory pattern (e.g. flaskr/__init__.py, app/__init__.py)
          - Subdirectory apps (src/app.py, backend/app.py)
        """
        # 1. Check application.py (very common in Flask)
        if has_application:
            content = PythonDetector._read_file_safe(path / "application.py")
            if "Flask(" in content or "create_app(" in content:
                match = re.search(r"(\w+)\s*=\s*Flask\(", content)
                var = match.group(1) if match else "application"
                return f"application:{var}"
            return "application"

        # 2. Check app.py
        if has_app:
            content = PythonDetector._read_file_safe(path / "app.py")
            if "Flask(" in content or "create_app" in content:
                match = re.search(r"(\w+)\s*=\s*Flask\(", content)
                var = match.group(1) if match else "app"
                return f"app:{var}"
            return "app"

        # 3. Check wsgi.py, run.py, server.py, main.py in root
        root_candidates = [
            ("run", has_run),
            ("server", has_server),
            ("main", has_main),
            ("wsgi", has_wsgi),
        ]
        for mod_name, exists in root_candidates:
            if exists:
                p = path / f"{mod_name}.py"
                content = PythonDetector._read_file_safe(p)
                if "Flask(" in content or "create_app" in content:
                    match = re.search(r"(\w+)\s*=\s*Flask\(", content)
                    var = match.group(1) if match else "app"
                    return f"{mod_name}:{var}"

        # 4. Check subdirectories for package application factories (e.g. flaskr/, app/, src/)
        for child in path.iterdir():
            if child.is_dir() and not child.name.startswith((".", "_", "test", "venv")):
                init_file = child / "__init__.py"
                if init_file.exists():
                    content = PythonDetector._read_file_safe(init_file)
                    if "create_app" in content:
                        return f"{child.name}:create_app()"
                    if "Flask(" in content:
                        match = re.search(r"(\w+)\s*=\s*Flask\(", content)
                        var = match.group(1) if match else "app"
                        return f"{child.name}:{var}"

                # Also check child/app.py
                child_app = child / "app.py"
                if child_app.exists():
                    content = PythonDetector._read_file_safe(child_app)
                    if "Flask(" in content or "create_app" in content:
                        match = re.search(r"(\w+)\s*=\s*Flask\(", content)
                        var = match.group(1) if match else "app"
                        return f"{child.name}.app:{var}"

        # 5. Deep scan for any file initializing Flask
        for p in path.rglob("*.py"):
            parts = p.relative_to(path).parts
            if any(part.startswith((".", "_")) or part in ("node_modules", "tests", "test", "venv", ".venv") for part in parts):
                continue
            content = PythonDetector._read_file_safe(p)
            if "Flask(" in content:
                match = re.search(r"(\w+)\s*=\s*Flask\(", content)
                var = match.group(1) if match else "app"
                mod_path = ".".join(parts).removesuffix(".py")
                return f"{mod_path}:{var}"

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
        for enc in ("utf-8", "utf-16", "latin-1"):
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

        framework_imports = {
            "streamlit": "Streamlit",
            "flask": "Flask",
            "fastapi": "FastAPI",
            "django": "Django",
            "sanic": "Sanic",
            "tornado": "Tornado"
        }

        # Collect .py files (skip hidden dirs and __pycache__)
        py_files = []
        for p in path.rglob("*.py"):
            parts = p.relative_to(path).parts
            if any(part.startswith(".") or part in ("__pycache__", "venv", ".venv", "tests", "test") for part in parts):
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

        # 1. Check if an existing requirements.txt exists anywhere in the project tree
        found_reqs = [r for r in path.rglob("requirements.txt") if not any(p in ("venv", ".venv", "scratch", "node_modules", "__pycache__") for p in r.parts)]
        if found_reqs:
            req_rel = str(found_reqs[0].relative_to(path)).replace("\\", "/")
            install_cmd = ["pip", "install", "-r", req_rel]
        else:
            inferred = self._infer_dependencies(path, found_framework)
            install_cmd = ["pip", "install"] + inferred if inferred else []

        expected_ports = []
        if found_framework == "Streamlit":
            run_cmd = ["streamlit", "run", rel, "--server.port", "8501", "--server.headless", "true", "--server.address", "0.0.0.0"]
            expected_ports = [8501]
        elif found_framework == "Flask":
            flask_app = self._find_flask_app(path) or rel.replace("/", ".").removesuffix(".py")
            run_cmd = ["python", "-m", "flask", "--app", flask_app, "run", "--host", "0.0.0.0", "--port", "5000"]
            expected_ports = [5000, 8000]
        elif found_framework == "FastAPI":
            module = rel.replace("/", ".").removesuffix(".py")
            run_cmd = ["python", "-m", "uvicorn", f"{module}:app", "--host", "0.0.0.0", "--port", "8000"]
            expected_ports = [8000]
        else:
            run_cmd = ["python", rel]
            expected_ports = [8000, 5000]

        is_api, docs_url, api_endpoints = ApiInspector.inspect(path, found_framework)

        return DetectorResult(
            project_type=ProjectType.PYTHON,
            framework=found_framework,
            package_manager="pip",
            install_command=install_cmd,
            run_command=run_cmd,
            expected_ports=expected_ports,
            confidence=0.6,
            is_backend_api=is_api,
            docs_url=docs_url,
            api_endpoints=api_endpoints
        )

    @staticmethod
    def _infer_dependencies(path: Path, framework: str = "") -> List[str]:
        """
        Extract third-party package dependencies by scanning Python imports
        when no manifest (requirements.txt, Pipfile, etc.) exists.
        """
        import ast
        stdlib = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else {
            "os", "sys", "re", "json", "time", "datetime", "math", "random", "typing",
            "pathlib", "logging", "shutil", "tempfile", "subprocess", "hashlib", "io",
            "collections", "itertools", "functools", "unittest", "urllib", "http", "email",
            "sqlite3", "csv", "xml", "html", "socket", "select", "threading", "multiprocessing",
            "asyncio", "copy", "pickle", "traceback", "gc", "stat", "struct", "queue", "uuid",
            "atexit", "abc", "contextlib", "inspect", "enum", "dataclasses", "typing_extensions"
        }

        py_files = []
        for p in path.rglob("*.py"):
            parts = p.relative_to(path).parts
            if any(part.startswith((".", "_")) or part in ("__pycache__", "venv", ".venv", "scratch", "node_modules", "tests", "test") for part in parts):
                continue
            py_files.append(p)

        if not py_files:
            deps = []
            if framework == "Django":
                deps.append("django")
            elif framework == "Flask":
                deps.append("flask")
            elif framework == "FastAPI":
                deps.extend(["fastapi", "uvicorn[standard]"])
            elif framework == "Streamlit":
                deps.append("streamlit")
            return deps

        all_imports = set()
        has_image_field = False

        for py_file in py_files:
            content = PythonDetector._read_file_safe(py_file)
            if "ImageField" in content:
                has_image_field = True
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for name in node.names:
                            if name.name:
                                all_imports.add(name.name.split(".")[0].strip())
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            all_imports.add(node.module.split(".")[0].strip())
            except Exception:
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("import "):
                        parts = line.split()
                        if len(parts) > 1:
                            all_imports.add(parts[1].split(".")[0].strip())
                    elif line.startswith("from ") and " import " in line:
                        parts = line.split()
                        if len(parts) > 1:
                            all_imports.add(parts[1].split(".")[0].strip())

        # Gather local module / directory names to exclude local packages
        local_names = {p.stem.lower() for p in py_files}
        for child in path.rglob("*"):
            if child.is_dir():
                local_names.add(child.name.lower())
        local_names.update({
            "tests", "test", "migrations", "static", "templates", "media", "views",
            "models", "forms", "admin", "apps", "urls", "routes", "controllers",
            "services", "utils", "config", "core", "application", "app", "main",
            "seed", "extensions", "database", "db", "templatetags", "flaskr"
        })

        raw_third_party = [
            pkg for pkg in sorted(all_imports - stdlib - {"__future__", ""})
            if pkg.lower() not in local_names and not pkg.startswith(("_", "."))
        ]

        # PyPI name mapping for packages where import name != pip install name
        pypi_map = {
            "PIL": "Pillow",
            "bs4": "beautifulsoup4",
            "sklearn": "scikit-learn",
            "yaml": "PyYAML",
            "cv2": "opencv-python",
            "dotenv": "python-dotenv",
            "mptt": "django-mptt",
            "rest_framework": "djangorestframework",
            "corsheaders": "django-cors-headers",
            "crispy_forms": "django-crispy-forms",
            "allauth": "django-allauth",
            "taggit": "django-taggit",
            "django_filters": "django-filter",
            "shortuuid": "shortuuid",
            "jwt": "PyJWT",
            "sqlalchemy": "SQLAlchemy",
            "psycopg2": "psycopg2-binary",
            "mysql": "mysqlclient",
            "marshmallow": "marshmallow",
        }

        deps = set()
        if framework == "Django":
            deps.add("django")
        elif framework == "Flask":
            deps.add("flask")
        elif framework == "FastAPI":
            deps.add("fastapi")
            deps.add("uvicorn[standard]")
        elif framework == "Streamlit":
            deps.add("streamlit")

        for pkg in raw_third_party:
            if pkg.lower() in local_names:
                continue
            deps.add(pypi_map.get(pkg, pkg))

        if has_image_field:
            deps.add("Pillow")

        return sorted([d for d in deps if d])
