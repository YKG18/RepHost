import os
import subprocess
import psutil
import time
import re
from typing import Optional, List
from pathlib import Path
from app.core.models import RunConfig, ProjectType
from app.runners.runner import resolve_executable


class ProcessManager:
    def __init__(self, config: RunConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.detected_ports: List[int] = []
        self._is_docker = config.detector_result.project_type == ProjectType.DOCKER

    def _run_dir(self) -> str:
        wd = self.config.detector_result.working_dir
        if wd and wd not in (".", ""):
            return str(Path(self.config.workspace_path) / wd)
        return self.config.workspace_path

    def start(self) -> bool:
        run_cmd = list(self.config.detector_result.run_command or [])
        if not run_cmd:
            print("No run command found.")
            return False

        if run_cmd[0] not in ("python", "node") and not self._is_docker:
            # Python/node paths are resolved elsewhere (venv substitution);
            # everything else (npm/yarn/pnpm/bun/uvicorn/flask/etc.) may need
            # PATH/PATHEXT resolution, especially on Windows.
            run_cmd[0] = resolve_executable(run_cmd[0])

        print(f"Starting application using: {' '.join(run_cmd)}")

        env = os.environ.copy()
        # Avoid block-buffered stdout under a non-interactive pipe/pty
        # (notably Windows/Git Bash), which can otherwise make a running
        # app look like it printed nothing until it exits.
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.update(self.config.detector_result.env or {})
        env.update(self.config.env_vars)

        try:
            self.process = subprocess.Popen(
                run_cmd,
                cwd=self._run_dir(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env
            )
            return True
        except Exception as e:
            print(f"Failed to start process: {e}")
            return False

    def get_listening_ports(self, max_wait: int = 45) -> List[int]:
        if not self.process:
            return []

        if self._is_docker:
            return self._get_docker_ports(max_wait)

        print("Detecting listening ports...")
        start_time = time.time()

        while time.time() - start_time < max_wait:
            if self.process.poll() is not None:
                # Process already exited - no point in continuing to poll.
                break

            ports = set()
            try:
                parent = psutil.Process(self.process.pid)
                children = parent.children(recursive=True)
                for proc in [parent] + children:
                    try:
                        conns = proc.connections(kind='inet')
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                    for conn in conns:
                        if conn.status == 'LISTEN':
                            ports.add(conn.laddr.port)
            except psutil.NoSuchProcess:
                break

            if ports:
                self.detected_ports = list(ports)
                return self.detected_ports

            time.sleep(1)

        return []

    def _get_docker_ports(self, max_wait: int) -> List[int]:
        container_name = "repohost-app-run"
        start_time = time.time()
        while time.time() - start_time < max_wait:
            if self.process and self.process.poll() is not None:
                break
            try:
                result = subprocess.run(
                    ["docker", "port", container_name],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    # Lines look like: "8080/tcp -> 0.0.0.0:54321"
                    ports = set()
                    for line in result.stdout.strip().splitlines():
                        m = re.search(r':(\d+)\s*$', line.strip())
                        if m:
                            ports.add(int(m.group(1)))
                    if ports:
                        self.detected_ports = list(ports)
                        return self.detected_ports
            except Exception:
                pass
            time.sleep(1)
        return []

    def stop(self):
        if not self.process:
            return

        if self._is_docker:
            print("Stopping Docker container...")
            try:
                subprocess.run(["docker", "stop", "repohost-app-run"],
                                capture_output=True, timeout=15)
            except Exception:
                pass

        print(f"Terminating process {self.process.pid}...")
        try:
            parent = psutil.Process(self.process.pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            parent.terminate()

            gone, alive = psutil.wait_procs([parent] + children, timeout=3)
            for p in alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
        except psutil.NoSuchProcess:
            pass
