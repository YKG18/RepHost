import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import typer
import git
import shutil
import tempfile
import time
import os
import stat
import webbrowser
from pathlib import Path
from typing import List, Optional

from app.core.config import WORKSPACES_DIR
from app.core.models import RunConfig
from app.detectors import detect_project
from app.detectors.connection_bridge import ConnectionBridge
from app.runners.runner import Runner
from app.process.manager import ProcessManager, is_port_available
from app.health.checks import verify_http_ports, find_working_docs_url
from app.tunnel.manager import TunnelManager
from app.sandbox.docker_checker import ensure_docker_running

# Ensure Docker binaries are available in PATH
for docker_bin in [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin"),
    r"C:\Program Files\Docker\Docker\resources\bin",
]:
    if os.path.exists(docker_bin) and docker_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = docker_bin + os.pathsep + os.environ.get("PATH", "")

app = typer.Typer(help="RepoHost CLI - Host GitHub repositories locally.")

def parse_duration(d_str: str) -> int:
    """Parse duration string like '5h', '1h', '30m', '120s' to seconds."""
    s = d_str.strip().lower()
    if s.endswith("h"):
        return int(float(s[:-1]) * 3600)
    elif s.endswith("m"):
        return int(float(s[:-1]) * 60)
    elif s.endswith("s"):
        return int(float(s[:-1]))
    try:
        return int(s)
    except ValueError:
        return 5 * 3600

def remove_readonly(func, path, exc_info):
    """Clear the readonly bit and reattempt the removal."""
    os.chmod(path, stat.S_IWRITE)
    func(path)

