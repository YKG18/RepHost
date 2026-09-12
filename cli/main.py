import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
import git
import shutil
import tempfile
import time
import os
import stat
from pathlib import Path
from typing import List

from app.core.config import WORKSPACES_DIR
from app.core.models import RunConfig
from app.detectors import detect_project
from app.runners.runner import Runner
from app.process.manager import ProcessManager, MissingDependencyError
from app.health.checks import verify_http_ports

app = typer.Typer(help="RepoHost CLI - Host GitHub repositories locally.")

def remove_readonly(func, path, exc_info):
    """Clear the readonly bit and reattempt the removal."""
    os.chmod(path, stat.S_IWRITE)
    func(path)

@app.command()
def main(repo_url: str):
    """
    Host a public GitHub repository locally and expose it via Cloudflare Tunnels.
    """
    import urllib.parse
    
    parsed_url = urllib.parse.urlparse(repo_url)
    clean_repo_url = urllib.parse.urlunparse(parsed_url._replace(query=""))
    
    typer.echo(f"RepoHost\n")
    typer.echo(f"-> Cloning repository: {clean_repo_url}")
    
    workspace = Path(tempfile.mkdtemp(dir=WORKSPACES_DIR))
    
    process_managers: List[ProcessManager] = []
    
    try:
        git.Repo.clone_from(clean_repo_url, workspace)
        typer.echo("[+] Done")
        
        typer.echo("\n-> Detecting projects")
        detector_results = detect_project(workspace)
        
        if not detector_results:
            typer.echo("[-] Could not detect any runnable projects.")
            return
            
        typer.echo(f"[+] Found {len(detector_results)} service(s):")
        
        # We need to collect env vars before building
        configs = []
        for result in detector_results:
            typer.echo(f"  - [{result.sub_path}] {result.framework} / {result.package_manager}")
            
            if result.env_vars:
                typer.echo(f"\n[Environment Variables] for {result.sub_path}:")
                # Iterate over a copy of keys so we can delete from original
                for key in list(result.env_vars.keys()):
                    val = result.env_vars[key]
                    default_val = val if val else ""
                    user_input = typer.prompt(f"{key}", default=default_val, show_default=bool(default_val))
                    if user_input.strip():
                        result.env_vars[key] = user_input.strip()
                    else:
                        del result.env_vars[key]
            
            config = RunConfig(
                repository_url=repo_url,
                workspace_path=str(workspace / result.sub_path),
                detector_result=result,
                env_vars=result.env_vars,
            )
            configs.append(config)
        
        # Build Docker images
        typer.echo("\n-> Building Docker Images")
        for config in configs:
            typer.echo(f"Building [{config.detector_result.sub_path}]...")
            if not Runner.install_dependencies(config):
                typer.echo(f"[-] Failed to build Docker image for {config.detector_result.sub_path}")
                return
            typer.echo("[+] Done")
            
        # Start Docker containers
        typer.echo("\n-> Starting services")
        for config in configs:
            manager = ProcessManager(config)
            process_managers.append(manager)
            
            if not manager.start():
                typer.echo(f"[-] Failed to start container for {config.detector_result.sub_path}.")
                return
                
            ports = manager.get_listening_ports()
            if not ports:
                typer.echo(f"[-] No listening port detected for {config.detector_result.sub_path} within timeout.")
                return
                
            target_port = verify_http_ports(ports, container_name=manager.container_name)
            
            if target_port:
                manager.detected_ports = [target_port] # Save the exact working port for the output summary
            else:
                typer.echo(f"[-] {config.detector_result.sub_path} failed HTTP health check on all detected ports.")
                return
                
        typer.echo("\nALL SERVICES RUNNING")
        for config, manager in zip(configs, process_managers):
            typer.echo(f"\n[{config.detector_result.sub_path}]")
            typer.echo(f"  Local:  http://localhost:{manager.detected_ports[0]}")
            
        try:
            typer.echo("\nPress Ctrl+C to stop.")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            typer.echo("\nStopping application...")
            
    except Exception as e:
        typer.echo(f"\n[-] Error: {e}")
    finally:
        for manager in process_managers:
            manager.stop()
            
        typer.echo(f"Cleaning up workspace...")
        try:
            shutil.rmtree(workspace, onerror=remove_readonly)
            typer.echo("[+] Cleaned up")
        except Exception as e:
            typer.echo(f"Failed to clean up: {e}")

if __name__ == "__main__":
    app()
