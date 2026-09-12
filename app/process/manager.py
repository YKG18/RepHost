import os
import subprocess
import time
import re
from typing import Optional, List
from pathlib import Path
from app.core.models import RunConfig, ProjectType

class MissingDependencyError(Exception):
    def __init__(self, packages: List[str]):
        self.packages = packages
        super().__init__(f"Missing dependencies: {packages}")


class ProcessManager:
    def __init__(self, config: RunConfig):
        self.config = config
        self.container_name: Optional[str] = None
        self.detected_ports: List[int] = []

    def start(self) -> bool:
        if not self.config.docker_image:
            print("No Docker image found in config.")
            return False
            
        self.container_name = f"repohost-run-{int(time.time())}"
        
        # Build env var string. Inject HOST=0.0.0.0 to ensure servers 
        # (like Vite, Flask, FastAPI) bind to all interfaces instead of 127.0.0.1.
        env_args = ["-e", "HOST=0.0.0.0"]
        for k, v in self.config.env_vars.items():
            env_args.extend(["-e", f"{k}={v}"])
            
        # Start container detached, mapping all exposed ports to random host ports (-P)
        cmd = [
            "docker", "run", "-d", 
            "--name", self.container_name,
            "-P"
        ] + env_args + [self.config.docker_image]
        
        print(f"Starting Docker container {self.container_name}...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to start Docker container: {e.stderr}")
            return False

    def get_listening_ports(self, max_wait: int = 30) -> List[int]:
        if not self.container_name:
            return []
            
        print("Detecting listening ports from Docker...")
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            # Check if container is still running
            status_proc = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Status}}", self.container_name],
                capture_output=True, text=True
            )
            
            if status_proc.returncode != 0 or status_proc.stdout.strip() != "running":
                self._dump_output("Docker container exited prematurely")
                return []

            # Get port mappings
            # Output format: 
            # 8000/tcp -> 0.0.0.0:32768
            # 3000/tcp -> 0.0.0.0:32769
            port_proc = subprocess.run(
                ["docker", "port", self.container_name],
                capture_output=True, text=True
            )
            
            ports = set()
            for line in port_proc.stdout.splitlines():
                m = re.search(r"0\.0\.0\.0:(\d+)", line)
                if m:
                    ports.add(int(m.group(1)))
                    
            if ports:
                # To be absolutely sure the app is listening inside, we could check logs,
                # but if docker port returned it, it's mapped.
                # However, docker maps it immediately even if the app hasn't bound it internally yet.
                # The health checker in cli/main.py will wait until it returns HTTP 200.
                self.detected_ports = list(ports)
                return self.detected_ports
                
            time.sleep(1)
            
        self._dump_output("Timed out waiting for a listening port")
        return []

    def _dump_output(self, reason: str):
        if not self.container_name:
            return
            
        print(f"\n  {reason}.")
        log_proc = subprocess.run(
            ["docker", "logs", "--tail", "50", self.container_name],
            capture_output=True, text=True
        )
        
        lines = (log_proc.stdout + log_proc.stderr).splitlines()
        if lines:
            print("  --- Container output ---")
            for line in lines:
                print(f"  {line}")
            print("  --- End of output ---")

    def stop(self):
        if not self.container_name:
            return
            
        print(f"Terminating container {self.container_name}...")
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
