import pytest
from pathlib import Path
from app.detectors import detect_project, describe_scan
from app.core.models import ProjectType

def test_static_detection(tmp_path: Path):
    (tmp_path / "index.html").touch()
    result = detect_project(tmp_path)
    assert result is not None
    assert result.project_type == ProjectType.STATIC
    assert result.framework == "HTML"

def test_node_detection(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name": "test", "dependencies": {"vite": "1.0"}, "scripts": {"dev": "vite"}}')
    result = detect_project(tmp_path)
    assert result is not None
    assert result.project_type == ProjectType.NODE
    assert result.framework == "Vite"
    assert result.package_manager == "npm"

def test_python_detection(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text('fastapi\nuvicorn\n')
    (tmp_path / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    result = detect_project(tmp_path)
    assert result is not None
    assert result.project_type == ProjectType.PYTHON
    assert result.framework == "FastAPI"
    assert "main:app" in result.run_command


def test_django_detection(tmp_path: Path):
    (tmp_path / "manage.py").write_text("#!/usr/bin/env python\n")
    (tmp_path / "requirements.txt").write_text("django\n")
    result = detect_project(tmp_path)
    assert result is not None
    assert result.project_type == ProjectType.PYTHON
    assert result.framework == "Django"
    assert result.run_command[:2] == ["python", "manage.py"]


def test_flask_custom_entrypoint(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("flask\n")
    (tmp_path / "server.py").write_text("from flask import Flask\napp = Flask(__name__)\n")
    result = detect_project(tmp_path)
    assert result is not None
    assert result.framework == "Flask"
    assert "server.py" in " ".join(result.run_command)


def test_fastapi_custom_variable(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (tmp_path / "api.py").write_text("from fastapi import FastAPI\napplication = FastAPI()\n")
    result = detect_project(tmp_path)
    assert result is not None
    assert result.framework == "FastAPI"
    assert "api:application" in result.run_command


def test_flask_factory_reexport_preferred_over_incidental_match(tmp_path: Path):
    """Regression test for a real-world pattern: an app-factory function
    lives in a package's __init__.py (where the module-level `def
    create_app(...)` is real, but any `Flask(...)` call inside it is
    indented/local to that function), while the actual documented
    entrypoint is a thin `application.py` that just calls the factory:
        application.py:      app = create_app()
        mypkg/__init__.py:    def create_app(): ... app = Flask(__name__) ...
    application.py should win, both because it's a conventional filename
    and because a bare `app = <call>` assignment is a stronger signal than
    an indented Flask() call nested inside someone else's function body.
    """
    (tmp_path / "requirements.txt").write_text("flask\n")
    (tmp_path / "application.py").write_text(
        "from mypkg import create_app\napp = create_app()\n"
    )
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from flask import Flask\n\n"
        "def create_app(test_config=None):\n"
        "    app = Flask(__name__)\n"
        "    return app\n"
    )

    result = detect_project(tmp_path)
    assert result is not None
    assert result.framework == "Flask"
    assert "application.py" in " ".join(result.run_command)
    assert "mypkg" not in " ".join(result.run_command)


def test_flask_factory_only_file_used_when_nothing_else_matches(tmp_path: Path):
    """If the only file with any Flask signal at all is a bare factory
    function (no app/application variable anywhere), it should still be
    picked - Flask's own CLI auto-calls create_app()/make_app()."""
    (tmp_path / "requirements.txt").write_text("flask\n")
    (tmp_path / "server.py").write_text(
        "from flask import Flask\n\n"
        "def create_app():\n"
        "    app = Flask(__name__)\n"
        "    return app\n"
    )

    result = detect_project(tmp_path)
    assert result is not None
    assert result.framework == "Flask"
    assert "server.py" in " ".join(result.run_command)


def test_node_fallback_to_main_field(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name": "x", "main": "server.js"}')
    (tmp_path / "server.js").write_text("console.log('hi')")
    result = detect_project(tmp_path)
    assert result is not None
    assert result.project_type == ProjectType.NODE
    assert result.run_command == ["node", "server.js"]


def test_node_serve_script(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"name": "x", "scripts": {"serve": "vite preview"}, "dependencies": {"vite": "1.0"}}'
    )
    result = detect_project(tmp_path)
    assert result is not None
    assert result.project_type == ProjectType.NODE
    assert result.run_command == ["npm", "run", "serve"]


def test_static_in_subdirectory(tmp_path: Path):
    (tmp_path / "public").mkdir()
    (tmp_path / "public" / "index.html").write_text("<html></html>")
    result = detect_project(tmp_path)
    assert result is not None
    assert result.project_type == ProjectType.STATIC
    assert "public" in " ".join(result.run_command)


def _make_flask_backend(backend_dir: Path):
    backend_dir.mkdir(parents=True)
    (backend_dir / "requirements.txt").write_text("flask\n")
    (backend_dir / "app.py").write_text("from flask import Flask\napp = Flask(__name__)\n")


def _make_react_frontend(frontend_dir: Path):
    frontend_dir.mkdir(parents=True)
    (frontend_dir / "package.json").write_text(
        '{"name": "frontend", "dependencies": {"vite": "1.0"}, "scripts": {"dev": "vite"}}'
    )


def test_monorepo_backend_frontend_split(tmp_path: Path):
    """backend/ + frontend/ monorepo: should run the Flask backend and
    report the frontend as an unstarted secondary service, rather than
    returning None just because nothing matches at the repo root."""
    _make_flask_backend(tmp_path / "backend")
    _make_react_frontend(tmp_path / "frontend")

    result = detect_project(tmp_path)
    assert result is not None
    assert result.project_type == ProjectType.PYTHON
    assert result.framework == "Flask"
    assert result.working_dir == "backend"
    assert result.matched_path == "backend"
    assert len(result.secondary_services) == 1
    assert result.secondary_services[0]["path"] == "frontend"
    assert result.secondary_services[0]["type"] == "node"


def test_monorepo_server_client_split(tmp_path: Path):
    """A differently-named split layout (server/ + client/) should be
    recognized the same way as backend/ + frontend/."""
    _make_flask_backend(tmp_path / "server")
    _make_react_frontend(tmp_path / "client")

    result = detect_project(tmp_path)
    assert result is not None
    assert result.working_dir == "server"
    assert result.secondary_services[0]["path"] == "client"


def test_monorepo_prefers_split_layout_over_weak_root_match(tmp_path: Path):
    """A root-level package.json with no real scripts (e.g. shared lint
    tooling) shouldn't hide a real backend+frontend split underneath it."""
    (tmp_path / "package.json").write_text('{"name": "monorepo-root"}')
    _make_flask_backend(tmp_path / "backend")
    _make_react_frontend(tmp_path / "frontend")

    result = detect_project(tmp_path)
    assert result is not None
    assert result.matched_path == "backend"
    assert result.framework == "Flask"


def test_never_silently_returns_none_for_nested_project(tmp_path: Path):
    """If nothing is detectable at the root and no known split layout
    applies, RepoHost should still recurse one level down and find a
    runnable project rather than giving up."""
    nested = tmp_path / "my-app"
    _make_react_frontend(nested)

    result = detect_project(tmp_path)
    assert result is not None
    assert result.project_type == ProjectType.NODE
    assert result.working_dir == "my-app"
    assert result.matched_path == "my-app"


def test_describe_scan_reports_context_on_total_failure(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "notes.txt").write_text("nothing runnable here")

    assert detect_project(tmp_path) is None
    lines = describe_scan(tmp_path)
    assert any("docs" in line for line in lines)
