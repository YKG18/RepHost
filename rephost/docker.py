import subprocess
from pathlib import Path

class DockerError(RuntimeError):
    pass

def _run(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError:
        raise DockerError('Docker CLI was not found.')
    if result.returncode != 0:
        output = (result.stderr or result.stdout).strip()
        raise DockerError(output or f'Docker command failed: {" ".join(args)}')
    return result

def ensure_available():
    return _run(['docker', 'info'])

def _start(cmd, image):
    print(f'    Container: {image}')
    print('    Installing dependencies and starting application...')
    try:
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
    except FileNotFoundError:
        raise DockerError('Docker CLI was not found.')

def run_python(root: Path, port: int, module: str):
    subprocess.run(['docker','rm','-f','rephost-python'], capture_output=True, text=True)
    source = str(root.resolve())
    requirements = root / 'requirements.txt'
    if requirements.is_file():
        install = 'python -m pip install --no-cache-dir -r requirements.txt'
    else:
        install = 'python -m pip install --no-cache-dir Flask'
    cmd = [
        'docker','run','--rm','--name','rephost-python',
        '--mount',f'type=bind,source={source},target=/app',
        '-w','/app','-p',f'{port}:{port}','python:3.12-slim',
        'bash','-lc',f'{install} && python -m flask --app {module} run --host 0.0.0.0 --port {port}'
    ]
    # The entrypoint is supplied through the environment so shell quoting stays simple.
    return _start(cmd, 'python:3.12-slim')

def run_node(root: Path, port: int):
    subprocess.run(['docker','rm','-f','rephost-node'], capture_output=True, text=True)
    source = str(root.resolve())
    cmd = [
        'docker','run','--rm','--name','rephost-node',
        '--mount',f'type=bind,source={source},target=/app',
        '-w','/app','-p',f'{port}:{port}','node:22-bookworm',
        'bash','-lc',f'npm install && npm run dev -- --host 0.0.0.0 --port {port}'
    ]
    print('    Container: node:22-bookworm')
    print('    Installing dependencies and starting dev server...')
    try:
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
    except FileNotFoundError:
        raise DockerError('Docker CLI was not found.')

def run_fastapi(root: Path, port: int, target: str):
    subprocess.run(['docker','rm','-f','rephost-fastapi'], capture_output=True, text=True)
    source = str(root.resolve())
    requirements = root / 'requirements.txt'
    if requirements.is_file():
        install = 'python -m pip install --no-cache-dir -r requirements.txt'
    else:
        install = 'python -m pip install --no-cache-dir "fastapi[standard]"'
    cmd = [
        'docker','run','--rm','--name','rephost-fastapi',
        '--mount',f'type=bind,source={source},target=/app',
        '-w','/app','-p',f'{port}:{port}','python:3.12-slim',
        'bash','-lc',f'{install} && python -m pip install --no-cache-dir uvicorn && python -m uvicorn {target} --host 0.0.0.0 --port {port}'
    ]
    return _start(cmd, 'python:3.12-slim')


def run_django(root: Path, port: int):
    subprocess.run(['docker','rm','-f','rephost-django'], capture_output=True, text=True)
    source = str(root.resolve())
    requirements = root / 'requirements.txt'
    if requirements.is_file():
        install = 'python -m pip install --no-cache-dir -r requirements.txt'
    else:
        install = 'python -m pip install --no-cache-dir Django'
    cmd = [
        'docker','run','--rm','--name','rephost-django',
        '--mount',f'type=bind,source={source},target=/app',
        '-w','/app','-p',f'{port}:{port}','python:3.12-slim',
        'bash','-lc',f'{install} && python manage.py runserver 0.0.0.0:{port}'
    ]
    return _start(cmd, 'python:3.12-slim')


def _rails_ruby_version(root: Path) -> str:
    for filename in ('.ruby-version',):
        p = root / filename
        if p.is_file():
            value = p.read_text(errors='ignore').strip().splitlines()[0].strip()
            value = value.removeprefix('ruby-')
            if value:
                return value
    lock = root / 'Gemfile.lock'
    if lock.is_file():
        text = lock.read_text(errors='ignore')
        marker = text.find('RUBY VERSION')
        if marker >= 0:
            for line in text[marker:].splitlines()[1:4]:
                if line.strip().startswith('ruby '):
                    return line.strip().split()[1]
    return '3.3'

def _rails_bundler_version(root: Path):
    lock = root / 'Gemfile.lock'
    if lock.is_file():
        text = lock.read_text(errors='ignore')
        marker = text.find('BUNDLED WITH')
        if marker >= 0:
            for line in text[marker:].splitlines()[1:4]:
                value = line.strip()
                if value and value[0].isdigit():
                    return value
    return None

def run_rails(root: Path, port: int):
    subprocess.run(['docker','rm','-f','rephost-rails'], capture_output=True, text=True)
    source = str(root.resolve())
    ruby_version = _rails_ruby_version(root)
    image = f'ruby:{ruby_version}-bookworm'
    bundler = _rails_bundler_version(root)
    bundle_cmd = f'gem install bundler -v {bundler} --no-document && bundle install --jobs 4' if bundler else 'bundle install --jobs 4'
    cmd = [
        'docker','run','--rm','--name','rephost-rails',
        '--mount',f'type=bind,source={source},target=/app',
        '-w','/app','-p',f'{port}:{port}',image,
        'bash','-lc',f'{bundle_cmd} && bundle exec rails db:prepare && bundle exec rails server -b 0.0.0.0 -p {port}'
    ]
    return _start(cmd, image)


def run_php(root: Path, port: int):
    subprocess.run(['docker','rm','-f','rephost-php'], capture_output=True, text=True)
    source = str(root.resolve())
    composer = root / 'composer.json'
    if (root / 'public' / 'index.php').is_file():
        document_root = 'public'
    else:
        document_root = '.'
    install = 'composer install --no-interaction --prefer-dist' if composer.is_file() else 'true'
    cmd = [
        'docker','run','--rm','--name','rephost-php',
        '--mount',f'type=bind,source={source},target=/app',
        '-w','/app','-p',f'{port}:{port}','composer:2',
        'sh','-lc',f'{install} && php -S 0.0.0.0:{port} -t {document_root}'
    ]
    return _start(cmd, 'composer:2')


def compose_host_port(root: Path):
    """Return the first published HTTP-like host port from docker compose config."""
    import json
    compose = next((root/n for n in ('compose.yml','compose.yaml','docker-compose.yml','docker-compose.yaml') if (root/n).is_file()), None)
    if compose is None:
        raise DockerError('No Docker Compose file found.')
    result = _run(['docker','compose','-f', str(compose), 'config', '--format', 'json'])
    data=json.loads(result.stdout)
    candidates=[]
    for service_name, service in data.get('services', {}).items():
        for pub in service.get('ports', []) or []:
            if isinstance(pub, dict):
                target=int(pub.get('target',0) or 0)
                published=pub.get('published')
                if published and target != 5432:
                    candidates.append((service_name, int(published), target))
    # Prefer a browser-facing frontend port when the Compose project exposes one.
    # Fall back to the first non-database published port.
    priority={3000:0,5173:1,80:2,443:3,8080:4,5000:5,8000:6}
    if candidates:
        candidates.sort(key=lambda x: priority.get(x[1], 100))
        return candidates[0][1]
    return None


def compose_services_ready(root: Path):
    """Return (ready, details) for Compose services, with special attention to databases."""
    compose = next((root/n for n in ('compose.yml','compose.yaml','docker-compose.yml','docker-compose.yaml') if (root/n).is_file()), None)
    if compose is None:
        raise DockerError('No Docker Compose file found.')
    project_name='rephost-' + root.name.lower().replace('_','-')[:40]
    result = _run(['docker','compose','-p',project_name,'-f',str(compose),'ps','--format','json'])
    import json
    raw = result.stdout.strip()
    if not raw:
        return False, 'No Compose containers are running yet.'
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Some Compose versions emit one JSON object per line.
        data = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if isinstance(data, dict):
        data=[data]
    for item in data:
        state=str(item.get('State','')).lower()
        health=str(item.get('Health','')).lower()
        if state not in ('running','up'):
            return False, f"Service {item.get('Service', item.get('Name','unknown'))} is {state or 'not running'}."
        if health == 'unhealthy':
            return False, f"Service {item.get('Service', item.get('Name','unknown'))} is unhealthy."
    return True, 'All Compose services are running.'

def run_compose(root: Path):
    compose = next((root/n for n in ('compose.yml','compose.yaml','docker-compose.yml','docker-compose.yaml') if (root/n).is_file()), None)
    if compose is None:
        raise DockerError('No Docker Compose file found.')
    project_name='rephost-' + root.name.lower().replace('_','-')[:40]
    cmd=['docker','compose','-p',project_name,'-f',str(compose),'up','--build']
    print('    Starting Docker Compose services...')
    try:
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
    except FileNotFoundError:
        raise DockerError('Docker Compose is not available.')
