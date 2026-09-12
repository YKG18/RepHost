import os
import subprocess
import time
import re
import socket
from typing import Optional, List
from pathlib import Path
from app.core.models import RunConfig, ProjectType

# Ensure Docker binaries are available in PATH
for docker_bin in [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin"),
    r"C:\Program Files\Docker\Docker\resources\bin",
]:
    if os.path.exists(docker_bin) and docker_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = docker_bin + os.pathsep + os.environ.get("PATH", "")


def is_port_available(port: int) -> bool:
    """Check whether a host port is currently available on 127.0.0.1."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(("127.0.0.1", port)) != 0
    except Exception:
        return False

class MissingDependencyError(Exception):
    def __init__(self, packages: List[str]):
        self.packages = packages
        super().__init__(f"Missing dependencies: {packages}")


class ProcessManager:
    def __init__(self, config: RunConfig):
        self.config = config
        self.container_name: Optional[str] = None
        self.is_compose = (config.detector_result.project_type == ProjectType.DOCKER_COMPOSE)
        self.detected_ports: List[int] = []
        self.public_url: Optional[str] = None

    def _get_compose_cmd(self) -> List[str]:
        """Detect whether 'docker compose' (v2) or 'docker-compose' (v1) should be used."""
        try:
            res = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
            if res.returncode == 0:
                return ["docker", "compose"]
        except Exception:
            pass
        return ["docker-compose"]

    def start(self) -> bool:
        if self.is_compose:
            print("Starting Docker Compose project...")
            compose_cmd = self._get_compose_cmd()
            
            # Rule 11: Bounded automatic recovery (max 3 attempts for network/registry glitches)
            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                try:
                    subprocess.run(compose_cmd + ["up", "-d", "--build"], cwd=self.config.workspace_path, check=True)
                    # The project name defaults to the basename of the directory
                    self.container_name = Path(self.config.workspace_path).name.lower()
                    return True
                except subprocess.CalledProcessError as e:
                    print(f"\n[!] Docker Compose startup attempt {attempt}/{max_attempts} failed.")
                    if attempt < max_attempts:
                        print("Retrying Docker Compose startup (resuming layer downloads and build)...")
                        time.sleep(3)
                    else:
                        print(f"Failed to start Docker Compose after {max_attempts} attempts: {e}")
                        self._dump_output("Docker Compose startup failure")
                        return False

        if not self.config.docker_image:
            print("No Docker image found in config.")
            return False
            
        self.container_name = f"repohost-run-{int(time.time())}"
        
        # Smart Preferred Port Mapping:
        # Priority 1: If the ConnectionBridge pinned a specific port (because the
        # frontend has hardcoded references to it), map that port explicitly.
        # Priority 2: Check if the framework's expected ports are free on the host.
        port_args = []
        mapped_ports = set()

        # Pinned port from ConnectionBridge takes absolute priority
        if self.config.pinned_port and is_port_available(self.config.pinned_port):
            port_args.extend(["-p", f"{self.config.pinned_port}:{self.config.pinned_port}"])
            mapped_ports.add(self.config.pinned_port)

        # Map the primary expected port directly if free on host and not already mapped
        if not mapped_ports and self.config.detector_result and self.config.detector_result.expected_ports:
            for exp_port in self.config.detector_result.expected_ports:
                if is_port_available(exp_port):
                    port_args.extend(["-p", f"{exp_port}:{exp_port}"])
                    mapped_ports.add(exp_port)
                    break

        # Build env var string. Inject HOST=0.0.0.0 to ensure servers 
        # (like Vite, Flask, FastAPI) bind to all interfaces instead of 127.0.0.1.
        env_args = ["-e", "HOST=0.0.0.0"]
        for k, v in self.config.env_vars.items():
            env_args.extend(["-e", f"{k}={v}"])
            
        # Start container detached, mapping preferred ports directly and remaining with -P
        cmd = [
            "docker", "run", "-d", 
            "--name", self.container_name,
        ] + port_args + ["-P"] + env_args + [self.config.docker_image]
        
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
            ports = set()
            
            if self.is_compose:
                # Get ports for all services in the compose project
                compose_cmd = self._get_compose_cmd()
                ps_proc = subprocess.run(
                    compose_cmd + ["ps"],
                    cwd=self.config.workspace_path, capture_output=True, text=True
                )
                if ps_proc.returncode != 0:
                    self._dump_output("Docker Compose ps failed")
                    return []
                    
                # Support IPv4 (0.0.0.0, 127.0.0.1) and IPv6 (:::)
                for line in ps_proc.stdout.splitlines():
                    matches = re.finditer(r"(?:0\.0\.0\.0|:::|127\.0\.0\.1):(\d+)", line)
                    for m in matches:
                        ports.add(int(m.group(1)))
            else:
                # Check if container is still running
                status_proc = subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.Status}}", self.container_name],
                    capture_output=True, text=True
                )
                
                if status_proc.returncode != 0 or status_proc.stdout.strip() != "running":
                    self._dump_output("Docker container exited prematurely")
                    return []

                # Get port mappings
                port_proc = subprocess.run(
                    ["docker", "port", self.container_name],
                    capture_output=True, text=True
                )
                
                for line in port_proc.stdout.splitlines():
                    m = re.search(r"(?:0\.0\.0\.0|:::|127\.0\.0\.1):(\d+)", line)
                    if m:
                        ports.add(int(m.group(1)))
                    
            if ports:
                # Prioritize expected ports if present
                sorted_ports = []
                if self.config.detector_result and self.config.detector_result.expected_ports:
                    for ep in self.config.detector_result.expected_ports:
                        if ep in ports and ep not in sorted_ports:
                            sorted_ports.append(ep)
                for p in sorted(list(ports)):
                    if p not in sorted_ports:
                        sorted_ports.append(p)
                self.detected_ports = sorted_ports
                return self.detected_ports
                
            time.sleep(1)
            
        self._dump_output("Timed out waiting for a listening port")
        return []

    def _dump_output(self, reason: str):
        if not self.container_name:
            return
            
        print(f"\n  {reason}.")
        
        if self.is_compose:
            compose_cmd = self._get_compose_cmd()
            log_proc = subprocess.run(
                compose_cmd + ["logs", "--tail", "50"],
                cwd=self.config.workspace_path, capture_output=True, text=True
            )
        else:
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
            
        if self.is_compose:
            print(f"Terminating Docker Compose project {self.container_name}...")
            compose_cmd = self._get_compose_cmd()
            subprocess.run(
                compose_cmd + ["down"],
                cwd=self.config.workspace_path,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        else:
            print(f"Terminating container {self.container_name}...")
            subprocess.run(
                ["docker", "rm", "-f", self.container_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
