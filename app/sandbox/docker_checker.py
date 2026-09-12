import os
import sys
import time
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# Ensure Docker binaries are available in PATH
for docker_bin in [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin"),
    r"C:\Program Files\Docker\Docker\resources\bin",
]:
    if os.path.exists(docker_bin) and docker_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = docker_bin + os.pathsep + os.environ.get("PATH", "")

def is_docker_running() -> bool:
    """Checks whether the Docker daemon is active and accepting commands."""
    try:
        res = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode == 0:
            out = res.stdout.lower()
            # If server connection failed, docker info returns error in stdout/stderr
            if "failed to connect" not in out and "is the docker daemon running" not in out:
                return True
        return False
    except Exception:
        return False

def find_docker_desktop_executable() -> Optional[Path]:
    """Finds the Docker Desktop executable path across standard operating system locations."""
    if os.name == "nt":
        candidates = [
            Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe")),
            Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe"),
            Path(os.path.expandvars(r"%ProgramFiles%\Docker\Docker\Docker Desktop.exe")),
            Path(os.path.expandvars(r"%ProgramW6432%\Docker\Docker\Docker Desktop.exe")),
        ]
        for p in candidates:
            if p.exists():
                return p
        which_path = shutil.which("Docker Desktop.exe")
        if which_path:
            return Path(which_path)
    return None

def start_docker_desktop() -> bool:
    """Attempts to launch Docker Desktop or the Docker daemon."""
    if sys.platform == "win32":
        exe_path = find_docker_desktop_executable()
        if exe_path and exe_path.exists():
            try:
                # Launch detached without blocking
                subprocess.Popen([str(exe_path)], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
                return True
            except Exception as e:
                print(f"[!] Failed to launch Docker Desktop executable: {e}")
                return False
        else:
            # Fallback to shell start command
            try:
                subprocess.Popen(["cmd", "/c", "start", "docker"], shell=True)
                return True
            except Exception:
                return False
    elif sys.platform == "darwin":
        try:
            subprocess.Popen(["open", "-a", "Docker"])
            return True
        except Exception:
            return False
    else:
        # Linux
        try:
            subprocess.Popen(["sudo", "systemctl", "start", "docker"])
            return True
        except Exception:
            return False

def ensure_docker_running(timeout: int = 90) -> bool:
    """
    Checks if Docker daemon is running. If not, automatically launches
    Docker Desktop and waits until the daemon is fully ready.
    """
    if is_docker_running():
        return True

    print("\n[!] Docker daemon is not running.")
    print("-> Attempting to start Docker Desktop automatically...")
    
    launched = start_docker_desktop()
    if not launched:
        print("[-] Could not find or launch Docker Desktop automatically.")
        print("    Please start Docker Desktop manually and retry.")
        return False

    print("-> Waiting for Docker engine to initialize (this may take up to a minute)...")
    start_time = time.time()
    last_reported = 0

    while time.time() - start_time < timeout:
        elapsed = int(time.time() - start_time)
        if is_docker_running():
            print(f"[+] Docker Desktop is ready! (initialized in {elapsed}s)\n")
            return True

        if elapsed - last_reported >= 5:
            last_reported = elapsed
            print(f"   Waiting for Docker daemon... ({elapsed}s/{timeout}s)")
        time.sleep(2)

    print(f"\n[-] Docker daemon failed to become ready within {timeout} seconds.")
    print("    Please ensure Docker Desktop is running and fully initialized.")
    return False
