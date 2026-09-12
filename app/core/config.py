import sys
import os
import tempfile
from pathlib import Path

def get_base_path() -> Path:
    """Returns the base project directory, handling both standard and PyInstaller frozen execution."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent

def get_workspaces_dir() -> Path:
    """Returns the writable directory for cloning and building temporary workspaces."""
    if getattr(sys, "frozen", False):
        # When running as an .exe, use a local workspaces folder next to the exe or tempdir
        exe_dir = Path(sys.executable).parent / "workspaces"
        try:
            exe_dir.mkdir(parents=True, exist_ok=True)
            return exe_dir
        except Exception:
            temp_dir = Path(tempfile.gettempdir()) / "repohost_workspaces"
            temp_dir.mkdir(parents=True, exist_ok=True)
            return temp_dir
    ws = get_base_path() / "workspaces"
    ws.mkdir(parents=True, exist_ok=True)
    return ws

BASE_DIR = get_base_path()
WORKSPACES_DIR = get_workspaces_dir()

# Application settings
DEFAULT_TIMEOUT = 300  # seconds for cloning and building
HEALTH_CHECK_INTERVAL = 2  # seconds
MAX_HEALTH_RETRIES = 30

