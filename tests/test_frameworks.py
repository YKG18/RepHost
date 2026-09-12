import pytest
from pathlib import Path
from app.detectors import detect_project
from app.core.models import ProjectType
from app.sandbox.dockerfile_generator import DockerfileGenerator
from app.sandbox.docker_checker import find_docker_desktop_executable
from app.detectors.api_inspector import ApiInspector


def test_spring_boot_maven_detection(tmp_path: Path):
    pom_content = """<project xmlns="http://maven.apache.org/POM/4.0.0">
        <modelVersion>4.0.0</modelVersion>
        <groupId>com.example</groupId>
        <artifactId>demo</artifactId>
        <version>0.0.1-SNAPSHOT</version>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-web</artifactId>
            </dependency>
            <dependency>
                <groupId>org.springdoc</groupId>
                <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
            </dependency>
        </dependencies>
    </project>"""
    (tmp_path / "pom.xml").write_text(pom_content, encoding="utf-8")
    
    # Create sample controller
    src_dir = tmp_path / "src" / "main" / "java" / "com" / "example"
    src_dir.mkdir(parents=True)
    java_file = src_dir / "UserController.java"
    java_file.write_text("""
    package com.example;
    import org.springframework.web.bind.annotation.*;

    @RestController
    @RequestMapping("/api/v1")
    public class UserController {
        @GetMapping("/users")
        public String getUsers() { return "users"; }

        @PostMapping("/users")
        public String createUser() { return "created"; }
    }
    """, encoding="utf-8")

    results = detect_project(tmp_path)
    assert len(results) == 1
    res = results[0]
    assert res.project_type == ProjectType.JAVA
    assert res.framework == "Spring Boot"
    assert res.package_manager == "maven"
    assert res.is_backend_api is True
    assert "/swagger-ui/index.html" in (res.docs_url or "")
    assert any("/api/v1/users" in ep for ep in res.api_endpoints)

    # Test Dockerfile generation
    dockerfile = DockerfileGenerator.generate(tmp_path, res)
    assert "maven:3.9-eclipse-temurin-17" in dockerfile
    assert "EXPOSE 8080" in dockerfile


def test_spring_boot_gradle_detection(tmp_path: Path):
    gradle_content = """
    plugins {
        id 'org.springframework.boot' version '3.2.0'
        id 'java'
    }
    dependencies {
        implementation 'org.springframework.boot:spring-boot-starter-web'
    }
    """
    (tmp_path / "build.gradle").write_text(gradle_content, encoding="utf-8")
    results = detect_project(tmp_path)
    assert len(results) == 1
    res = results[0]
    assert res.project_type == ProjectType.JAVA
    assert res.package_manager == "gradle"
    dockerfile = DockerfileGenerator.generate(tmp_path, res)
    assert "gradle:8.5-jdk17" in dockerfile


