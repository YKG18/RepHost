from pathlib import Path
from rephost.detector import detect_project

def test_detect_react_vite(tmp_path):
    (tmp_path/'package.json').write_text('{"scripts":{"dev":"vite"},"dependencies":{"react":"latest","vite":"latest"}}')
    (tmp_path/'index.html').write_text('<!doctype html>')
    p=detect_project(tmp_path)
    assert p.kind=='react-vite'
    assert p.port==5173

def test_detect_flask(tmp_path):
    (tmp_path/'requirements.txt').write_text('Flask==3.1.0\n')
    (tmp_path/'app.py').write_text('from flask import Flask\napp=Flask(__name__)\n')
    p=detect_project(tmp_path)
    assert p.kind=='flask'
    assert p.port==5000
    assert p.command[:4]==('python','-m','flask','--app')

def test_detect_static(tmp_path):
    (tmp_path/'index.html').write_text('<html></html>')
    p=detect_project(tmp_path)
    assert p.kind=='static'
    assert p.port==8080


def test_detect_fastapi(tmp_path):
    (tmp_path/'requirements.txt').write_text('fastapi==0.116.0\n')
    (tmp_path/'main.py').write_text('from fastapi import FastAPI\napp = FastAPI()\n')
    p=detect_project(tmp_path)
    assert p.kind=='fastapi'
    assert p.port==8000
    assert p.entrypoint.name=='main.py'

def test_detect_fastapi_nested_app(tmp_path):
    (tmp_path/'requirements.txt').write_text('fastapi\nuvicorn\n')
    app=tmp_path/'app'; app.mkdir()
    (app/'__init__.py').write_text('')
    (app/'main.py').write_text('from fastapi import FastAPI\napplication = FastAPI()\n')
    p=detect_project(tmp_path)
    assert p.kind=='fastapi'
    assert p.entrypoint == app/'main.py'


def test_detect_fastapi_standard_extra(tmp_path):
    (tmp_path/'requirements.txt').write_text('fastapi[standard]==0.116.0\n')
    (tmp_path/'main.py').write_text('from fastapi import FastAPI\napp = FastAPI()\n')
    p=detect_project(tmp_path)
    assert p.kind=='fastapi'


def test_detect_django(tmp_path):
    (tmp_path / 'requirements.txt').write_text('Django==5.1.6\n')
    (tmp_path / 'manage.py').write_text("os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')\nimport django\n")
    project = detect_project(tmp_path)
    assert project.kind == 'django'
    assert project.port == 8000


def test_detect_rails(tmp_path):
    (tmp_path/'Gemfile').write_text("source 'https://rubygems.org'\ngem 'rails', '~> 8.0'\n")
    (tmp_path/'config').mkdir()
    (tmp_path/'config'/'application.rb').write_text('module Sample\n class Application < Rails::Application\n end\nend\n')
    (tmp_path/'config.ru').write_text('run Rails.application\n')
    (tmp_path/'bin').mkdir()
    (tmp_path/'bin'/'rails').write_text('#!/usr/bin/env ruby\n')
    p=detect_project(tmp_path)
    assert p.kind=='rails'
    assert p.port==3000
    assert p.root==tmp_path.resolve()

def test_detect_php(tmp_path):
    (tmp_path / 'index.php').write_text('<?php echo "PHP";')
    p = detect_project(tmp_path)
    assert p.kind == 'php'
    assert p.port == 8000


def test_detect_php_public_entry(tmp_path):
    public = tmp_path / 'public'
    public.mkdir()
    (public / 'index.php').write_text('<?php echo "PHP";')
    p = detect_project(tmp_path)
    assert p.kind == 'php'
    assert p.entrypoint == public / 'index.php'


def test_detects_compose(tmp_path):
    (tmp_path / "compose.yml").write_text("services:\n  web:\n    image: nginx\n")
    from rephost.detector import detect_project
    assert detect_project(tmp_path).kind == "compose"
