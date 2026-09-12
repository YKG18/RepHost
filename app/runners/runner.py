import os
import subprocess
from typing import Optional
from pathlib import Path
from app.core.models import RunConfig, ProjectType
from app.sandbox.dockerfile_generator import DockerfileGenerator

class Runner:
    @staticmethod
    def install_dependencies(config: RunConfig) -> bool:
        """
        Generates a Dockerfile (if none exists) and builds the Docker image.
        If the repo already ships a Dockerfile, we use it as-is rather than
        overwriting the author's setup with our generated one.
        """
        workspace = Path(config.workspace_path)
        project_name = f"repohost-{workspace.name.lower()}"
        
        dockerfile_path = workspace / "Dockerfile"
        
        if dockerfile_path.exists():
            print("Using repository's own Dockerfile.")
            # Ensure the existing Dockerfile exposes at least one port so
            # Docker -P has something to map.  If EXPOSE is missing we
            # append common ports.
            content = dockerfile_path.read_text(encoding="utf-8", errors="ignore")
            if "EXPOSE" not in content.upper():
                with open(dockerfile_path, "a", encoding="utf-8") as f:
                    f.write("\nEXPOSE 3000 5000 8000 8080\n")
        else:
            # Generate our own Dockerfile
            try:
                dockerfile_content = DockerfileGenerator.generate(workspace, config.detector_result)
                dockerfile_path.write_text(dockerfile_content, encoding="utf-8")
            except Exception as e:
                print(f"[-] Failed to generate Dockerfile: {e}")
                return False
            
        print("Building Docker image (this may take a few minutes)...")
        try:
            # Build Docker Image
            # We do NOT capture output. We let it stream natively to stdout so the user
            # can see long-running installations (like npm install) and we avoid
            # UnicodeDecodeErrors crashing the Python reader thread on Windows cp1252.
            result = subprocess.run(
                ["docker", "build", "-t", project_name, "."],
                cwd=workspace
            )
            
            if result.returncode != 0:
                print("[-] Docker build failed.")
                return False
                
            # Save the image name in the config for the ProcessManager to use
            config.docker_image = project_name
            print(f"[+] Docker image {project_name} built successfully.")
            return True
            
        except FileNotFoundError:
            print("[-] Docker is not installed or not in PATH.")
            return False
        except Exception as e:
            print(f"[-] Error during Docker build: {e}")
            return False
