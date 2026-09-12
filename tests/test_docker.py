from pathlib import Path
from unittest.mock import patch
from rephost import docker
from rephost.docker import run_django

def test_python_command_uses_bind_mount_and_flask(monkeypatch, tmp_path):
    captured={}
    class Dummy:
        pass
    monkeypatch.setattr(docker.subprocess, 'run', lambda *a, **k: Dummy())
    monkeypatch.setattr(docker, '_start', lambda cmd, image: captured.update(cmd=cmd,image=image) or 'process')
    (tmp_path/'requirements.txt').write_text('Flask\n')
    result=docker.run_python(tmp_path,5000,'app')
    assert result=='process'
    cmd=captured['cmd']
    assert '--mount' in cmd
    assert 'type=bind' in cmd[cmd.index('--mount')+1]
    assert 'python:3.12-slim' in cmd
    assert 'flask --app app' in cmd[-1]


def test_fastapi_command_uses_bind_mount_and_uvicorn(monkeypatch, tmp_path):
    captured={}
    class Dummy: pass
    monkeypatch.setattr(docker.subprocess, 'run', lambda *a, **k: Dummy())
    monkeypatch.setattr(docker, '_start', lambda cmd, image: captured.update(cmd=cmd,image=image) or 'process')
    (tmp_path/'requirements.txt').write_text('fastapi\n')
    result=docker.run_fastapi(tmp_path,8000,'main:app')
    assert result=='process'
    cmd=captured['cmd']
    assert '--mount' in cmd
    assert 'type=bind' in cmd[cmd.index('--mount')+1]
    assert 'python:3.12-slim' in cmd
    assert 'uvicorn main:app' in cmd[-1]


def test_django_command():
    root = Path('C:/repo')
    with patch('subprocess.run') as run, patch('subprocess.Popen') as popen:
        run.return_value.returncode = 0
        run_django(root, 8000)
        cmd = popen.call_args.args[0]
        assert 'rephost-django' in cmd
        assert 'python manage.py runserver 0.0.0.0:8000' in cmd[-1]


def test_rails_command_uses_ruby_and_bundle(monkeypatch, tmp_path):
    captured={}
    class Dummy: pass
    monkeypatch.setattr(docker.subprocess, 'run', lambda *a, **k: Dummy())
    monkeypatch.setattr(docker, '_start', lambda cmd, image: captured.update(cmd=cmd,image=image) or 'process')
    (tmp_path/'Gemfile').write_text("gem 'rails'\n")
    (tmp_path/'.ruby-version').write_text('3.3.6\n')
    (tmp_path/'Gemfile.lock').write_text('BUNDLED WITH\n   2.6.2\n')
    result=docker.run_rails(tmp_path,3000)
    assert result=='process'
    cmd=captured['cmd']
    assert '--mount' in cmd
    assert 'type=bind' in cmd[cmd.index('--mount')+1]
    assert 'ruby:3.3.6-bookworm' in cmd
    assert 'gem install bundler -v 2.6.2' in cmd[-1]
    assert 'bundle exec rails server -b 0.0.0.0 -p 3000' in cmd[-1]

def test_php_docker_command(monkeypatch, tmp_path):
    import rephost.docker as d
    calls=[]
    class P:
        def poll(self): return None
    monkeypatch.setattr(d.subprocess, 'run', lambda *a, **k: type('R', (), {'returncode':0})())
    monkeypatch.setattr(d.subprocess, 'Popen', lambda *a, **k: calls.append(a[0]) or P())
    d.run_php(tmp_path, 8000)
    cmd=calls[0]
    assert 'composer:2' in cmd
    assert '-p' in cmd and '8000:8000' in cmd
    assert 'php -S 0.0.0.0:8000 -t .' in cmd[-1]


def test_compose_command_exists():
    from rephost.docker import run_compose
    assert callable(run_compose)


def test_compose_host_port_uses_absolute_compose_path(monkeypatch, tmp_path):
    compose = tmp_path / 'docker-compose.yml'
    compose.write_text('services:\n  web:\n    image: nginx\n    ports:\n      - "8080:80"\n')
    captured = {}
    class Dummy:
        stdout = '{"services":{"web":{"ports":[{"target":80,"published":8080}]}}}'
    def fake_run(args):
        captured['args'] = args
        return Dummy()
    monkeypatch.setattr(docker, '_run', fake_run)
    assert docker.compose_host_port(tmp_path) == 8080
    assert captured['args'][captured['args'].index('-f') + 1] == str(compose)


def test_compose_port_prefers_frontend_port(monkeypatch, tmp_path):
    import json
    from rephost import docker
    (tmp_path / "docker-compose.yml").write_text("services: {}")
    class R:
        returncode = 0
        stdout = json.dumps({"services": {
            "db": {"ports": [{"published": 5432, "target": 5432}]},
            "backend": {"ports": [{"published": 8000, "target": 8000}]},
            "frontend": {"ports": [{"published": 3000, "target": 8080}]}
        }})
        stderr = ""
    monkeypatch.setattr(docker, "_run", lambda args: R())
    assert docker.compose_host_port(tmp_path) == 3000


def test_compose_services_ready_accepts_running_services(monkeypatch, tmp_path):
    from rephost import docker
    compose=tmp_path/'docker-compose.yml'
    compose.write_text('services: {}')
    class R:
        returncode=0
        stdout='[{"Service":"db","State":"running","Health":"healthy"},{"Service":"web","State":"running","Health":""}]'
        stderr=''
    monkeypatch.setattr(docker, '_run', lambda args: R())
    ok, detail=docker.compose_services_ready(tmp_path)
    assert ok is True
    assert 'running' in detail

def test_compose_services_ready_rejects_exited_database(monkeypatch, tmp_path):
    from rephost import docker
    compose=tmp_path/'docker-compose.yml'
    compose.write_text('services: {}')
    class R:
        returncode=0
        stdout='[{"Service":"db","State":"exited","Health":""}]'
        stderr=''
    monkeypatch.setattr(docker, '_run', lambda args: R())
    ok, detail=docker.compose_services_ready(tmp_path)
    assert ok is False
    assert 'db' in detail


def test_compose_services_ready_allows_starting_health(monkeypatch, tmp_path):
    compose=tmp_path/'docker-compose.yml'
    compose.write_text('services: {}')
    class R:
        returncode=0
        stdout='[{"Service":"db","State":"running","Health":"starting"}]'
        stderr=''
    monkeypatch.setattr(docker, '_run', lambda args: R())
    ok, detail=docker.compose_services_ready(tmp_path)
    assert ok is True
