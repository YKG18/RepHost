import os
import sys
import subprocess
import time
import re
import urllib.request
from pathlib import Path
from typing import Optional

import queue
import threading

def enqueue_output(out, q):
    try:
        for line in iter(out.readline, ''):
            q.put(line)
    except ValueError:
        pass # Handle closed file
    out.close()

from app.core.config import get_base_path

class TunnelManager:
    def __init__(self, port: int):
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.public_url: Optional[str] = None
        self.bin_path = get_base_path() / "bin"
        self.cloudflared_path = self.bin_path / ("cloudflared.exe" if os.name == "nt" else "cloudflared")

    def _ensure_cloudflared(self):
        if self.cloudflared_path.exists():
            return
            
        # If running as PyInstaller EXE and not bundled, write next to executable
        if getattr(sys, "frozen", False):
            self.bin_path = Path(sys.executable).parent / "bin"
            self.cloudflared_path = self.bin_path / ("cloudflared.exe" if os.name == "nt" else "cloudflared")
            if self.cloudflared_path.exists():
                return

        self.bin_path.mkdir(parents=True, exist_ok=True)
        print("Downloading cloudflared binary...")
        if os.name == "nt":
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
        else:
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
            
        urllib.request.urlretrieve(url, str(self.cloudflared_path))
        if os.name != "nt":
            os.chmod(str(self.cloudflared_path), 0o755)

    def start(self) -> bool:
        self._ensure_cloudflared()
        
        # Start cloudflared in a subprocess targeting IPv4 127.0.0.1
        cmd = [str(self.cloudflared_path), "tunnel", "--url", f"http://127.0.0.1:{self.port}"]
        
        # cloudflared logs to stderr
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        print("Creating tunnel...")
        start_time = time.time()
        
        q = queue.Queue()
        t = threading.Thread(target=enqueue_output, args=(self.process.stderr, q))
        t.daemon = True
        t.start()
        
        while time.time() - start_time < 20:
            if self.process.poll() is not None:
                print("cloudflared exited unexpectedly.")
                return False
                
            try:
                line = q.get(timeout=0.5)
                m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if m:
                    self.public_url = m.group(0)
                    return True
            except queue.Empty:
                continue
                    
        print("Timed out waiting for tunnel URL.")
        return False

    def stop(self):
        if self.process:
            print(f"Closing tunnel for port {self.port}...")
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
