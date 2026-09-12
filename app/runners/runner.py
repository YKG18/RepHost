import subprocess
import shutil
import os
import re
from pathlib import Path
from app.core.models import RunConfig, ProjectType


class Runner:
    """Handles dependency installation with automatic recovery strategies."""

    MAX_RETRIES = 3

    @staticmethod
    def _run_subprocess(cmd, cwd, project_type, check=True, **kwargs):
        """Central subprocess helper. Uses shell=True on Windows for Node.js
        commands so that .cmd batch files (npm.cmd, yarn.cmd, etc.) resolve."""
        use_shell = (os.name == "nt" and project_type == ProjectType.NODE)
        return subprocess.run(
            cmd, cwd=cwd, check=check, shell=use_shell, **kwargs
        )

    @staticmethod
    def _ensure_package_manager(config: RunConfig):
        """If the detected package manager isn't installed, fall back to npm."""
        if config.detector_result.project_type != ProjectType.NODE:
            return

        pm = config.detector_result.package_manager
        if pm in ("yarn", "pnpm", "bun") and shutil.which(pm) is None:
            print(f"Warning: '{pm}' not found on system. Falling back to npm.")
            config.detector_result.package_manager = "npm"
            config.detector_result.install_command = ["npm", "install"]

            run_cmd = config.detector_result.run_command
            if run_cmd and len(run_cmd) >= 2:
                script = run_cmd[-1]
                config.detector_result.run_command = ["npm", "run", script]

    # ── Python install strategies (tried in order) ──────────────────────

    @staticmethod
    def _python_strategies(pip_path: str, cwd: str, install_cmd: list = None):
        """Yields (description, command_list) tuples for progressively more
        lenient pip install attempts."""
        
        # If no requirements.txt exists and we generated a direct command like
        # ["pip", "install", "streamlit", "yfinance"], just use that directly
        # and don't try all the -r requirements.txt fallbacks.
        if install_cmd and "-r" not in install_cmd:
            # Replace 'pip' with the venv pip path
            base = [pip_path] + install_cmd[1:]
            yield ("Installing dynamically discovered dependencies", base)
            return

        base = [pip_path, "install", "-r", "requirements.txt"]

        yield (
            "Installing with pre-built binaries preferred",
            base + ["--prefer-binary"],
        )
        yield (
            "Retrying with binary-only packages (skipping source builds)",
            base + ["--only-binary", ":all:"],
        )
        yield (
            "Retrying with relaxed constraints (ignoring version pins)",
            [pip_path, "install", "--prefer-binary", "--no-deps", "-r", "requirements.txt"],
        )

    @staticmethod
    def _setup_python_venv(config: RunConfig) -> str:
        """Create a venv if needed, upgrade pip inside it, and return the
        absolute path to the venv's pip executable."""
        venv_path = Path(config.workspace_path) / ".venv"
        if not venv_path.exists():
            print("Creating virtual environment...")
            subprocess.run(
                ["python", "-m", "venv", ".venv"],
                cwd=config.workspace_path, check=True,
            )

        if os.name == "nt":
            pip_path = str(venv_path / "Scripts" / "pip")
            python_path = str(venv_path / "Scripts" / "python")
        else:
            pip_path = str(venv_path / "bin" / "pip")
            python_path = str(venv_path / "bin" / "python")

        # Always upgrade pip first — avoids a huge class of build failures
        print("Upgrading pip...")
        subprocess.run(
            [python_path, "-m", "pip", "install", "--upgrade", "pip"],
            cwd=config.workspace_path,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        return pip_path

    @staticmethod
    def _rewrite_python_run_command(config: RunConfig):
        """Point the run command at the venv's Python/binaries."""
        venv_path = Path(config.workspace_path) / ".venv"
        run_cmd = config.detector_result.run_command
        if not run_cmd:
            return

        target_bins = ["python", "flask", "uvicorn", "streamlit"]
        if run_cmd[0] in target_bins:
            if os.name == "nt":
                run_cmd[0] = str(venv_path / "Scripts" / run_cmd[0])
            else:
                run_cmd[0] = str(venv_path / "bin" / run_cmd[0])

    @staticmethod
    def _install_python(config: RunConfig) -> bool:
        pip_path = Runner._setup_python_venv(config)
        Runner._rewrite_python_run_command(config)

        for desc, cmd in Runner._python_strategies(pip_path, config.workspace_path, config.detector_result.install_command):
            print(desc + "...")
            try:
                result = subprocess.run(
                    cmd, cwd=config.workspace_path,
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    return True

                # Parse which package failed so we can report it clearly
                stderr = result.stdout + result.stderr
                failed_pkg = Runner._extract_failed_package(stderr)
                if failed_pkg:
                    print(f"  Package '{failed_pkg}' failed to build. Trying next strategy...")
                else:
                    print("  Install returned errors. Trying next strategy...")
            except FileNotFoundError:
                print(f"  Command not found: {cmd[0]}")
                return False

        # Last resort: install line-by-line, skipping broken packages
        # If the install_command provides a list of packages instead of requirements.txt, use those.
        cmd = config.detector_result.install_command
        packages = []
        if cmd and cmd[0] == "pip" and cmd[1] == "install" and "-r" not in cmd:
            packages = cmd[2:]

        return Runner._install_python_line_by_line(pip_path, config.workspace_path, packages)

    @staticmethod
    def _install_python_line_by_line(pip_path: str, cwd: str, fallback_packages: list = None) -> bool:
        """Read requirements.txt and install each package individually,
        skipping any that fail. This ensures one broken package doesn't
        block the entire project."""
        lines = fallback_packages or []
        req_file = Path(cwd) / "requirements.txt"
        if req_file.exists():
            try:
                content = req_file.read_text(encoding="utf-8", errors="ignore")
                lines = [l.strip() for l in content.splitlines()]
            except Exception:
                pass

        if not lines:
            return False

        installed = 0
        skipped = []

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Strip off inline comments
            pkg = line.split("#")[0].strip()
            if not pkg:
                continue

            try:
                subprocess.run(
                    [pip_path, "install", pkg],
                    cwd=cwd,
                    capture_output=True,
                    check=True
                )
                installed += 1
            except subprocess.CalledProcessError:
                pkg_name = pkg.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0]
                print(f"  Skipped: {pkg_name} (failed to build)")
                skipped.append(pkg_name)

        total = installed + len(skipped)
        if skipped:
            print(f"  Installed {installed}/{total} packages. Skipped: {', '.join(skipped)}")
            print("  The application may still work if these are optional dependencies.")
        else:
            print(f"  All {installed} packages installed.")

        return installed > 0 or total == 0

    @staticmethod
    def _extract_failed_package(output: str) -> str:
        """Try to pull the failing package name out of pip's error output."""
        patterns = [
            r"Failed to build\s+'?([a-zA-Z0-9_-]+)'?",
            r"ERROR: Failed to build '([a-zA-Z0-9_-]+)'",
            r"error: subprocess-exited-with-error.*?([a-zA-Z0-9_-]+)",
        ]
        for pat in patterns:
            m = re.search(pat, output, re.IGNORECASE | re.DOTALL)
            if m:
                return m.group(1)
        return ""

    # ── Node.js install ─────────────────────────────────────────────────

    @staticmethod
    def _install_node(config: RunConfig) -> bool:
        Runner._ensure_package_manager(config)
        cmd = config.detector_result.install_command
        print(f"Installing dependencies using: {' '.join(cmd)}")
        try:
            Runner._run_subprocess(
                cmd, config.workspace_path,
                config.detector_result.project_type,
            )
            return True
        except FileNotFoundError:
            print(f"Installation failed: '{cmd[0]}' not found. Is Node.js installed?")
            return False
        except subprocess.CalledProcessError as e:
            print(f"Installation failed (exit code {e.returncode}).")
            return False

    # ── Public entry point ──────────────────────────────────────────────

    @staticmethod
    def install_dependencies(config: RunConfig) -> bool:
        if not config.detector_result.install_command:
            return True

        ptype = config.detector_result.project_type

        if ptype == ProjectType.PYTHON:
            return Runner._install_python(config)
        elif ptype == ProjectType.NODE:
            return Runner._install_node(config)
        else:
            # Generic fallback
            print(f"Installing dependencies using: {' '.join(config.detector_result.install_command)}")
            try:
                Runner._run_subprocess(
                    config.detector_result.install_command,
                    config.workspace_path,
                    config.detector_result.project_type,
                )
                return True
            except Exception as e:
                print(f"Installation failed: {e}")
                return False
