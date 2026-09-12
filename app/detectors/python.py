from pathlib import Path
from typing import Optional
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType

class PythonDetector(Detector):
    def detect(self, path: Path) -> Optional[DetectorResult]:
        requirements = path / "requirements.txt"
        
        has_reqs = requirements.exists()
        has_pyproject = (path / "pyproject.toml").exists()
        has_main = (path / "main.py").exists()
        has_app = (path / "app.py").exists()
        
        if not any([has_reqs, has_pyproject, has_main, has_app]):
            return None
            
        install_cmd = []
        if has_reqs:
            install_cmd = ["pip", "install", "-r", "requirements.txt"]
            
        run_cmd = None
        framework = "Python"
        
        req_content = ""
        if has_reqs:
            with open(requirements, 'r', encoding='utf-8') as f:
                req_content = f.read().lower()
                
        if "fastapi" in req_content or "uvicorn" in req_content:
            framework = "FastAPI"
            if has_main:
                run_cmd = ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "0"]
        elif "flask" in req_content:
            framework = "Flask"
            run_cmd = ["python", "-m", "flask", "run"]
        elif "streamlit" in req_content:
            framework = "Streamlit"
            run_cmd = ["streamlit", "run", "app.py"]
            
        if not run_cmd:
            if has_main:
                run_cmd = ["python", "main.py"]
            elif has_app:
                run_cmd = ["python", "app.py"]
            else:
                return None
                
        return DetectorResult(
            project_type=ProjectType.PYTHON,
            framework=framework,
            package_manager="pip",
            install_command=install_cmd,
            run_command=run_cmd,
            confidence=0.8
        )
