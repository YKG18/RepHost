import os
import subprocess
import psutil
import time
from typing import Optional, List
from pathlib import Path
from app.core.models import RunConfig, ProjectType

class ProcessManager:
    def __init__(self, config: RunConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.detected_ports: List[int] = []

    def start(self) -> bool:
        run_cmd = self.config.detector_result.run_command
        if not run_cmd:
            print("No run command found.")
            return False
            
        print(f"Starting application using: {' '.join(run_cmd)}")
        
        env = os.environ.copy()
        env.update(self.config.env_vars)
        
        # On Windows, Node.js tools (npm, npx, yarn) are .cmd batch files
        # that require shell=True for subprocess to resolve them.
        use_shell = (os.name == "nt" and
                     self.config.detector_result.project_type == ProjectType.NODE)
        
        try:
            self.process = subprocess.Popen(
                run_cmd,
                cwd=self.config.workspace_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                shell=use_shell,
            )
            return True
        except Exception as e:
            print(f"Failed to start process: {e}")
            return False

    def get_listening_ports(self, max_wait: int = 30) -> List[int]:
        if not self.process:
            return []
            
        print("Detecting listening ports...")
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            # Check if the process has already crashed
            if self.process.poll() is not None:
                self._dump_output("Process exited prematurely")
                return []

            ports = set()
            try:
                parent = psutil.Process(self.process.pid)
                children = parent.children(recursive=True)
                for proc in [parent] + children:
                    for conn in proc.connections(kind='inet'):
                        if conn.status == 'LISTEN':
                            ports.add(conn.laddr.port)
            except psutil.NoSuchProcess:
                self._dump_output("Process disappeared")
                return []
                
            if ports:
                self.detected_ports = list(ports)
                return self.detected_ports
                
            time.sleep(1)
            
        # Timed out — show what the process printed
        self._dump_output("Timed out waiting for a listening port")
        return []

    def _dump_output(self, reason: str):
        """Read whatever the process wrote to stdout/stderr and print it."""
        if not self.process or not self.process.stdout:
            return
        lines = []
        try:
            # Read available output (non-blocking)
            import select
            while True:
                line = self.process.stdout.readline()
                if not line:
                    break
                lines.append(line.rstrip())
                if len(lines) > 50:  # Cap output
                    break
        except Exception:
            pass

        print(f"\n  {reason}.")
        if lines:
            print("  --- Application output ---")
            for line in lines:
                print(f"  {line}")
            print("  --- End of output ---")

    def stop(self):
        if not self.process:
            return
            
        print(f"Terminating process {self.process.pid}...")
        try:
            parent = psutil.Process(self.process.pid)
            for child in parent.children(recursive=True):
                child.terminate()
            parent.terminate()
            
            gone, alive = psutil.wait_procs([parent] + parent.children(recursive=True), timeout=3)
            for p in alive:
                p.kill()
        except psutil.NoSuchProcess:
            pass
