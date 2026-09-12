import httpx
import time
from typing import Optional, Tuple

# Paths that commonly serve something more useful than "/" on API-only
# backends (REST APIs, Swagger/OpenAPI docs, etc). Purely used to make the
# "app responded with a non-2xx status at /" message actionable instead of
# leaving the user staring at a bare JSON/HTML error body.
COMMON_ALTERNATE_PATHS = ["/docs", "/api", "/api/docs", "/health", "/api/v1"]


def verify_http_port(port: int, max_retries: int = 25, interval: int = 2) -> Tuple[bool, Optional[int]]:
    """Poll the given local port until it responds to HTTP or we give up.

    Returns (success, last_status_code). A response in [200, 500) counts as
    success - the process is genuinely up and talking HTTP - even if that
    status is a 404/401/etc rather than 200. That distinction matters for
    the caller: many real apps (REST APIs, SPAs with client-side routing)
    have no route at "/" at all, so a 404 there is not itself a failure.
    """
    print(f"Performing health check on port {port}...")
    url = f"http://127.0.0.1:{port}"

    last_status: Optional[int] = None
    for attempt in range(max_retries):
        try:
            response = httpx.get(url, timeout=5.0, follow_redirects=True)
            last_status = response.status_code
            if 200 <= response.status_code < 500:
                print(f"Health check passed for port {port} (Status: {response.status_code})")
                return True, response.status_code
        except httpx.RequestError:
            pass

        print(f"Waiting for server on port {port}...")
        time.sleep(interval)

    print(f"Health check failed for port {port} after {max_retries} attempts.")
    return False, last_status


def probe_alternate_paths(port: int) -> list:
    """Best-effort check of a few common non-root paths, used only to give
    a more useful hint when the root path returned a non-2xx status. Not a
    correctness check - just UX."""
    found = []
    for path in COMMON_ALTERNATE_PATHS:
        try:
            response = httpx.get(f"http://127.0.0.1:{port}{path}", timeout=2.0, follow_redirects=True)
            if response.status_code < 400:
                found.append(path)
        except httpx.RequestError:
            continue
    return found
