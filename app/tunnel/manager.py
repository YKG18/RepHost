import os
import subprocess
import threading
import time
import re
import urllib.request
import stat
import shutil
from pathlib import Path
from typing import Optional

from app.core.config import BASE_DIR

class CloudflareTunnel:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.public_url: Optional[str] = None
        self.bin_dir = BASE_DIR / "bin"
        self.bin_path = self.bin_dir / "cloudflared.exe" if os.name == "nt" else self.bin_dir / "cloudflared"

    def ensure_binary(self) -> str:
        # First check if cloudflared is in PATH
        if shutil.which("cloudflared"):
            return "cloudflared"
            
        if not self.bin_path.exists():
            print("cloudflared binary not found. Downloading...")
            self.bin_dir.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
            else:
                machine = os.uname().machine
                if machine == "aarch64":
                     url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
                else:
                     url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
            
            urllib.request.urlretrieve(url, self.bin_path)
            
            if os.name != "nt":
                st = os.stat(self.bin_path)
                os.chmod(self.bin_path, st.st_mode | stat.S_IEXEC)
                
            print(f"Downloaded cloudflared to {self.bin_path}")
            
        return str(self.bin_path)

    def start(self, port: int) -> bool:
        bin_cmd = self.ensure_binary()
        
        # Start quick tunnel
        cmd = [bin_cmd, "tunnel", "--url", f"http://localhost:{port}"]
        
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        print("Waiting for Cloudflare Tunnel public URL...")
        
        # Parse output for URL
        def parse_output():
            url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
            while True:
                if self.process is None or self.process.stdout is None:
                    break
                line = self.process.stdout.readline()
                if not line:
                    break
                # print(f"[Tunnel] {line.strip()}") # Optional: debug logging
                match = url_pattern.search(line)
                if match and not self.public_url:
                    self.public_url = match.group(0)
                    print(f"Tunnel URL obtained: {self.public_url}")

        t = threading.Thread(target=parse_output, daemon=True)
        t.start()
        
        # Wait up to 15 seconds for URL
        for _ in range(30):
            if self.public_url:
                return True
            time.sleep(0.5)
            
        return False
        
    def stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            self.public_url = None
            print("Tunnel stopped.")
