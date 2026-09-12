from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel

class ProjectType(str, Enum):
    STATIC = "static"
    NODE = "node"
    PYTHON = "python"
    JAVA = "java"
    RUBY = "ruby"
    PHP = "php"
    DOTNET = "dotnet"
    GO = "go"
    RUST = "rust"
    DOCKER = "docker"
    DOCKER_COMPOSE = "docker_compose"
    UNKNOWN = "unknown"

class DetectorResult(BaseModel):
    project_type: ProjectType
    sub_path: str = "."
    framework: Optional[str] = None
    package_manager: Optional[str] = None
    install_command: Optional[List[str]] = None
    run_command: Optional[List[str]] = None
    expected_ports: List[int] = []
    entrypoint: Optional[str] = None
    env_vars: Dict[str, str] = {}
    confidence: float = 0.0
    is_backend_api: bool = False
    api_endpoints: List[str] = []
    docs_url: Optional[str] = None
    # Connection bridge metadata
    expected_backend_port: Optional[int] = None
    uses_env_var_for_api: Optional[str] = None
    proxy_config_detected: bool = False
    source_rewrite_from: Optional[str] = None
    source_rewrite_to: Optional[str] = None

class RunConfig(BaseModel):
    repository_url: str
    workspace_path: str
    detector_result: DetectorResult
    env_vars: Dict[str, str] = {}
    docker_image: Optional[str] = None
    pinned_port: Optional[int] = None
    source_rewrite_from: Optional[str] = None
    source_rewrite_to: Optional[str] = None
