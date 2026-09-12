import typer
import git
import shutil
import tempfile
import time
import os
import stat
from pathlib import Path

from app.core.config import WORKSPACES_DIR
from app.core.models import RunConfig
from app.detectors import detect_project
from app.runners.runner import Runner
from app.process.manager import ProcessManager
from app.health.checks import verify_http_port

app = typer.Typer(help="RepoHost CLI - Host GitHub repositories locally.")

def remove_readonly(func, path, exc_info):
    """Clear the readonly bit and reattempt the removal."""
    os.chmod(path, stat.S_IWRITE)
    func(path)

@app.command()
def main(repo_url: str):
    """
    Host a public GitHub repository locally.
    """
    import urllib.parse
    
    # Strip query parameters (e.g., ?utm_source=...) which cause git clone to fail
    parsed_url = urllib.parse.urlparse(repo_url)
    clean_repo_url = urllib.parse.urlunparse(parsed_url._replace(query=""))
    
    typer.echo(f"RepoHost\n")
    typer.echo(f"-> Cloning repository: {clean_repo_url}")
    
    workspace = Path(tempfile.mkdtemp(dir=WORKSPACES_DIR))
    manager = None
    
    try:
        git.Repo.clone_from(clean_repo_url, workspace)
        typer.echo("[+] Done")
        
        typer.echo("\n-> Detecting project")
        detector_result = detect_project(workspace)
        
        if not detector_result:
            typer.echo("[-] Could not detect project type.")
            return
            
        typer.echo(f"[+] {detector_result.framework} / {detector_result.package_manager}")
        
        # Ask for environment variables if detected
        if detector_result.env_vars:
            typer.echo("\nThis project appears to require environment variables.")
            for key, val in detector_result.env_vars.items():
                default_val = val if val else ""
                user_input = typer.prompt(f"{key}", default=default_val, show_default=bool(default_val))
                detector_result.env_vars[key] = user_input
        
        config = RunConfig(
            repository_url=repo_url,
            workspace_path=str(workspace),
            detector_result=detector_result,
            env_vars=detector_result.env_vars,
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
            typer.echo("\nPUBLIC URL\n(Not implemented in Phase 1)\n")
            typer.echo(f"Local URL\nhttp://localhost:{target_port}\n")
            
            try:
                typer.echo("Press Ctrl+C to stop.")
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                typer.echo("\nStopping application...")
        else:
            typer.echo("\n[-] Application failed health check.")
            
    except Exception as e:
        typer.echo(f"\n[-] Error: {e}")
    finally:
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
