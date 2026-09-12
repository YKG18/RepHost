from urllib.error import URLError
from urllib.request import urlopen
import time
import threading

def check(url: str, timeout=3.0):
    try:
        with urlopen(url, timeout=timeout) as response:
            # Any HTTP response means the service is reachable. A 404 is a valid
            # response for APIs that intentionally do not expose `/`.
            return response.status < 500, response.status
    except (URLError, OSError):
        return False, None

def start_drain(process):
    output=[]
    if process is None or process.stdout is None:
        return output, None
    def drain():
        for line in iter(process.stdout.readline, ''):
            line=line.rstrip()
            if line:
                output.append(line)
                print(f'    | {line}')
    t=threading.Thread(target=drain, daemon=True); t.start()
    return output, t

def wait_for(url: str, process=None, timeout=120.0, drain_logs=True):
    output=[]
    t=None
    if drain_logs:
        output, t = start_drain(process)
    deadline=time.time()+timeout
    while time.time()<deadline:
        if process is not None and process.poll() is not None:
            t.join(timeout=1); return False,None
        ok,status=check(url)
        if ok: return True,status
        time.sleep(.5)
    return False,None
