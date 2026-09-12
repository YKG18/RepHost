import httpx
import subprocess
import time
from typing import Optional, List


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


def verify_http_ports(
    ports: List[int],
    container_name: Optional[str] = None,
    max_retries: int = 15,
    interval: int = 2,
) -> Optional[int]:
    """Try to reach any of the given localhost ports via HTTP.

    If *container_name* is provided, each iteration checks whether the
    Docker container is still alive.  If it has exited, we fail
    immediately and dump the container logs so the user can see what
    went wrong instead of looping for 30 seconds against dead ports.
    """
    print(f"Performing health check on ports: {ports}...")

    for attempt in range(max_retries):
        # ── Fast-fail: is the container still alive? ──────────────
        if container_name and not _is_container_running(container_name):
            print(f"[!] Container '{container_name}' has stopped unexpectedly.")
            _dump_container_logs(container_name)
            return None

        # ── Probe every mapped port ───────────────────────────────
        for port in ports:
            url = f"http://127.0.0.1:{port}"
            try:
                response = httpx.get(url, timeout=2.0, follow_redirects=True)
                if 200 <= response.status_code < 500:
                    print(f"Health check passed for port {port} (Status: {response.status_code})")
                    return port
            except httpx.RequestError:
                pass

        print(f"Waiting for server to respond on any mapped port... (attempt {attempt + 1}/{max_retries})")
        time.sleep(interval)

    # All retries exhausted
    print(f"Health check failed for all ports after {max_retries} attempts.")
    if container_name:
        _dump_container_logs(container_name)
    return None
