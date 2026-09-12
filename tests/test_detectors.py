import pytest
from pathlib import Path
from app.detectors import detect_project
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
    (tmp_path / "main.py").touch()
    result = detect_project(tmp_path)
    assert result is not None
    assert result.project_type == ProjectType.PYTHON
    assert result.framework == "FastAPI"
    assert "uvicorn" in result.run_command
