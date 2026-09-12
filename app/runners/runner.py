import subprocess
import os
from pathlib import Path
from app.core.models import RunConfig, ProjectType

class Runner:
    @staticmethod
    def install_dependencies(config: RunConfig) -> bool:
        if not config.detector_result.install_command:
            return True
            
        print(f"Installing dependencies using: {' '.join(config.detector_result.install_command)}")
        
        env = os.environ.copy()
        
        if config.detector_result.project_type == ProjectType.PYTHON:
            venv_path = Path(config.workspace_path) / ".venv"
            if not venv_path.exists():
                print("Creating virtual environment...")
                subprocess.run(["python", "-m", "venv", ".venv"], cwd=config.workspace_path, check=True)
            
            install_cmd = config.detector_result.install_command
            if install_cmd[0] == "pip":
                if os.name == "nt":
                    install_cmd[0] = str(venv_path / "Scripts" / "pip")
                else:
                    install_cmd[0] = str(venv_path / "bin" / "pip")
            
            run_cmd = config.detector_result.run_command
            if run_cmd and run_cmd[0] in ["python", "flask", "uvicorn", "streamlit"]:
                if os.name == "nt":
                    run_cmd[0] = str(venv_path / "Scripts" / run_cmd[0])
                else:
                    run_cmd[0] = str(venv_path / "bin" / run_cmd[0])
        
        try:
            subprocess.run(config.detector_result.install_command, cwd=config.workspace_path, check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Installation failed: {e}")
            return False
