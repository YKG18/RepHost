import os
import httpx
import subprocess
import time
from typing import Optional, List

# Ensure Docker binaries are available in PATH
for docker_bin in [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin"),
    r"C:\Program Files\Docker\Docker\resources\bin",
]:
    if os.path.exists(docker_bin) and docker_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = docker_bin + os.pathsep + os.environ.get("PATH", "")


def _is_container_running(container_name: str) -> bool:
    """Check if a Docker container is still in 'running' state."""
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Status}}", container_name],
        capture_output=True, text=True
    )
    return result.returncode == 0 and result.stdout.strip() == "running"


def _dump_container_logs(container_name: str):
    """Print the last 30 lines of container logs for debugging."""
    result = subprocess.run(
        ["docker", "logs", "--tail", "30", container_name],
        capture_output=True, text=True
    )
    output = (result.stdout + result.stderr).strip()
    if output:
        print("\n  --- Container logs ---")
        for line in output.splitlines():
            print(f"  {line}")
        print("  --- End of logs ---\n")


def _is_compose_running(workspace_path: str) -> bool:
    """Check if at least one container in the compose project is running."""
    try:
        cmd = ["docker", "compose", "ps", "--status", "running", "-q"]
        res = subprocess.run(cmd, cwd=workspace_path, capture_output=True, text=True)
        if res.returncode != 0:
            cmd = ["docker-compose", "ps", "-q"]
            res = subprocess.run(cmd, cwd=workspace_path, capture_output=True, text=True)
        return bool(res.stdout.strip())
    except Exception:
        return True


def _dump_compose_logs(workspace_path: str):
    """Print the last 30 lines of compose logs."""
    try:
        cmd = ["docker", "compose", "logs", "--tail", "30"]
        res = subprocess.run(cmd, cwd=workspace_path, capture_output=True, text=True)
        if res.returncode != 0:
            cmd = ["docker-compose", "logs", "--tail", "30"]
            res = subprocess.run(cmd, cwd=workspace_path, capture_output=True, text=True)
        output = (res.stdout + res.stderr).strip()
        if output:
            print("\n  --- Compose logs ---")
            for line in output.splitlines():
                print(f"  {line}")
            print("  --- End of logs ---\n")
    except Exception:
        pass


def _get_latest_log_line(workspace_path: Optional[str], container_name: Optional[str], is_compose: bool) -> Optional[str]:
    try:
        if is_compose and workspace_path:
            cmd = ["docker", "compose", "logs", "--tail", "1"]
            res = subprocess.run(cmd, cwd=workspace_path, capture_output=True, text=True)
            if res.returncode != 0:
                cmd = ["docker-compose", "logs", "--tail", "1"]
                res = subprocess.run(cmd, cwd=workspace_path, capture_output=True, text=True)
        elif container_name and not is_compose:
            cmd = ["docker", "logs", "--tail", "1", container_name]
            res = subprocess.run(cmd, capture_output=True, text=True)
        else:
            return None
        out = (res.stdout + res.stderr).strip()
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        return lines[-1] if lines else None
    except Exception:
        return None


