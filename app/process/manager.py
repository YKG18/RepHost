import os
import subprocess
import psutil
import time
from typing import Optional, List
from pathlib import Path
from app.core.models import RunConfig

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
        
        try:
            self.process = subprocess.Popen(
                run_cmd,
                cwd=self.config.workspace_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env
            )
            return True
        except Exception as e:
            print(f"Failed to start process: {e}")
            return False

    def get_listening_ports(self, max_wait: int = 15) -> List[int]:
        if not self.process:
            return []
            
        print("Detecting listening ports...")
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            ports = set()
            try:
                parent = psutil.Process(self.process.pid)
                children = parent.children(recursive=True)
                for proc in [parent] + children:
                    for conn in proc.connections(kind='inet'):
                        if conn.status == 'LISTEN':
                            ports.add(conn.laddr.port)
            except psutil.NoSuchProcess:
                break
                
            if ports:
                self.detected_ports = list(ports)
                return self.detected_ports
                
            time.sleep(1)
            
        return []

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
