import re
from pathlib import Path
from typing import List, Tuple, Optional, Set

class ApiInspector:
    """Inspects project files to detect API endpoints and documentation URLs."""

    @staticmethod
    def inspect(path: Path, framework: str) -> Tuple[bool, Optional[str], List[str]]:
        """
        Returns (is_backend_api, docs_url, api_endpoints).
        """
        fw = (framework or "").lower()
        endpoints = set()
        docs_url = None
        is_api = False

        if "fastapi" in fw:
            is_api = True
            docs_url = "/docs"
            endpoints.update(ApiInspector._scan_fastapi_routes(path))
            # Include standard FastAPI endpoints
            endpoints.add("GET    /docs")
            endpoints.add("GET    /openapi.json")
        elif "flask" in fw:
            docs_url = ApiInspector._detect_flask_docs(path)
            endpoints.update(ApiInspector._scan_flask_routes(path))
            if docs_url:
                endpoints.add(f"GET    {docs_url}")
                endpoints.add("GET    /openapi.json")
            has_templates = (path / "templates").is_dir() and any((path / "templates").rglob("*.html"))
            uses_rest_framework = False
            for p in path.rglob("*.py"):
                if ApiInspector._should_skip(p, path):
                    continue
                c = ApiInspector._read_file(p).lower()
                if "smorest" in c or "restful" in c or "restx" in c or "flask_cors" in c:
                    uses_rest_framework = True
                    break
            if docs_url or uses_rest_framework or not has_templates:
                is_api = True
        elif "django" in fw:
            endpoints.update(ApiInspector._scan_django_routes(path))
            docs_url = ApiInspector._detect_django_docs(path)
            has_templates = (path / "templates").is_dir() and any((path / "templates").rglob("*.html"))
            uses_api_framework = False
            for p in path.rglob("*.py"):
                if ApiInspector._should_skip(p, path):
                    continue
                c = ApiInspector._read_file(p).lower()
                if "rest_framework" in c or "ninja" in c or "drf_spectacular" in c or "drf_yasg" in c:
                    uses_api_framework = True
                    break
            if docs_url or uses_api_framework or not has_templates:
                is_api = True
        elif "spring" in fw or "java" in fw:
            endpoints.update(ApiInspector._scan_spring_routes(path))
            docs_url = ApiInspector._detect_spring_docs(path)
            is_api = True
        elif "rails" in fw or "ruby" in fw or "sinatra" in fw:
            endpoints.update(ApiInspector._scan_rails_routes(path))
            docs_url = ApiInspector._detect_rails_docs(path)
            has_views = (path / "app" / "views").is_dir() and any((path / "app" / "views").rglob("*.html*"))
            gemfile = path / "Gemfile"
            gemfile_content = ApiInspector._read_file(gemfile) if gemfile.exists() else ""
            if "api_only" in gemfile_content or docs_url or not has_views:
                is_api = True
        elif "laravel" in fw or "php" in fw or "symfony" in fw:
            endpoints.update(ApiInspector._scan_php_routes(path))
            docs_url = ApiInspector._detect_php_docs(path)
            has_views = (path / "resources" / "views").is_dir() and any((path / "resources" / "views").rglob("*.blade.php"))
            if docs_url or ((path / "routes" / "api.php").exists() and not has_views):
                is_api = True
        elif "asp.net" in fw or "dotnet" in fw or "c#" in fw:
            endpoints.update(ApiInspector._scan_dotnet_routes(path))
            docs_url = ApiInspector._detect_dotnet_docs(path)
            is_api = True
        elif any(n in fw for n in ["express", "nest", "fastify", "koa", "hono", "node"]):
            endpoints.update(ApiInspector._scan_node_routes(path))
            docs_url = ApiInspector._detect_node_docs(path)
            has_frontend = (path / "public" / "index.html").exists() or (path / "build" / "index.html").exists() or (path / "dist" / "index.html").exists()
            if "express" in fw or "nest" in fw or "fastify" in fw or docs_url or (endpoints and not has_frontend):
                is_api = True

        formatted_endpoints = sorted(list(endpoints))[:20]  # Cap at 20 most relevant endpoints
        return is_api, docs_url, formatted_endpoints

    @staticmethod
    def _scan_fastapi_routes(path: Path) -> List[str]:
        results = set()
        for p in path.rglob("*.py"):
            if ApiInspector._should_skip(p, path):
                continue
            content = ApiInspector._read_file(p)
            matches = re.findall(r"@(?:app|router|api)\.(get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]", content, re.IGNORECASE)
            for method, route in matches:
                clean_route = route if route.startswith("/") else f"/{route}"
                results.add(f"{method.upper():<6} {clean_route}")
        return list(results)

    @staticmethod
    def _scan_flask_routes(path: Path) -> List[str]:
        results = set()

        # Step 1: Discover Blueprint registrations and URL prefixes across Python files
        blueprint_prefixes = {}
        for p in path.rglob("*.py"):
            if ApiInspector._should_skip(p, path):
                continue
            content = ApiInspector._read_file(p)
            if not content:
                continue

            # (api|app).register_blueprint(name, url_prefix="...")
            for m in re.finditer(r"(?:api|app)\.register_blueprint\(\s*(\w+)[^)]*?url_prefix\s*=\s*['\"]([^'\"]+)['\"]", content):
                bp_var = m.group(1)
                prefix = m.group(2).rstrip("/")
                blueprint_prefixes[bp_var] = prefix
                # Check import aliases in the same file: e.g. from flaskr.routes.auth_route import bp as auth_route
                for im in re.finditer(rf"from\s+[\w\.]*?(\w+)\s+import\s+(?:.*?\bas\s+)?{bp_var}\b", content):
                    blueprint_prefixes[im.group(1)] = prefix

            # Blueprint("name", __name__, url_prefix="...")
            for m in re.finditer(r"Blueprint\(\s*['\"]([^'\"]+)['\"][^)]*?url_prefix\s*=\s*['\"]([^'\"]+)['\"]", content):
                bp_name = m.group(1)
                prefix = m.group(2).rstrip("/")
                blueprint_prefixes[bp_name] = prefix

        # Step 2: Scan routes in each file and prepend blueprint prefix where applicable
        for p in path.rglob("*.py"):
            if ApiInspector._should_skip(p, path):
                continue
            content = ApiInspector._read_file(p)
            if not content:
                continue

            # Determine prefix for this file
            file_prefix = blueprint_prefixes.get(p.stem, "")
            if not file_prefix:
                bp_def = re.search(r"Blueprint\(\s*['\"](\w+)['\"]", content)
                if bp_def and bp_def.group(1) in blueprint_prefixes:
                    file_prefix = blueprint_prefixes[bp_def.group(1)]

            # Matches @(app|bp|blueprint|api).route(...)
            matches = re.finditer(r"@(?:app|bp|blueprint|api|\w+)\.route\(\s*['\"]([^'\"]+)['\"](?:,\s*methods=\[([^\]]+)\])?", content, re.IGNORECASE)
            for m in matches:
                route = m.group(1)
                methods_raw = m.group(2)
                clean_route = route if route.startswith("/") else f"/{route}"
                if file_prefix and not clean_route.startswith(file_prefix):
                    clean_route = f"{file_prefix}{clean_route}"

                if methods_raw:
                    methods = re.findall(r"['\"]([A-Z]+)['\"]", methods_raw, re.IGNORECASE)
                    for meth in methods:
                        results.add(f"{meth.upper():<6} {clean_route}")
                else:
                    results.add(f"GET    {clean_route}")

            # Matches @bp.route(...) on a MethodView class:
            # @bp.route("/auth/sign-in")
            # class SignIn(MethodView):
            #     def post(self, data):
            view_matches = re.finditer(r"@(?:bp|api|app)\.route\(\s*['\"]([^'\"]+)['\"]\)\s*\nclass\s+(\w+)\s*\((.*?)\):", content)
            for vm in view_matches:
                route = vm.group(1)
                clean_route = route if route.startswith("/") else f"/{route}"
                if file_prefix and not clean_route.startswith(file_prefix):
                    clean_route = f"{file_prefix}{clean_route}"

                start_idx = vm.end()
                class_content = content[start_idx:start_idx + 1500]
                methods = re.findall(r"def\s+(get|post|put|delete|patch)\s*\(", class_content)
                if methods:
                    for meth in set(methods):
                        results.add(f"{meth.upper():<6} {clean_route}")
                else:
                    results.add(f"API    {clean_route}")
                
        return list(results)

    @staticmethod
    def _detect_flask_docs(path: Path) -> Optional[str]:
        openapi_url_prefix = ""
        openapi_swagger_path = None
        has_smorest = False
        has_flasgger = False
        has_restx = False
        has_openapi3 = False

        for p in path.rglob("*.py"):
            if ApiInspector._should_skip(p, path):
                continue
            content = ApiInspector._read_file(p)
            if not content:
                continue

            # Check OPENAPI_URL_PREFIX and OPENAPI_SWAGGER_UI_PATH (e.g. flask_smorest)
            if "OPENAPI_URL_PREFIX" in content:
                m_prefix = re.search(r"OPENAPI_URL_PREFIX\s*=\s*['\"]([^'\"]*)['\"]", content)
                if m_prefix:
                    openapi_url_prefix = m_prefix.group(1).rstrip("/")
            if "OPENAPI_SWAGGER_UI_PATH" in content:
                m_path = re.search(r"OPENAPI_SWAGGER_UI_PATH\s*=\s*['\"]([^'\"]+)['\"]", content)
                if m_path:
                    openapi_swagger_path = m_path.group(1)

            # SWAGGER_URL / DOCS_URL
            for key in ["SWAGGER_URL", "SWAGGERUI_URL", "DOCS_URL", "API_DOCS_URL"]:
                if key in content:
                    m_cust = re.search(rf"{key}\s*=\s*['\"]([^'\"]+)['\"]", content)
                    if m_cust:
                        clean = m_cust.group(1)
                        return clean if clean.startswith("/") else f"/{clean}"

            if "flask_smorest" in content:
                has_smorest = True
            if "flasgger" in content or "Swagger(" in content:
                has_flasgger = True
            if "flask_restx" in content or "flask_restplus" in content:
                has_restx = True
            if "flask_openapi3" in content:
                has_openapi3 = True

        if openapi_swagger_path:
            clean_path = openapi_swagger_path if openapi_swagger_path.startswith("/") else f"/{openapi_swagger_path}"
            return f"{openapi_url_prefix}{clean_path}" or "/docs"

        if has_smorest:
            return "/docs"
        if has_restx:
            return "/docs"
        if has_flasgger:
            return "/apidocs"
        if has_openapi3:
            return "/openapi/swagger"

        return None

    @staticmethod
    def _scan_django_routes(path: Path) -> List[str]:
        results = set()
        for p in path.rglob("urls.py"):
            if ApiInspector._should_skip(p, path):
                continue
            content = ApiInspector._read_file(p)
            matches = re.findall(r"path\(\s*['\"]([^'\"]*)['\"]", content)
            for route in matches:
                clean = route if route.startswith("/") else f"/{route}"
                results.add(f"ROUTE  {clean}")
            # Also check re_path
            re_matches = re.findall(r"re_path\(\s*r?['\"]([^'\"]*)['\"]", content)
            for route in re_matches:
                clean = route if route.startswith("/") else f"/{route}"
                results.add(f"ROUTE  {clean}")
        return list(results)

    @staticmethod
    def _detect_django_docs(path: Path) -> Optional[str]:
        for p in path.rglob("*.py"):
            if ApiInspector._should_skip(p, path):
                continue
            content = ApiInspector._read_file(p)
            if "drf_spectacular" in content:
                return "/api/schema/swagger-ui/"
            if "swagger" in content.lower():
                return "/swagger/"
        return None

    @staticmethod
    def _scan_spring_routes(path: Path) -> List[str]:
        results = set()
        for ext in ["*.java", "*.kt"]:
            for p in path.rglob(ext):
                if ApiInspector._should_skip(p, path):
                    continue
                content = ApiInspector._read_file(p)
                # Check class base mapping: @RequestMapping("/api/v1")
                base_match = re.search(r"@RequestMapping\(\s*(?:value\s*=\s*)?['\"]([^'\"]+)['\"]", content)
                base_prefix = base_match.group(1) if base_match else ""
                if base_prefix and not base_prefix.startswith("/"):
                    base_prefix = f"/{base_prefix}"
                if base_prefix.endswith("/"):
                    base_prefix = base_prefix[:-1]

                # Match @GetMapping("/users"), @PostMapping, etc.
                matches = re.findall(r"@(Get|Post|Put|Delete|Patch)Mapping\(\s*(?:value\s*=\s*)?['\"]?([^'\")\s]*)['\"]?\s*\)", content, re.IGNORECASE)
                for method, route in matches:
                    clean_route = f"/{route}" if route and not route.startswith("/") else (route or "")
                    full_path = f"{base_prefix}{clean_route}" or "/"
                    results.add(f"{method.upper():<6} {full_path}")
        return list(results)

    @staticmethod
    def _detect_spring_docs(path: Path) -> Optional[str]:
        # Check pom.xml or build.gradle
        for manifest_name in ["pom.xml", "build.gradle", "build.gradle.kts"]:
            p = path / manifest_name
            if p.exists():
                content = ApiInspector._read_file(p)
                if "springdoc-openapi" in content:
                    return "/swagger-ui/index.html"
                if "springfox-swagger" in content or "swagger" in content.lower():
                    return "/swagger-ui.html"
        return "/swagger-ui/index.html"

    @staticmethod
    def _scan_rails_routes(path: Path) -> List[str]:
        results = set()
        routes_file = path / "config" / "routes.rb"
        if routes_file.exists():
            content = ApiInspector._read_file(routes_file)
            # get 'items', to: 'items#index'
            verb_matches = re.findall(r"(get|post|put|delete|patch)\s+['\":]([a-zA-Z0-9_\/-]+)", content, re.IGNORECASE)
            for verb, route in verb_matches:
                clean = f"/{route}" if not route.startswith("/") else route
                results.add(f"{verb.upper():<6} {clean}")
            # resources :users
            resource_matches = re.findall(r"resources?\s+:([a-zA-Z0-9_]+)", content)
            for res_name in resource_matches:
                results.add(f"GET    /{res_name}")
                results.add(f"POST   /{res_name}")
            # root to: '...'
            if "root " in content:
                results.add("GET    /")
        return list(results)

    @staticmethod
    def _detect_rails_docs(path: Path) -> Optional[str]:
        gemfile = path / "Gemfile"
        if gemfile.exists():
            content = ApiInspector._read_file(gemfile)
            if "rswag" in content or "swagger" in content.lower():
                return "/api-docs"
        return None

    @staticmethod
    def _scan_php_routes(path: Path) -> List[str]:
        results = set()
        for r_name in ["routes/api.php", "routes/web.php"]:
            p = path / r_name
            if p.exists():
                content = ApiInspector._read_file(p)
                # Route::get('/users', ...), Route::post, etc.
                matches = re.findall(r"Route::(get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]", content, re.IGNORECASE)
                for method, route in matches:
                    clean = route if route.startswith("/") else f"/{route}"
                    if "api.php" in r_name and not clean.startswith("/api"):
                        clean = f"/api{clean}"
                    results.add(f"{method.upper():<6} {clean}")
                # Route::apiResource('users', ...)
                res_matches = re.findall(r"Route::(?:apiResource|resource)\(\s*['\"]([^'\"]+)['\"]", content)
                for res_name in res_matches:
                    prefix = f"/api/{res_name}" if "api.php" in r_name else f"/{res_name}"
                    results.add(f"GET    {prefix}")
                    results.add(f"POST   {prefix}")
        return list(results)

    @staticmethod
    def _detect_php_docs(path: Path) -> Optional[str]:
        composer_file = path / "composer.json"
        if composer_file.exists():
            content = ApiInspector._read_file(composer_file)
            if "l5-swagger" in content or "swagger" in content.lower():
                return "/api/documentation"
        return None

    @staticmethod
    def _scan_dotnet_routes(path: Path) -> List[str]:
        results = set()
        for p in path.rglob("*.cs"):
            if ApiInspector._should_skip(p, path):
                continue
            content = ApiInspector._read_file(p)
            # Controller route attributes: [Route("api/[controller]")]
            route_attr = re.search(r'\[Route\(\s*["\']([^"\']+)["\']\s*\)\]', content)
            prefix = route_attr.group(1) if route_attr else ""
            if prefix and not prefix.startswith("/"):
                prefix = f"/{prefix}"
            # [HttpGet("path")]
            matches = re.findall(r'\[Http(Get|Post|Put|Delete|Patch)\(?\s*["\']?([^"\')\s]*)["\']?\s*\)?\]', content)
            for verb, route in matches:
                clean = f"/{route}" if route and not route.startswith("/") else (route or "")
                full = f"{prefix}{clean}" or "/"
                results.add(f"{verb.upper():<6} {full}")
            # Minimal APIs: app.MapGet("/todos", ...)
            map_matches = re.findall(r'app\.Map(Get|Post|Put|Delete|Patch)\(\s*["\']([^"\']+)["\']', content)
            for verb, route in map_matches:
                clean = route if route.startswith("/") else f"/{route}"
                results.add(f"{verb.upper():<6} {clean}")
        return list(results)

    @staticmethod
    def _detect_dotnet_docs(path: Path) -> Optional[str]:
        for p in path.rglob("*.cs"):
            if ApiInspector._should_skip(p, path):
                continue
            content = ApiInspector._read_file(p)
            if "UseSwagger" in content or "SwaggerGen" in content:
                return "/swagger/index.html"
        return "/swagger/index.html"

    @staticmethod
    def _scan_node_routes(path: Path) -> List[str]:
        results = set()
        for ext in ["*.js", "*.ts", "*.mjs"]:
            for p in path.rglob(ext):
                if ApiInspector._should_skip(p, path):
                    continue
                content = ApiInspector._read_file(p)
                matches = re.findall(r"(?:app|router)\.(get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]", content, re.IGNORECASE)
                for method, route in matches:
                    clean = route if route.startswith("/") else f"/{route}"
                    results.add(f"{method.upper():<6} {clean}")
                nest_matches = re.findall(r"@(Get|Post|Put|Delete|Patch)\(\s*['\"]?([^'\")\s]*)['\"]?\s*\)", content, re.IGNORECASE)
                for method, route in nest_matches:
                    clean = f"/{route}" if route and not route.startswith("/") else (route or "/")
                    results.add(f"{method.upper():<6} {clean}")
        return list(results)

    @staticmethod
    def _detect_node_docs(path: Path) -> Optional[str]:
        for ext in ["*.js", "*.ts", "*.json"]:
            for p in path.rglob(ext):
                if ApiInspector._should_skip(p, path):
                    continue
                content = ApiInspector._read_file(p)
                if "swagger" in content.lower():
                    if "/api-docs" in content:
                        return "/api-docs"
                    if "/docs" in content:
                        return "/docs"
                    return "/api"
        return None

    @staticmethod
    def _should_skip(p: Path, root: Path) -> bool:
        parts = p.relative_to(root).parts
        skip_dirs = {".git", ".venv", "node_modules", "vendor", "__pycache__", "dist", "build", "coverage", ".next", "target", "bin", "obj"}
        return any(part in skip_dirs or part.startswith(".") for part in parts)

    @staticmethod
    def _read_file(p: Path) -> str:
        try:
            return p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""

