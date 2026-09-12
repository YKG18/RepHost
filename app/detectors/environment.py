import re
from pathlib import Path
from typing import Dict

def detect_environment_variables(workspace: Path) -> Dict[str, str]:
    """
    Scans the workspace for common environment variable templates
    and extracts the required keys.
    """
    env_vars = {}
    candidate_files = [
        ".env.example",
        ".env.sample",
        ".env.template",
        ".env.dev"
    ]
    
    for candidate in candidate_files:
        env_path = workspace / candidate
        if env_path.exists() and env_path.is_file():
            try:
                content = env_path.read_text(encoding="utf-8")
                # Simple parsing of KEY=VALUE or just KEY
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    
                    # Try to extract the key (everything before first =)
                    if "=" in line:
                        key = line.split("=", 1)[0].strip()
                        val = line.split("=", 1)[1].strip()
                        if key:
                            env_vars[key] = val
                    else:
                        # Sometimes it's just the key name exported
                        key = line.split()[0].strip()
                        if key:
                            env_vars[key] = ""
                            
            except Exception:
                continue
                
    return env_vars