def test_ruby_on_rails_detection(tmp_path: Path):
    (tmp_path / "Gemfile").write_text('source "https://rubygems.org"\ngem "rails", "~> 7.1"\ngem "rswag"\n', encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    routes_file = config_dir / "routes.rb"
    routes_file.write_text("""
    Rails.application.routes.draw do
        resources :articles
        get 'health', to: 'health#check'
    end
    """, encoding="utf-8")

    results = detect_project(tmp_path)
    assert len(results) == 1
    res = results[0]
    assert res.project_type == ProjectType.RUBY
    assert res.framework == "Ruby on Rails"
    assert res.package_manager == "bundle"
    assert res.is_backend_api is True
    assert res.docs_url == "/api-docs"
    assert any("/articles" in ep for ep in res.api_endpoints)
    assert any("/health" in ep for ep in res.api_endpoints)

    dockerfile = DockerfileGenerator.generate(tmp_path, res)
    assert "ruby:3.2-slim" in dockerfile
    assert "rails db:prepare" in dockerfile


def test_php_laravel_detection(tmp_path: Path):
    (tmp_path / "artisan").touch()
    (tmp_path / "composer.json").write_text('{"require": {"laravel/framework": "^10.0"}}', encoding="utf-8")
    routes_dir = tmp_path / "routes"
    routes_dir.mkdir(parents=True)
    (routes_dir / "api.php").write_text("""<?php
    Route::get('/products', [ProductController::class, 'index']);
    Route::post('/products', [ProductController::class, 'store']);
    """, encoding="utf-8")

    results = detect_project(tmp_path)
    assert len(results) == 1
    res = results[0]
    assert res.project_type == ProjectType.PHP
    assert res.framework == "Laravel"
    assert res.package_manager == "composer"
    assert res.is_backend_api is True
    assert any("/api/products" in ep for ep in res.api_endpoints)

    dockerfile = DockerfileGenerator.generate(tmp_path, res)
    assert "php:8.2-cli" in dockerfile
    assert "artisan key:generate" in dockerfile


def test_dotnet_aspnet_detection(tmp_path: Path):
    (tmp_path / "WebApi.csproj").write_text("""<Project Sdk="Microsoft.NET.Sdk.Web">
        <PropertyGroup>
            <TargetFramework>net8.0</TargetFramework>
        </PropertyGroup>
    </Project>""", encoding="utf-8")
    (tmp_path / "Program.cs").write_text("""
    var builder = WebApplication.CreateBuilder(args);
    builder.Services.AddEndpointsApiExplorer();
    builder.Services.AddSwaggerGen();
    var app = builder.Build();
    app.UseSwagger();
    app.UseSwaggerUI();
    app.MapGet("/weatherforecast", () => "sunny");
    app.Run();
    """, encoding="utf-8")

    results = detect_project(tmp_path)
    assert len(results) == 1
    res = results[0]
    assert res.project_type == ProjectType.DOTNET
    assert res.framework == "ASP.NET Core"
    assert res.is_backend_api is True
    assert "/swagger/index.html" in (res.docs_url or "")
    assert any("/weatherforecast" in ep for ep in res.api_endpoints)

    dockerfile = DockerfileGenerator.generate(tmp_path, res)
    assert "mcr.microsoft.com/dotnet/sdk:8.0" in dockerfile
    assert "EXPOSE 5000 8080" in dockerfile


def test_django_detection_and_routes(tmp_path: Path):
    (tmp_path / "manage.py").touch()
    (tmp_path / "requirements.txt").write_text("django>=4.2\n", encoding="utf-8")
    
    # Create urls.py
    app_dir = tmp_path / "myproject"
    app_dir.mkdir(parents=True)
    (app_dir / "urls.py").write_text("""
    from django.urls import path
    urlpatterns = [
        path('admin/', admin.site.urls),
        path('api/v1/posts/', post_views),
    ]
    """, encoding="utf-8")

    results = detect_project(tmp_path)
    assert len(results) == 1
    res = results[0]
    assert res.project_type == ProjectType.PYTHON
    assert res.framework == "Django"
    assert any("/admin/" in ep for ep in res.api_endpoints)
    assert any("/api/v1/posts/" in ep for ep in res.api_endpoints)

    dockerfile = DockerfileGenerator.generate(tmp_path, res)
    assert "python manage.py migrate --noinput" in dockerfile


def test_django_without_requirements_with_templates(tmp_path: Path):
    (tmp_path / "manage.py").touch()
    # No requirements.txt!
    # Create templates directory with index.html containing Django template tags
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "index.html").write_text("{% extends 'base.html' %}\n{% block content %}Home{% endblock %}", encoding="utf-8")
    
    # Create models.py with imports and ImageField
    app_dir = tmp_path / "myapp"
    app_dir.mkdir()
    (app_dir / "models.py").write_text("""
    import shortuuid
    from django.db import models
    from mptt.models import MPTTModel
    
    class Item(models.Model):
        pic = models.ImageField(upload_to='pics/')
    """, encoding="utf-8")

    results = detect_project(tmp_path)
    assert len(results) == 1
    res = results[0]
    assert res.project_type == ProjectType.PYTHON
    assert res.framework == "Django"
    assert res.sub_path == "."
    assert "django" in res.install_command
    assert "django-mptt" in res.install_command
    assert "shortuuid" in res.install_command
    assert "Pillow" in res.install_command

    dockerfile = DockerfileGenerator.generate(tmp_path, res)
    assert "ALLOWED_HOSTS" in dockerfile
    assert "CSRF_TRUSTED_ORIGINS" in dockerfile
    assert "--insecure" in dockerfile


