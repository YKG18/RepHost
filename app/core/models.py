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
    # Directory (relative to the workspace root) that run_command should be
    # executed from. Defaults to the workspace root when None/".".
    # This lets us run entrypoints that live in a subdirectory (e.g. a
    # FastAPI app at src/main.py) without needing the parent directory to be
    # an importable Python package.
    working_dir: Optional[str] = None
    # Extra environment variables the detector determined are needed to run
    # the app (e.g. FLASK_APP). Merged into RunConfig.env_vars.
    env: Dict[str, str] = {}
    # Set when this result came from scanning a subdirectory rather than the
    # repo root (monorepo / split-service layouts, or a generic one-level
    # recursive fallback). Purely informational - used for CLI reporting.
    matched_path: Optional[str] = None
    # Other runnable-looking services found alongside the one we picked
    # (e.g. a frontend in a backend+frontend monorepo) that we are not
    # starting. Each entry: {"path": ..., "type": ..., "framework": ...}.
    # Purely informational - used for CLI reporting ("bypass non-essential").
    secondary_services: List[Dict[str, str]] = []

class RunConfig(BaseModel):
    repository_url: str
    workspace_path: str
    detector_result: DetectorResult
    env_vars: Dict[str, str] = {}