@app.command()
def main(
    repo_url: str,
    duration: str = typer.Option("5h", "--duration", "-d", help="Hosting session duration (e.g. 5h, 1h, 30m). Default: 5h."),
    no_tunnel: bool = typer.Option(False, "--no-tunnel", help="Do not create a public Cloudflare tunnel."),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Automatically open application in browser."),
):
    """
    Host a public GitHub repository locally and expose it via Cloudflare Tunnels.
    """
    import urllib.parse
    
    parsed_url = urllib.parse.urlparse(repo_url)
    clean_repo_url = urllib.parse.urlunparse(parsed_url._replace(query=""))
    
    typer.echo(f"RepoHost\n")

    # 1. Pre-flight check: Ensure Docker Desktop / daemon is active
    if not ensure_docker_running():
        typer.echo("[-] Docker must be running to build and host repositories. Exiting.")
        raise typer.Exit(code=1)

    typer.echo(f"-> Cloning repository: {clean_repo_url}")
    
    workspace = Path(tempfile.mkdtemp(dir=WORKSPACES_DIR))
    
    process_managers: List[ProcessManager] = []
    tunnel_managers: List[TunnelManager] = []
    
    try:
        if os.path.isdir(clean_repo_url):
            shutil.copytree(clean_repo_url, workspace, dirs_exist_ok=True)
            typer.echo("[+] Loaded local repository")
        else:
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
        is_interactive = sys.stdin.isatty()
        for result in detector_results:
            api_label = " (Backend API)" if result.is_backend_api else ""
            typer.echo(f"  - [{result.sub_path}] {result.framework}{api_label} / {result.package_manager}")
            
            if result.env_vars:
                for key in list(result.env_vars.keys()):
                    val = result.env_vars[key]
                    if not val and is_interactive:
                        user_input = typer.prompt(f"  [{result.sub_path}] {key} (optional, press Enter to skip)", default="", show_default=False)
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
        
        # Separate backend APIs from frontend/fullstack applications
        backend_configs = [c for c in configs if c.detector_result.is_backend_api]
        frontend_configs = [c for c in configs if not c.detector_result.is_backend_api]

        # 1. Pre-configure backends with default development secrets & CORS
        default_backend_secrets = {
            "JWT_SECRET_KEY": "repohost-dev-secret-jwt-key-change-in-production-32b",
            "SECRET_KEY": "repohost-dev-secret-key-change-in-production-32b",
            "FLASK_SECRET_KEY": "repohost-dev-secret-key-change-in-production-32b",
            "SESSION_SECRET": "repohost-dev-session-secret-key-32b",
            "CORS_ORIGIN": "*",
            "CORS_ORIGINS": "*",
            "CORS_ALLOW_ALL_ORIGINS": "True",
            "ALLOWED_HOSTS": "*",
        }
        for b_cfg in backend_configs:
            for k, v in default_backend_secrets.items():
                if k not in b_cfg.env_vars:
                    b_cfg.env_vars[k] = v

        # If frontend expects a backend port and it's free, pin it now before backend starts
        if backend_configs and frontend_configs:
            for f_cfg in frontend_configs:
                conn_info = ConnectionBridge.analyze_frontend(Path(f_cfg.workspace_path))
                if conn_info.expected_backend_port and is_port_available(conn_info.expected_backend_port):
                    for b_cfg in backend_configs:
                        b_cfg.pinned_port = conn_info.expected_backend_port
                        if conn_info.expected_backend_port not in b_cfg.detector_result.expected_ports:
                            b_cfg.detector_result.expected_ports.insert(0, conn_info.expected_backend_port)
                    break

        active_backends = []
        
        # 2. Build and start Backends FIRST (if any)
        if backend_configs:
            typer.echo("\n-> Building & Starting Backend Services")
            for b_cfg in backend_configs:
                typer.echo(f"Building [{b_cfg.detector_result.sub_path}]...")
                if not Runner.install_dependencies(b_cfg):
                    typer.echo(f"[-] Failed to build Docker image for {b_cfg.detector_result.sub_path}")
                    return
                typer.echo("[+] Done")
                
                b_manager = ProcessManager(b_cfg)
                process_managers.append(b_manager)
                if not b_manager.start():
                    typer.echo(f"[-] Failed to start container for {b_cfg.detector_result.sub_path}.")
                    return
                    
                b_ports = b_manager.get_listening_ports()
                if not b_ports:
                    typer.echo(f"[-] No listening port detected for {b_cfg.detector_result.sub_path} within timeout.")
                    return
                    
                candidate_paths = list(b_cfg.detector_result.api_endpoints)
                if b_cfg.detector_result.docs_url:
                    candidate_paths.insert(0, b_cfg.detector_result.docs_url)

                target_port = verify_http_ports(
                    b_ports,
                    container_name=b_manager.container_name,
                    is_compose=b_manager.is_compose,
                    workspace_path=b_cfg.workspace_path,
                    candidate_paths=candidate_paths,
                )
                if target_port:
                    b_manager.detected_ports = [target_port]
                    active_backends.append({"sub_path": b_cfg.detector_result.sub_path, "port": target_port})
                    working_docs = find_working_docs_url(
                        target_port,
                        [b_cfg.detector_result.docs_url] if b_cfg.detector_result.docs_url else []
                    )
                    if working_docs:
                        b_cfg.detector_result.docs_url = working_docs
                    typer.echo(f"[+] Backend [{b_cfg.detector_result.sub_path}] verified on port {target_port}")
                else:
                    typer.echo(f"[-] Backend {b_cfg.detector_result.sub_path} failed HTTP health check.")
                    return

        # 3. Configure Frontends with actual running backend port, then Build and Start Frontends
        if frontend_configs:
            if active_backends:
                actual_backend_port = active_backends[0]["port"]
                b_localhost = f"http://localhost:{actual_backend_port}"
                typer.echo(f"\n-> Bridging Frontend(s) with Backend on port {actual_backend_port}")
                
                for f_cfg in frontend_configs:
                    conn_info = ConnectionBridge.analyze_frontend(Path(f_cfg.workspace_path))
                    strategy = ConnectionBridge.determine_strategy(
                        conn_info,
                        is_port_available(conn_info.expected_backend_port) if conn_info.expected_backend_port else False,
                        actual_backend_port=actual_backend_port,
                    )
                    typer.echo(f"  [{f_cfg.detector_result.sub_path}] Strategy: {strategy.description}")
                    
                    # Apply source rewrite if frontend expected another port
                    if strategy.name == "source_rewrite" and strategy.source_rewrite_from and strategy.source_rewrite_to:
                        f_cfg.detector_result.source_rewrite_from = strategy.source_rewrite_from
                        f_cfg.detector_result.source_rewrite_to = strategy.source_rewrite_to
                        f_cfg.source_rewrite_from = strategy.source_rewrite_from
                        f_cfg.source_rewrite_to = strategy.source_rewrite_to
                    elif conn_info.expected_backend_port and conn_info.expected_backend_port != actual_backend_port:
                        f_cfg.detector_result.source_rewrite_from = str(conn_info.expected_backend_port)
                        f_cfg.detector_result.source_rewrite_to = str(actual_backend_port)
                        f_cfg.source_rewrite_from = str(conn_info.expected_backend_port)
                        f_cfg.source_rewrite_to = str(actual_backend_port)
                        
                    # Inject standard API env vars into frontend
                    api_envs = {
                        "VITE_API_URL": b_localhost,
                        "VITE_BACKEND_URL": b_localhost,
                        "REACT_APP_API_URL": b_localhost,
                        "REACT_APP_BACKEND_URL": b_localhost,
                        "NEXT_PUBLIC_API_URL": b_localhost,
                        "API_URL": b_localhost,
                        "BACKEND_URL": b_localhost,
                        "API_BASE_URL": b_localhost,
                        "SERVER_URL": b_localhost,
                    }
                    if conn_info.env_var_for_api:
                        api_envs[conn_info.env_var_for_api] = b_localhost
                    for k, v in api_envs.items():
                        if k not in f_cfg.env_vars:
                            f_cfg.env_vars[k] = v

            typer.echo("\n-> Building & Starting Frontend / Application Services")
            for f_cfg in frontend_configs:
                typer.echo(f"Building [{f_cfg.detector_result.sub_path}]...")
                if not Runner.install_dependencies(f_cfg):
                    typer.echo(f"[-] Failed to build Docker image for {f_cfg.detector_result.sub_path}")
                    return
                typer.echo("[+] Done")
                
                f_manager = ProcessManager(f_cfg)
                process_managers.append(f_manager)
                if not f_manager.start():
                    typer.echo(f"[-] Failed to start container for {f_cfg.detector_result.sub_path}.")
                    return
                    
                f_ports = f_manager.get_listening_ports()
                if not f_ports:
                    typer.echo(f"[-] No listening port detected for {f_cfg.detector_result.sub_path} within timeout.")
                    return
                    
                target_port = verify_http_ports(
                    f_ports,
                    container_name=f_manager.container_name,
                    is_compose=f_manager.is_compose,
                    workspace_path=f_cfg.workspace_path,
                )
                if target_port:
                    f_manager.detected_ports = [target_port]
                    typer.echo(f"[+] Service [{f_cfg.detector_result.sub_path}] verified on port {target_port}")
                else:
                    typer.echo(f"[-] Service {f_cfg.detector_result.sub_path} failed HTTP health check.")
                    return

        # Keep configs in sync with process_managers for tunnels and display
        configs = backend_configs + frontend_configs
                
        # Create public tunnels if enabled
        if not no_tunnel:
            typer.echo("\n-> Creating public tunnel")
            for config, manager in zip(configs, process_managers):
                if manager.detected_ports:
                    tunnel = TunnelManager(port=manager.detected_ports[0])
                    if tunnel.start():
                        tunnel_managers.append(tunnel)
                        manager.public_url = tunnel.public_url
                        typer.echo(f"[+] Tunnel established: {tunnel.public_url}")
                    else:
                        typer.echo(f"[-] Warning: Failed to create public tunnel for port {manager.detected_ports[0]}.")

        typer.echo("\n" + "=" * 56)
        typer.echo("[●] APPLICATION IS LIVE")
        typer.echo("=" * 56)
        
        for config, manager in zip(configs, process_managers):
            local_url = f"http://localhost:{manager.detected_ports[0]}"
            pub_url = getattr(manager, "public_url", None)
            is_api = config.detector_result.is_backend_api
            tag = " (Backend API)" if is_api else ""
            
            typer.echo(f"\nService: [{config.detector_result.sub_path}] ({config.detector_result.framework}{tag})")
            if pub_url:
                typer.echo(f"  PUBLIC URL:  {pub_url}")
            typer.echo(f"  LOCAL URL:   {local_url}")

            if config.detector_result.framework == "Django":
                typer.echo("  DEMO AUTH:   admin / admin123  (Superuser seeded automatically)")

            docs_subpath = config.detector_result.docs_url
            if docs_subpath and is_api:
                docs_local = f"{local_url}{docs_subpath}"
                docs_pub = f"{pub_url}{docs_subpath}" if pub_url else ""
                docs_str = f"  API DOCS:    {docs_local}"
                if docs_pub:
                    docs_str += f"  (Public: {docs_pub})"
                typer.echo(docs_str)

            if config.detector_result.api_endpoints and is_api:
                typer.echo(f"  Discovered Endpoints:")
                for ep in config.detector_result.api_endpoints[:10]:
                    typer.echo(f"    - {ep}")
                if len(config.detector_result.api_endpoints) > 10:
                    typer.echo(f"    - ... and {len(config.detector_result.api_endpoints) - 10} more")
        
        # Select best URL to open in browser:
        # 1. Prefer interactive Frontend UI if available
        # 2. If Backend-only, open verified API documentation
        # 3. Fallback to base local URL
        browser_target_url = None
        frontend_pair = next(
            ((c, m) for c, m in zip(configs, process_managers) if not c.detector_result.is_backend_api and m.detected_ports),
            None
        )
        if frontend_pair:
            f_cfg, f_mgr = frontend_pair
            browser_target_url = f"http://localhost:{f_mgr.detected_ports[0]}"
        elif configs and process_managers and process_managers[0].detected_ports:
            b_cfg, b_mgr = configs[0], process_managers[0]
            b_base = f"http://localhost:{b_mgr.detected_ports[0]}"
            if b_cfg.detector_result.is_backend_api and b_cfg.detector_result.docs_url:
                browser_target_url = f"{b_base}{b_cfg.detector_result.docs_url}"
            elif b_cfg.detector_result.is_backend_api and b_cfg.detector_result.api_endpoints:
                first_ep = b_cfg.detector_result.api_endpoints[0].split()[-1]
                browser_target_url = f"{b_base}{first_ep}"
            else:
                browser_target_url = b_base

        typer.echo(f"\nSession duration: {duration}")
        typer.echo("=" * 56)
        
        # Automatically launch in default browser
        if open_browser and browser_target_url:
            typer.echo(f"\nOpening {browser_target_url} in your browser...")
            try:
                webbrowser.open(browser_target_url)
            except Exception:
                pass

        total_seconds = parse_duration(duration)
        start_wait = time.time()
        try:
            typer.echo("Press Ctrl+C to stop hosting.\n")
            while time.time() - start_wait < total_seconds:
                remaining = int(total_seconds - (time.time() - start_wait))
                hrs = remaining // 3600
                mins = (remaining % 3600) // 60
                secs = remaining % 60
                print(f"\r  Expires in: {hrs:02d}:{mins:02d}:{secs:02d} ", end="", flush=True)
                time.sleep(1)
            typer.echo("\nSession expired.")
        except KeyboardInterrupt:
            typer.echo("\n\nStopping application...")
            
    except Exception as e:
        typer.echo(f"\n[-] Error: {e}")
    finally:
        for tunnel in tunnel_managers:
            tunnel.stop()
            
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