def verify_http_ports(
    ports: List[int],
    container_name: Optional[str] = None,
    is_compose: bool = False,
    workspace_path: Optional[str] = None,
    candidate_paths: Optional[List[str]] = None,
    max_retries: Optional[int] = None,
    interval: int = 2,
) -> Optional[int]:
    """Try to reach any of the given localhost ports via HTTP.

    If *container_name* is provided (or *is_compose* with *workspace_path*),
    each iteration checks whether the process/container is still alive.
    If it has exited, we fail immediately and dump the logs.
    """
    if max_retries is None:
        # Multi-container/compose services (databases + in-container package installs)
        # require up to 120-140s on first boot. Single containers need ~60-70s.
        max_retries = 70 if is_compose else 35

    print(f"Performing health check on ports: {ports}...")

    clean_candidate_paths = []
    if candidate_paths:
        for cp in candidate_paths:
            if not cp:
                continue
            path_part = cp.split()[-1]  # In case format is "GET /path"
            if not path_part.startswith("/"):
                path_part = f"/{path_part}"
            if path_part not in clean_candidate_paths:
                clean_candidate_paths.append(path_part)

    for attempt in range(max_retries):
        # ── Fast-fail: is the container/compose project still alive? ──
        if is_compose and workspace_path:
            if not _is_compose_running(workspace_path):
                print(f"[!] Docker Compose services have stopped unexpectedly.")
                _dump_compose_logs(workspace_path)
                return None
        elif container_name and not is_compose and not _is_container_running(container_name):
            print(f"[!] Container '{container_name}' has stopped unexpectedly.")
            _dump_container_logs(container_name)
            return None

        # ── Probe every mapped port ───────────────────────────────
        for port in ports:
            url = f"http://127.0.0.1:{port}"
            try:
                response = httpx.get(url, timeout=2.0, follow_redirects=True)
                if 200 <= response.status_code < 400:
                    print(f"Health check passed for port {port} (Status: {response.status_code})")
                    return port
                elif response.status_code in (401, 403, 404, 405):
                    # Pure API backend: root might not have an index route. Probe candidate API paths.
                    for cp in clean_candidate_paths:
                        try:
                            cp_resp = httpx.get(f"{url}{cp}", timeout=2.0, follow_redirects=True)
                            if 200 <= cp_resp.status_code < 400:
                                print(f"Health check passed for port {port} (Endpoint {cp}, Status: {cp_resp.status_code})")
                                return port
                        except httpx.RequestError:
                            pass
                    # If candidate paths didn't return 2xx, server still actively returned HTTP response
                    print(f"Health check passed for port {port} (Server active, Status: {response.status_code})")
                    return port
                elif 400 <= response.status_code < 500:
                    print(f"Health check passed for port {port} (Status: {response.status_code})")
                    return port
            except httpx.RequestError:
                # If root failed, probe candidate paths in case root is strictly rejected
                for cp in clean_candidate_paths:
                    try:
                        cp_resp = httpx.get(f"{url}{cp}", timeout=2.0, follow_redirects=True)
                        if 200 <= cp_resp.status_code < 500:
                            print(f"Health check passed for port {port} (Endpoint {cp}, Status: {cp_resp.status_code})")
                            return port
                    except httpx.RequestError:
                        pass

        # Progress display with live container status every 5 attempts
        if (attempt + 1) % 5 == 0:
            latest = _get_latest_log_line(workspace_path, container_name, is_compose)
            if latest:
                print(f"Waiting for server... ({attempt + 1}/{max_retries}) | Log: {latest[:80]}")
            else:
                print(f"Waiting for server to respond on any mapped port... ({attempt + 1}/{max_retries})")
        else:
            print(f"Waiting for server to respond on any mapped port... (attempt {attempt + 1}/{max_retries})")

        time.sleep(interval)

    # All retries exhausted
    print(f"Health check failed for all ports after {max_retries} attempts.")
    if is_compose and workspace_path:
        _dump_compose_logs(workspace_path)
    elif container_name and not is_compose:
        _dump_container_logs(container_name)
    return None


def find_working_docs_url(port: int, candidate_docs: Optional[List[str]] = None) -> Optional[str]:
    """
    Probes candidate and well-known API documentation paths to discover
    which path actually returns HTTP 200/3xx on the running server.
    Guarantees the user/browser never receives a 404 docs link.
    """
    candidates = []
    if candidate_docs:
        for c in candidate_docs:
            if c:
                clean = c.strip()
                if not clean.startswith("/"):
                    clean = f"/{clean}"
                if clean not in candidates:
                    candidates.append(clean)

    common_docs_paths = [
        "/docs",
        "/swagger-ui",
        "/swagger-ui/",
        "/swagger-ui/index.html",
        "/swagger",
        "/swagger/",
        "/swagger/index.html",
        "/swagger-ui.html",
        "/api/docs",
        "/apidocs",
        "/api/documentation",
        "/openapi.json",
        "/redoc",
        "/api",
    ]
    for p in common_docs_paths:
        if p not in candidates:
            candidates.append(p)

    for path in candidates:
        url = f"http://127.0.0.1:{port}{path}"
        try:
            resp = httpx.get(url, timeout=1.5, follow_redirects=True)
            if 200 <= resp.status_code < 400:
                final_path = resp.url.path.lower()
                # If redirected to a login/auth page, this is NOT a documentation URL
                if any(x in final_path for x in ["login", "signin", "auth", "register", "signup"]):
                    continue
                content = resp.text.lower()
                is_docs = any(x in content for x in ["swagger", "openapi", "redoc", "api documentation", "api docs", "swagger-ui", "rapidoc"])
                is_json = resp.headers.get("content-type", "").startswith("application/json")
                if is_docs or is_json:
                    return path
        except httpx.RequestError:
            pass

    return None

