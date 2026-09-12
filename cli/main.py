import argparse,shutil,subprocess,tempfile,re,threading,time
from pathlib import Path
from rephost.detector import detect_project
from rephost.docker import ensure_available,run_node,run_python,run_fastapi,run_django,run_rails,run_php,run_compose,compose_host_port,compose_services_ready,DockerError
from rephost.health import check,wait_for,start_drain
from rephost.runner import start_static_server

def clone(url,dst):
 r=subprocess.run(['git','clone','--depth','1',url,str(dst)],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr.strip() or 'git clone failed')

def main():
 p=argparse.ArgumentParser();p.add_argument('repository');p.add_argument('--port',type=int);a=p.parse_args();w=Path(tempfile.mkdtemp(prefix='rephost-'));srv=None;proc=None;cf_proc=None;cloudflare_url=None
 try:
  repo=w/'repo';print('Rephost\n\n-> Cloning repository...');clone(a.repository,repo);print('[+] Repository cloned\n\n-> Detecting project...');proj=detect_project(repo)
  if not proj:print('[-] No supported project detected');return 1
  print(f'[+] Detected: {proj.kind}')
  port=a.port or proj.port
  if proj.kind=='static':
   srv=start_static_server(proj.root,port=port);ok,status=check(srv.url+'/');url=srv.url
  else:
   print('\n-> Checking Docker...');ensure_available();print('[+] Docker available')
   if proj.kind=='compose':
    print('\n-> Starting multi-service Docker project...')
    port=compose_host_port(proj.root) or port
    proc=run_compose(proj.root)
    # Start draining Compose output immediately so builds/startup never look frozen.
    _, log_thread = start_drain(proc)
   elif proj.kind=='react-vite':
    print('\n-> Starting Node inside Docker...');proc=run_node(proj.root,port)
   elif proj.kind=='flask':
    module='.'.join(proj.entrypoint.relative_to(proj.root).with_suffix('').parts)
    print('\n-> Starting Flask inside Docker...');proc=run_python(proj.root,port,module)
   elif proj.kind=='fastapi':
    target=proj.command[3]
    print('\n-> Starting FastAPI inside Docker...');proc=run_fastapi(proj.root,port,target)
   elif proj.kind=='django':
    print('\n-> Starting Django inside Docker...');proc=run_django(proj.root,port)
   elif proj.kind=='rails':
    print('\n-> Starting Ruby on Rails inside Docker...');proc=run_rails(proj.root,port)
   elif proj.kind=='php':
    print('\n-> Starting PHP inside Docker...');proc=run_php(proj.root,port)
   health_timeout = 300.0 if proj.kind in ('rails','compose') else 120.0
   if proj.kind == 'compose':
    # Databases and other dependencies may need time to become ready before the
    # browser-facing service can answer. Check Compose service state first.
    import time as _time
    deadline=_time.time()+health_timeout
    services_ok=False
    while _time.time()<deadline:
     if proc is not None and proc.poll() is not None:
      break
     try:
      services_ok, detail=compose_services_ready(proj.root)
     except DockerError:
      services_ok=False; detail='Waiting for Compose services...'
     if services_ok:
      print(f'    {detail}')
      break
     _time.sleep(1)
    if not services_ok:
     ok,status=False,None
    else:
     ok,status=wait_for(f'http://127.0.0.1:{port}/',proc,timeout=max(1,deadline-_time.time()),drain_logs=False);url=f'http://127.0.0.1:{port}'
   else:
    ok,status=wait_for(f'http://127.0.0.1:{port}/',proc,timeout=health_timeout);url=f'http://127.0.0.1:{port}'
  if not ok:
   print('[-] Health check failed')
   return 1

  # Start Cloudflare Quick Tunnel for the local server.
  try:
   print('\n-> Starting Cloudflare Quick Tunnel...')
   cf_proc=subprocess.Popen(
    ['cloudflared','tunnel','--url',f'http://127.0.0.1:{port}'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
   )

   def read_cloudflare_output():
    nonlocal cloudflare_url
    for line in cf_proc.stdout:
     match=re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com',line)
     if match:
      cloudflare_url=match.group(0)

   threading.Thread(target=read_cloudflare_output,daemon=True).start()

   for _ in range(30):
    if cloudflare_url or cf_proc.poll() is not None:
     break
    time.sleep(0.5)

   if cloudflare_url:
    print(f'[+] Cloudflare tunnel: {cloudflare_url}')
   else:
    print('[-] Cloudflare Quick Tunnel could not be started')
  except (FileNotFoundError,OSError):
   print('[-] cloudflared not found; skipping Cloudflare Quick Tunnel')

  print(f'[+] Health check passed (HTTP {status})\n\nLocal: {url}')
  if cloudflare_url:
   print(f'Cloudflare: {cloudflare_url}')
  print('Press Ctrl+C to stop.')
  try:(proc.wait() if proc else srv.thread.join())
  except KeyboardInterrupt:pass
  return 0
 except DockerError as e:print(f'[-] Docker error: {e}');return 1
 except Exception as e:print(f'[-] {e}');return 1
 finally:
  if srv:srv.stop()
  if proc and proc.poll() is None:proc.terminate()
  if cf_proc and cf_proc.poll() is None:cf_proc.terminate()
  if 'proj' in locals() and proj.kind=='compose':
   import subprocess as _sp
   _sp.run(['docker','compose','-p','rephost-'+proj.root.name.lower().replace('_','-')[:40],'down','--remove-orphans'],cwd=proj.root,capture_output=True,text=True)
  shutil.rmtree(w,ignore_errors=True)
if __name__=='__main__':raise SystemExit(main())
