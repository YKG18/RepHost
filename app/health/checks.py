import httpx
import time
from typing import Optional

def verify_http_port(port: int, max_retries: int = 15, interval: int = 2) -> bool:
    print(f"Performing health check on port {port}...")
    url = f"http://127.0.0.1:{port}"
    
    for attempt in range(max_retries):
        try:
            response = httpx.get(url, timeout=5.0, follow_redirects=True)
            if 200 <= response.status_code < 500:
                print(f"Health check passed for port {port} (Status: {response.status_code})")
                return True
        except httpx.RequestError:
            pass
            
        print(f"Waiting for server on port {port}...")
        time.sleep(interval)
        
    print(f"Health check failed for port {port} after {max_retries} attempts.")
    return False
