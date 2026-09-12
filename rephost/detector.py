import json
import re
from pathlib import Path
from .core import Project

IGNORED_DIRS={'.git','.github','node_modules','venv','.venv','__pycache__','dist','build','.next','target'}


def _find_compose_file(root):
    for name in ('compose.yml','compose.yaml','docker-compose.yml','docker-compose.yaml'):
        p=root/name
        if p.is_file():
            return p
    return None

def _find_index(root):
    p=root/'index.html'
    if p.is_file(): return p
    c=[x for x in root.rglob('index.html') if not any(a in IGNORED_DIRS for a in x.relative_to(root).parts[:-1])]
    return sorted(c,key=lambda x:(len(x.relative_to(root).parts),str(x)))[0] if c else None

def _has_python_dependency(root, package_name):
    for name in ('requirements.txt','requirements-dev.txt','requirements/base.txt','requirements/dev.txt'):
        p=root/name
        if p.is_file() and re.search(rf'(?im)^\s*{re.escape(package_name)}(?:\[[^\]]+\])?(?:\s|[<=>!~])', p.read_text(errors='ignore')):
            return True
    pyproject=root/'pyproject.toml'
    if pyproject.is_file() and re.search(rf'(?i)(["\']{re.escape(package_name)}(?:["\']|[<=>!~]))', pyproject.read_text(errors='ignore')):
        return True
    return False

def _has_flask_dependency(root):
    return _has_python_dependency(root, 'flask')

def _has_fastapi_dependency(root):
    return _has_python_dependency(root, 'fastapi')

def _has_django_dependency(root):
    return _has_python_dependency(root, 'django')

def _has_rails_dependency(root):
    gemfile = root/'Gemfile'
    if not gemfile.is_file():
        return False
    text = gemfile.read_text(errors='ignore')
    return bool(re.search(r"(?im)^\s*gem\s+['\"]rails['\"]", text))

def _find_rails_root(root):
    candidates=[]
    if (root/'Gemfile').is_file() and (root/'config'/'application.rb').is_file():
        candidates.append(root)
    for p in sorted(root.rglob('application.rb')):
        app_root=p.parent.parent
        if app_root in candidates or any(a in IGNORED_DIRS for a in p.relative_to(root).parts[:-1]):
            continue
        if (app_root/'Gemfile').is_file() and (app_root/'config.ru').is_file():
            candidates.append(app_root)
    for app_root in candidates:
        if _has_rails_dependency(app_root) and ((app_root/'bin'/'rails').is_file() or (app_root/'config.ru').is_file()):
            return app_root
    return None

def _find_django_manage(root):
    candidates=[]
    p=root/'manage.py'
    if p.is_file(): candidates.append(p)
    candidates += [p for p in sorted(root.rglob('manage.py')) if p not in candidates and not any(a in IGNORED_DIRS for a in p.relative_to(root).parts[:-1])]
    for p in candidates:
        text=p.read_text(errors='ignore')
        if 'django' in text.lower() and 'DJANGO_SETTINGS_MODULE' in text:
            return p
    return None

def _find_flask_entry(root):
    for name in ('app.py','wsgi.py','run.py','hello.py','main.py'):
        p=root/name
        if p.is_file():
            text=p.read_text(errors='ignore')
            if 'from flask import' in text or 'import flask' in text or 'Flask(' in text:
                return p
    for p in sorted(root.rglob('*.py')):
        if any(a in IGNORED_DIRS for a in p.relative_to(root).parts[:-1]):
            continue
        text=p.read_text(errors='ignore')
        if 'from flask import' in text and 'Flask(' in text:
            return p
    return None

def _find_fastapi_entry(root):
    candidates=[]
    preferred=('main.py','app.py','server.py','api.py')
    for name in preferred:
        p=root/name
        if p.is_file(): candidates.append(p)
    candidates += [p for p in sorted(root.rglob('*.py')) if p not in candidates and not any(a in IGNORED_DIRS for a in p.relative_to(root).parts[:-1])]
    for p in candidates:
        text=p.read_text(errors='ignore')
        if re.search(r'(?m)^\s*(?:app|application)\s*=\s*FastAPI\s*\(', text) or re.search(r'(?m)^\s*from\s+fastapi\s+import\s+FastAPI', text) and 'FastAPI(' in text:
            m=re.search(r'(?m)^\s*(\w+)\s*=\s*FastAPI\s*\(', text)
            app_name=m.group(1) if m else 'app'
            return p, app_name
    return None


def _find_php_entry(root):
    public = root / 'public'
    if (public / 'index.php').is_file():
        return public / 'index.php'
    if (root / 'index.php').is_file():
        return root / 'index.php'
    candidates = [p for p in sorted(root.rglob('*.php')) if not any(a in IGNORED_DIRS for a in p.relative_to(root).parts[:-1])]
    return candidates[0] if candidates else None

def detect_project(root):
    root=Path(root).resolve()
    package=root/'package.json'; index=_find_index(root)
    compose_file=_find_compose_file(root)
    if compose_file:
        return Project(root,'compose',compose_file,None,8000,{'compose_file': str(compose_file.name)})
    data=None
    if package.is_file():
        try: data=json.loads(package.read_text())
        except: pass
    if data is not None:
        scripts=data.get('scripts',{}); deps={**data.get('dependencies',{}),**data.get('devDependencies',{})}; names={x.lower() for x in deps}
        vite='vite' in names; react='react' in names or 'react-dom' in names
        if vite or 'dev' in scripts or 'start' in scripts:
            script='dev' if 'dev' in scripts else 'start'; kind='react-vite' if vite and react else 'node'
            return Project(root,kind,index,('npm','run',script,'--','--host','0.0.0.0'),5173 if vite else 3000)

    rails_root = _find_rails_root(root)
    if rails_root:
        return Project(rails_root,'rails',rails_root/'Gemfile',('bundle','exec','rails','server','-b','0.0.0.0','-p','3000'),3000)

    php_entry = _find_php_entry(root)
    if php_entry:
        return Project(root,'php',php_entry,None,8000)

    django_manage = _find_django_manage(root) if _has_django_dependency(root) else None
    if django_manage:
        return Project(root,'django',django_manage,('python','manage.py','runserver','0.0.0.0:8000'),8000)

    fastapi_entry = _find_fastapi_entry(root) if _has_fastapi_dependency(root) else None
    if fastapi_entry:
        entry, app_name = fastapi_entry
        rel=entry.relative_to(root).with_suffix('')
        module='.'.join(rel.parts)
        return Project(root,'fastapi',entry,('python','-m','uvicorn',f'{module}:{app_name}','--host','0.0.0.0'),8000)

    flask_entry=_find_flask_entry(root) if _has_flask_dependency(root) else None
    if flask_entry:
        rel=flask_entry.relative_to(root).with_suffix('')
        module='.'.join(rel.parts)
        return Project(root,'flask',flask_entry,('python','-m','flask','--app',module,'run','--host','0.0.0.0'),5000)

    return Project(root,'static',index,None,8080) if index else None
