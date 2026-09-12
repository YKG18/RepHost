import sys

# Fix for blank/delayed CLI output under non-interactive pipes and Windows
# ptys (e.g. Git Bash / MINGW): Python's stdout is block-buffered rather
# than line-buffered in that situation, so `print()`/`typer.echo()` calls
# can appear to "hang" until a buffer fills or the process exits. Forcing
# line buffering here means the user actually sees progress as it happens.
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

import typer
import git
import shutil
import tempfile
import time
import os
import stat
import threading
import collections
from pathlib import Path

from app.core.config import WORKSPACES_DIR
from app.core.models import RunConfig, ProjectType
from app.detectors import detect_project, describe_scan
from app.runners.runner import Runner
from app.process.manager import ProcessManager
from app.health.checks import verify_http_port, probe_alternate_paths

app = typer.Typer(help="RepoHost CLI - Host GitHub repositories locally.")

LOG_LINES = 200


def echo(message: str = "") -> None:
    """typer.echo, but flushed immediately. Belt-and-suspenders alongside
    the stdout line-buffering fix above, since some environments buffer
    even "line-buffered" streams more aggressively than expected."""
    typer.echo(message)
    sys.stdout.flush()


def remove_readonly(func, path, exc_info):
    """Clear the readonly bit and reattempt the removal."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _tail_process_output(process, buf: collections.deque):
    try:
        for line in iter(process.stdout.readline, ''):
            if not line:
                break
            buf.append(line.rstrip())
    except Exception:
        pass


def _print_logs(buf: collections.deque):
    if not buf:
        return
    echo("\n--- Application logs ---")
    for line in buf:
        echo(line)
    echo("--- end logs ---")


@app.command()
def main(repo_url: str):
    """
    Host a public GitHub repository locally.
    """
    echo("RepoHost\n")
    echo(f"-> Cloning repository: {repo_url}")

    workspace = Path(tempfile.mkdtemp(dir=WORKSPACES_DIR))
    manager = None
    log_buffer: collections.deque = collections.deque(maxlen=LOG_LINES)

    try:
        try:
            git.Repo.clone_from(repo_url, workspace, multi_options=["--depth=1"])
        except git.exc.GitCommandError as e:
            echo(f"[-] Could not clone repository: {e}")
            return
        echo("[+] Done")

        echo("\n-> Detecting project")
        detector_result = detect_project(workspace)

        if not detector_result:
            echo("[-] Could not detect how to run this project.")
            echo("    RepoHost looked for a static index.html, a Node.js")
            echo("    package.json, a Python project (Flask/FastAPI/Django/")
            echo("    Streamlit), and Docker configuration - at the repo root,")
            echo("    in common split-service layouts (backend/+frontend/,")
            echo("    server/+client/, api/+web/, api/+ui/), and one level")
            echo("    into every other subdirectory - but found none of these")
            echo("    in a recognizable form. Here's exactly what was checked:")
            for line in describe_scan(workspace):
                echo(f"      - {line}")
            return

        pm_label = detector_result.package_manager or "-"
        location = f" (in {detector_result.matched_path}/)" if detector_result.matched_path else ""
        echo(f"[+] {detector_result.framework} / {pm_label}{location} (confidence {detector_result.confidence:.2f})")

        if detector_result.secondary_services:
            for svc in detector_result.secondary_services:
                svc_desc = svc.get("framework") or svc.get("type") or "project"
                echo(f"    Note: also found a {svc_desc} in {svc['path']}/ - not started "
                     f"(this run only hosts one service; see logs to run it separately).")

        if detector_result.project_type == ProjectType.DOCKER and not shutil.which("docker"):
            echo("[-] This project needs Docker, but Docker was not found on PATH.")
            return

        config = RunConfig(
            repository_url=repo_url,
            workspace_path=str(workspace),
            detector_result=detector_result,
            env_vars=dict(detector_result.env or {}),
        )

        echo("\n-> Installing dependencies")
        if Runner.install_dependencies(config):
            echo("[+] Done")
        else:
            echo("[-] Failed to install dependencies (no usable install tool found).")
            return

        echo("\n-> Starting application")
        manager = ProcessManager(config)
        if not manager.start():
            echo("[-] Failed to start application.")
            return

        log_thread = threading.Thread(
            target=_tail_process_output, args=(manager.process, log_buffer), daemon=True
        )
        log_thread.start()

        ports = manager.get_listening_ports()
        if not ports:
            echo("[-] No listening port detected within timeout.")
            if manager.process.poll() is not None:
                echo(f"    The process exited early (code {manager.process.returncode}).")
            _print_logs(log_buffer)
            return

        target_port = ports[0]
        echo(f"[+] Listening on port {target_port}")

        ok, status = verify_http_port(target_port)
        if ok:
            echo("\nPUBLIC URL\n(Not implemented in Phase 1)\n")
            echo(f"Local URL\nhttp://localhost:{target_port}\n")

            if status is not None and status >= 400:
                echo(f"Note: the root path responded with HTTP {status}. That's still a live,")
                echo("responding server - many APIs/SPAs simply don't serve anything at \"/\".")
                alternates = probe_alternate_paths(target_port)
                if alternates:
                    echo(f"These paths responded successfully: {', '.join(alternates)}")
                echo("")

            try:
                echo("Press Ctrl+C to stop.")
                while True:
                    time.sleep(1)
                    if manager.process.poll() is not None:
                        echo(f"\n[-] Application process exited unexpectedly (code {manager.process.returncode}).")
                        _print_logs(log_buffer)
                        break
            except KeyboardInterrupt:
                echo("\nStopping application...")
        else:
            echo("\n[-] Application failed health check (no HTTP response within timeout).")
            _print_logs(log_buffer)

    except Exception as e:
        echo(f"\n[-] Error: {e}")
    finally:
        if manager and manager.process:
            manager.stop()

        echo("Cleaning up workspace...")
        try:
            shutil.rmtree(workspace, onerror=remove_readonly)
            echo("[+] Cleaned up")
        except Exception as e:
            echo(f"Failed to clean up: {e}")


if __name__ == "__main__":
    app()
