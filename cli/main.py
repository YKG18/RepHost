import typer
import git
import shutil
import tempfile
import time
import os
import stat
from pathlib import Path
from typing import Optional

from app.core.config import WORKSPACES_DIR
from app.core.models import RunConfig
from app.detectors import detect_project
from app.runners.runner import Runner
from app.process.manager import ProcessManager
from app.health.checks import verify_http_port
from app.tunnel.manager import CloudflareTunnel

app = typer.Typer(help="RepoHost CLI - Host GitHub repositories locally.")

def remove_readonly(func, path, exc_info):
    """Clear the readonly bit and reattempt the removal."""
    os.chmod(path, stat.S_IWRITE)
    func(path)

@app.command()
def main(
    repo_url: Optional[str] = typer.Argument(None, help="The GitHub repository URL to host."),
    gui: bool = typer.Option(False, "--gui", help="Launch the Tkinter GUI.")
):
    """
    Host a public GitHub repository locally, or launch the GUI interface.
    """
    if gui or not repo_url:
        typer.echo("Launching GUI...")
        from ui.app import run_gui
        run_gui()
        return

    typer.echo(f"RepoHost\n")
    typer.echo(f"-> Cloning repository: {repo_url}")
    
    workspace = Path(tempfile.mkdtemp(dir=WORKSPACES_DIR))
    manager = None
    tunnel = None
    
    try:
        git.Repo.clone_from(repo_url, workspace)
        typer.echo("[+] Done")
        
        typer.echo("\n-> Detecting project")
        detector_result = detect_project(workspace)
        
        if not detector_result:
            typer.echo("[-] Could not detect project type.")
            return
            
        typer.echo(f"[+] {detector_result.framework} / {detector_result.package_manager}")
        
        config = RunConfig(
            repository_url=repo_url,
            workspace_path=str(workspace),
            detector_result=detector_result
        )
        
        typer.echo("\n-> Installing dependencies")
        if Runner.install_dependencies(config):
            typer.echo("[+] Done")
        else:
            typer.echo("[-] Failed to install dependencies.")
            return
            
        typer.echo("\n-> Starting application")
        manager = ProcessManager(config)
        if not manager.start():
            typer.echo("[-] Failed to start application.")
            return
            
        ports = manager.get_listening_ports()
        if not ports:
            typer.echo("[-] No listening port detected within timeout.")
            return
            
        target_port = ports[0]
        typer.echo(f"[+] Listening on port {target_port}")
        
        if verify_http_port(target_port):
            typer.echo("\n-> Creating Cloudflare Tunnel...")
            tunnel = CloudflareTunnel()
            if tunnel.start(target_port):
                typer.echo("\nPUBLIC URL")
                typer.echo(tunnel.public_url)
                typer.echo(f"\nLocal URL\nhttp://localhost:{target_port}\n")
                
                try:
                    typer.echo("Press Ctrl+C to stop.")
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    typer.echo("\nStopping application...")
            else:
                typer.echo("[-] Failed to establish tunnel.")
        else:
            typer.echo("\n[-] Application failed health check.")
            
    except Exception as e:
        typer.echo(f"\n[-] Error: {e}")
    finally:
        if tunnel:
            tunnel.stop()
        if manager and manager.process:
            manager.stop()
            
        typer.echo(f"Cleaning up workspace...")
        try:
            shutil.rmtree(workspace, onerror=remove_readonly)
            typer.echo("[+] Cleaned up")
        except Exception as e:
            typer.echo(f"Failed to clean up: {e}")

if __name__ == "__main__":
    app()
