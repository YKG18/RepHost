import pytest
from pathlib import Path
from app.detectors import detect_project
from app.core.models import ProjectType

def test_static_detection(tmp_path: Path):
    (tmp_path / "index.html").touch()
    results = detect_project(tmp_path)
    assert len(results) == 1
    assert results[0].project_type == ProjectType.STATIC
    assert results[0].framework == "HTML"

def test_node_detection(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name": "test", "dependencies": {"vite": "1.0"}, "scripts": {"dev": "vite"}}')
    results = detect_project(tmp_path)
    assert len(results) == 1
    assert results[0].project_type == ProjectType.NODE
    assert results[0].framework == "Vite"
    assert results[0].package_manager == "npm"

def test_python_detection(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text('fastapi\nuvicorn\n')
    (tmp_path / "main.py").touch()
    results = detect_project(tmp_path)
    assert len(results) == 1
    assert results[0].project_type == ProjectType.PYTHON
    assert results[0].framework == "FastAPI"
    assert "uvicorn" in results[0].run_command

def test_compose_detection(tmp_path: Path):
    (tmp_path / "docker-compose.yml").write_text('version: "3"\nservices:\n  web:\n    image: nginx\n')
    results = detect_project(tmp_path)
    assert len(results) == 1
    assert results[0].project_type == ProjectType.DOCKER_COMPOSE
    assert results[0].framework == "Docker Compose"
