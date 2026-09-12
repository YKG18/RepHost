import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
WORKSPACES_DIR = BASE_DIR / "workspaces"

# Ensure workspaces dir exists
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

# Application settings
DEFAULT_TIMEOUT = 300 # seconds for cloning and building
HEALTH_CHECK_INTERVAL = 2 # seconds
MAX_HEALTH_RETRIES = 30
