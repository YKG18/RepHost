from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel

class ProjectType(str, Enum):
    STATIC = "static"
    NODE = "node"
    PYTHON = "python"
    DOCKER = "docker"
    UNKNOWN = "unknown"

class DetectorResult(BaseModel):
    project_type: ProjectType
    framework: Optional[str] = None
    package_manager: Optional[str] = None
    install_command: Optional[List[str]] = None
    run_command: Optional[List[str]] = None
    expected_ports: List[int] = []
    entrypoint: Optional[str] = None
    confidence: float = 0.0

class RunConfig(BaseModel):
    repository_url: str
    workspace_path: str
    detector_result: DetectorResult
    env_vars: Dict[str, str] = {}
