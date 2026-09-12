import shutil
import subprocess
import sys
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple
from app.core.models import RunConfig, ProjectType

# Binaries whose first argv element should be swapped for the project's
# freshly-created virtualenv equivalent once one exists.
VENV_BINARIES = {"python", "flask", "uvicorn", "streamlit"}

_MSYS_DRIVE_PATH = re.compile(r'^/([a-zA-Z])(/.*)?$')


def _msys_to_windows_path(path_str: str) -> str:
    """Convert an MSYS/Git-Bash style path (e.g. "/c/Program Files/nodejs")
    to a native Windows path ("C:\\Program Files\\nodejs"). Returns the
    input unchanged if it doesn't look like an MSYS-style absolute path."""
    m = _MSYS_DRIVE_PATH.match(path_str)
    if not m:
        return path_str
    drive = m.group(1).upper()
    rest = (m.group(2) or "").replace("/", "\\")
    return f"{drive}:{rest}"


def _split_path_env(raw_path: str) -> List[str]:
    """Split a PATH environment variable into directory entries, coping
    with the fact that under some Git Bash / MINGW64 setups a native
    Windows Python process can inherit PATH in Unix/MSYS format
    (colon-separated) rather than Windows format (semicolon-separated)."""
    if not raw_path:
        return []
    sep = ";" if ";" in raw_path else ":"
    return [p for p in raw_path.split(sep) if p]


def _windows_which_fallback(name: str) -> Optional[str]:
    """Manual PATH/PATHEXT lookup used when shutil.which() finds nothing.

    shutil.which() assumes PATH is in native-Windows format (semicolon
    separated, "C:\\..." entries). If the calling process actually
    inherited an MSYS/Git-Bash-style PATH (colon separated, "/c/..."
    entries) - which happens for some Git Bash/MINGW64 configurations -
    shutil.which() will silently find nothing even though the binary is
    genuinely installed and usable directly in that same shell. This
    re-does the search after normalizing each PATH entry to a Windows path.
    """
    raw_path = os.environ.get("PATH", "")
    pathext = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";")
    # Always check the bare name too, in case it's already a full filename.
    suffixes = [""] + [e for e in pathext if e]

    for entry in _split_path_env(raw_path):
        win_dir = _msys_to_windows_path(entry.strip())
        for suffix in suffixes:
            candidate = os.path.join(win_dir, f"{name}{suffix}")
            try:
                if os.path.isfile(candidate):
                    return candidate
            except OSError:
                continue
    return None


def resolve_executable(name: str) -> str:
    """Resolve a command name to a concrete executable path.

    On Windows, tools installed via npm/nvm/etc. are often `.cmd`/`.bat`
    shims. `subprocess.Popen([...])` without `shell=True` can fail to find
    these unless we resolve the full path ourselves via PATH/PATHEXT
    lookup (which `shutil.which` performs correctly). Falls back to the
    original name if resolution fails, so behavior on POSIX systems (where
    this is rarely an issue) is unaffected.
    """
    found = shutil.which(name)
    if found:
        return found

    # shutil.which() found nothing - before giving up, try again assuming
    # PATH might be in MSYS/Git-Bash format rather than native Windows
    # format (see _windows_which_fallback). Cheap and a no-op in practice
    # on real POSIX systems, since PATH entries there won't match the
    # "/<drive-letter>/..." pattern this rewrites.
    found = _windows_which_fallback(name)
    return found if found else name