def test_fastapi_backend_endpoints(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("""
    from fastapi import FastAPI
    app = FastAPI()

    @app.get("/items")
    def get_items(): return []

    @app.post("/items")
    def create_item(): return {}
    """, encoding="utf-8")

    results = detect_project(tmp_path)
    assert len(results) == 1
    res = results[0]
    assert res.project_type == ProjectType.PYTHON
    assert res.framework == "FastAPI"
    assert res.is_backend_api is True
    assert res.docs_url == "/docs"
    assert any("/docs" in ep for ep in res.api_endpoints)
    assert any("/openapi.json" in ep for ep in res.api_endpoints)
    assert any("/items" in ep for ep in res.api_endpoints)


def test_docker_desktop_finder():
    # Verify that the finder function returns a valid Path or None without crashing
    exe = find_docker_desktop_executable()
    if exe is not None:
        assert isinstance(exe, Path)


def test_multitier_backend_frontend_subprojects(tmp_path: Path):
    # Backend with requirements.txt and application.py
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "requirements.txt").write_text("flask\n", encoding="utf-8")
    (backend_dir / "application.py").write_text("from flask import Flask\napp = Flask(__name__)\n", encoding="utf-8")
    flaskr_dir = backend_dir / "flaskr"
    flaskr_dir.mkdir()
    (flaskr_dir / "__init__.py").touch()

    # Frontend with package.json
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "package.json").write_text('{"name": "fe", "scripts": {"dev": "vite"}}', encoding="utf-8")

    results = detect_project(tmp_path)
    assert len(results) == 2
    sub_paths = {r.sub_path for r in results}
    assert sub_paths == {"backend", "frontend"}
    assert "." not in sub_paths


def test_python_deep_scan_ignores_local_packages(tmp_path: Path):
    # No root requirements.txt, contains local module imports like flaskr and config
    local_pkg = tmp_path / "flaskr"
    local_pkg.mkdir()
    (local_pkg / "__init__.py").write_text("from flask import Flask\napp = Flask(__name__)\n", encoding="utf-8")
    (tmp_path / "config.py").write_text("DEBUG = True\n", encoding="utf-8")
    (tmp_path / "routes.py").write_text("""
    import config
    from flaskr import app
    from flask import request
    import requests
    """, encoding="utf-8")

    results = detect_project(tmp_path)
    assert len(results) == 1
    res = results[0]
    assert res.project_type == ProjectType.PYTHON
    assert res.install_command is not None
    # Ensure local names 'flaskr' and 'config' were NOT added to pip install
    assert "flaskr" not in res.install_command
    assert "config" not in res.install_command
    # Ensure third-party 'requests' was added
    assert "requests" in res.install_command


def test_flask_docs_and_blueprint_prefix_inspection(tmp_path: Path):
    from app.detectors.api_inspector import ApiInspector
    # Create config.py with OPENAPI_SWAGGER_UI_PATH = "/docs"
    (tmp_path / "config.py").write_text("""
OPENAPI_URL_PREFIX = "/"
OPENAPI_SWAGGER_UI_PATH = "/docs"
""", encoding="utf-8")

    # Create app registering blueprints with url_prefix="/api/v1"
    (tmp_path / "app.py").write_text("""
from flask import Flask
from flask_smorest import Api
from routes.auth import bp as auth_bp

app = Flask(__name__)
api = Api(app)
api.register_blueprint(auth_bp, url_prefix="/api/v1")
""", encoding="utf-8")

    routes_dir = tmp_path / "routes"
    routes_dir.mkdir()
    (routes_dir / "auth.py").write_text("""
from flask_smorest import Blueprint
from flask.views import MethodView

bp = Blueprint("auth", __name__)

@bp.route("/auth/sign-in")
class SignIn(MethodView):
    def post(self):
        return {"status": "ok"}
""", encoding="utf-8")

    is_api, docs_url, endpoints = ApiInspector.inspect(tmp_path, "flask")
    assert is_api is True
    assert docs_url == "/docs"
    assert any("/api/v1/auth/sign-in" in ep for ep in endpoints)
    assert any("POST" in ep for ep in endpoints if "/api/v1/auth/sign-in" in ep)
    assert any("/docs" in ep for ep in endpoints)


