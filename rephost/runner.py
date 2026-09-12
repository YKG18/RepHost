import http.server,socketserver,threading,subprocess
from dataclasses import dataclass
from pathlib import Path
@dataclass
class RunningServer:
    process:subprocess.Popen|None; thread:threading.Thread|None; server:socketserver.TCPServer|None; url:str
    def stop(self):
        if self.server:self.server.shutdown();self.server.server_close()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(5)
            except subprocess.TimeoutExpired:self.process.kill()
        if self.thread:self.thread.join(2)
def start_static_server(root:Path,host='127.0.0.1',port=8080):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self,*a,**k):super().__init__(*a,directory=str(root),**k)
        def log_message(self,*a):pass
    s=socketserver.ThreadingTCPServer((host,port),H);t=threading.Thread(target=s.serve_forever,daemon=True);t.start();return RunningServer(None,t,s,f'http://{host}:{s.server_address[1]}')
