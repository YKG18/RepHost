from urllib.request import urlopen
from rephost.runner import start_static_server
def test_static_server(tmp_path):
 (tmp_path/'index.html').write_text('Layer 2');s=start_static_server(tmp_path,port=0)
 try:
  with urlopen(s.url+'/') as r:assert r.status==200 and b'Layer 2' in r.read()
 finally:s.stop()