def test_port_availability_check():
    from app.process.manager import is_port_available
    import socket
    # Find a currently available port
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
    # Once closed, it should be available
    assert is_port_available(free_port) is True


def test_find_working_docs_url():
    import http.server
    import threading
    from app.health.checks import find_working_docs_url

    class CustomHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/docs":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><head><title>Swagger UI</title></head><body><div id='swagger-ui'></div></body></html>")
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), CustomHandler)
    server_port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        working_url = find_working_docs_url(server_port, ["/swagger-ui"])
        assert working_url == "/docs"
    finally:
        server.shutdown()


def test_connection_bridge_detection_and_strategy(tmp_path):
    from app.detectors.connection_bridge import ConnectionBridge

    frontend_dir = tmp_path / "frontend"
    src_dir = frontend_dir / "src"
    src_dir.mkdir(parents=True)

    api_service = src_dir / "api.ts"
    api_service.write_text("const API_URL = 'http://localhost:5000/api/v1';", encoding="utf-8")

    info = ConnectionBridge.analyze_frontend(frontend_dir)
    assert info.expected_backend_port == 5000
    assert "http://localhost:5000" in info.hardcoded_origins

    # Strategy with port available
    strategy_pin = ConnectionBridge.determine_strategy(info, backend_port_available=True)
    assert strategy_pin.name == "port_pin"
    assert strategy_pin.pinned_backend_port == 5000

    # Strategy with port unavailable and actual running backend port 5001
    strategy_rewrite = ConnectionBridge.determine_strategy(
        info, backend_port_available=False, actual_backend_port=5001
    )
    assert strategy_rewrite.name == "source_rewrite"
    assert strategy_rewrite.source_rewrite_to == "http://localhost:5001"


def test_flask_migration_and_seed_in_dockerfile(tmp_path):
    from app.sandbox.dockerfile_generator import DockerfileGenerator
    from app.core.models import DetectorResult, ProjectType

    workspace = tmp_path / "backend"
    workspace.mkdir()
    (workspace / "migrations").mkdir()
    (workspace / "seed.py").write_text("print('seeding')", encoding="utf-8")
    (workspace / "requirements.txt").write_text("flask\nflask_sqlalchemy\n", encoding="utf-8")

    result = DetectorResult(
        project_type=ProjectType.PYTHON,
        framework="Flask",
        package_manager="pip",
        install_command=["pip", "install", "-r", "requirements.txt"],
        run_command=["python", "-m", "flask", "run", "--host", "0.0.0.0", "--port", "5000"],
        expected_ports=[5000],
        confidence=0.9,
        is_backend_api=True,
    )

    dockerfile = DockerfileGenerator.generate(workspace, result)
    assert "# Generated by RepoHost" in dockerfile
    assert "flask db upgrade" in dockerfile
    assert "python seed.py" in dockerfile
    assert "origins" in dockerfile  # CORS permissive patch


def test_node_source_rewrite_in_dockerfile(tmp_path):
    from app.sandbox.dockerfile_generator import DockerfileGenerator
    from app.core.models import DetectorResult, ProjectType

    workspace = tmp_path / "frontend"
    workspace.mkdir()
    (workspace / "package.json").write_text('{"name": "frontend"}', encoding="utf-8")

    result = DetectorResult(
        project_type=ProjectType.NODE,
        framework="Vite",
        package_manager="npm",
        install_command=["npm", "install"],
        run_command=["npm", "run", "dev", "--", "--host", "0.0.0.0"],
        expected_ports=[5173],
        confidence=0.9,
        is_backend_api=False,
        source_rewrite_from="http://localhost:5000",
        source_rewrite_to="http://localhost:5001",
    )

    dockerfile = DockerfileGenerator.generate(workspace, result)
    assert "# Generated by RepoHost" in dockerfile
    assert "sed -i -E" in dockerfile
    assert "5000" in dockerfile
    assert "5001" in dockerfile