class Runner:
    @staticmethod
    def _work_dir(config: RunConfig) -> Path:
        """Directory install/build commands should run from. Mirrors
        ProcessManager._run_dir() so a detector result whose working_dir
        points into a monorepo subfolder (e.g. "backend") gets its
        dependencies installed in that subfolder, not the repo root."""
        wd = config.detector_result.working_dir
        base = Path(config.workspace_path)
        if wd and wd not in (".", ""):
            return base / wd
        return base

    @staticmethod
    def _run_install(cmd: List[str], cwd: Path, env: dict) -> Tuple[bool, bool]:
        """Run one install command. Returns (succeeded, essential_failure).
        essential_failure is only True when the command itself couldn't be
        found (e.g. npm/pip missing) - a non-zero exit from a real install
        attempt is treated as non-essential per the "if it runs, it runs"
        directive, since the real arbiter of success is whether the app
        starts and responds afterward."""
        try:
            subprocess.run(cmd, cwd=cwd, check=True, env=env)
            return True, False
        except subprocess.CalledProcessError as e:
            print(f"Installation command failed (exit {e.returncode}): {' '.join(cmd)}")
            return False, False
        except FileNotFoundError as e:
            print(f"Installation failed - command not found ({cmd[0]}): {e}")
            print(f"    If '{Path(cmd[0]).name}' works when you type it directly in this")
            print("    terminal, this is likely a PATH-format mismatch between this shell")
            print("    and the Python process (common under Git Bash/MINGW64 on Windows)")
            print(f"    rather than a missing install. Otherwise, install {Path(cmd[0]).name}")
            print("    and make sure it's on your PATH, then try again.")
            return False, True

    @staticmethod
    def _permissive_fallback(install_cmd: List[str]) -> Optional[List[str]]:
        """A more permissive retry variant of an install command, for
        non-essential failures like optional/peer-dependency errors."""
        if not install_cmd:
            return None
        exe = Path(install_cmd[0]).name.lower()
        if exe.startswith("npm"):
            if "install" not in install_cmd or "--no-optional" in install_cmd:
                return None
            return install_cmd + ["--no-optional", "--legacy-peer-deps"]
        if exe.startswith("yarn"):
            if "install" not in install_cmd and len(install_cmd) > 1:
                pass
            if "--ignore-optional" in install_cmd:
                return None
            return install_cmd + ["--ignore-optional"]
        if exe.startswith("pnpm"):
            if "--no-optional" in install_cmd:
                return None
            return install_cmd + ["--no-optional"]
        if exe.startswith("pip"):
            if "--no-deps" in install_cmd:
                return None
            return install_cmd + ["--no-deps"]
        return None

    @staticmethod
    def install_dependencies(config: RunConfig) -> bool:
        if config.detector_result.project_type == ProjectType.DOCKER:
            return Runner._docker_build(config)

        if not config.detector_result.install_command:
            return True

        install_cmd = list(config.detector_result.install_command)
        run_cmd = config.detector_result.run_command
        work_dir = Runner._work_dir(config)

        env = os.environ.copy()
        # Ensure any Python child process (this install step, and later the
        # app itself) flushes output immediately rather than block-buffering
        # under a non-interactive pipe/pty (notably on Windows/Git Bash),
        # which otherwise makes long installs/startups look "hung".
        env["PYTHONUNBUFFERED"] = "1"

        if config.detector_result.project_type == ProjectType.PYTHON:
            venv_path = work_dir / ".venv"
            if not venv_path.exists():
                print("Creating virtual environment...")
                try:
                    subprocess.run([sys.executable, "-m", "venv", ".venv"],
                                   cwd=work_dir, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"Failed to create virtual environment: {e}")
                    return False

            bin_dir = "Scripts" if os.name == "nt" else "bin"

            if install_cmd and install_cmd[0] == "pip":
                install_cmd[0] = str(venv_path / bin_dir / "pip")

            if run_cmd and run_cmd[0] in VENV_BINARIES:
                run_cmd[0] = str(venv_path / bin_dir / run_cmd[0])
        else:
            install_cmd[0] = resolve_executable(install_cmd[0])

        print(f"Installing dependencies using: {' '.join(install_cmd)}")

        ok, essential_failure = Runner._run_install(install_cmd, work_dir, env)
        if ok:
            return True
        if essential_failure:
            # The install tool itself isn't available - nothing we retry
            # will fix that.
            return False

        fallback_cmd = Runner._permissive_fallback(install_cmd)
        if fallback_cmd:
            print(f"Retrying install with a more permissive flag: {' '.join(fallback_cmd)}")
            ok, essential_failure = Runner._run_install(fallback_cmd, work_dir, env)
            if ok:
                return True
            if essential_failure:
                return False

        # Non-essential: log and keep going. Whether the app actually
        # starts and responds on a port is the real test, not the
        # install step's exit code.
        print("[!] Dependency installation did not fully succeed. "
              "Continuing anyway - startup and the health check will be "
              "the real test of whether this app runs.")
        return True

    @staticmethod
    def _docker_build(config: RunConfig) -> bool:
        install_cmd = config.detector_result.install_command
        if not install_cmd:
            return True
        if not shutil.which("docker"):
            print("Docker does not appear to be installed or is not on PATH.")
            return False
        work_dir = Runner._work_dir(config)
        print(f"Building Docker image using: {' '.join(install_cmd)}")
        try:
            subprocess.run(install_cmd, cwd=work_dir, check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Docker build failed: {e}")
            return False
