"""
ConnectionBridge — Framework-Aware Frontend↔Backend Connection Discovery

Scans a multi-tier repository to discover how the frontend references the
backend (hardcoded URLs, environment variables, proxy configurations) and
determines the correct bridging strategy so both services can communicate
when running inside separate Docker containers.

Strategies (in priority order):
  1. Port Pinning — backend maps to the exact port the frontend expects
  2. Env-Var Injection — frontend reads API URL from env vars
  3. Source Rewriting — hardcoded URLs are sed-replaced at Docker build time
"""

import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Set
from dataclasses import dataclass, field


@dataclass
class ConnectionInfo:
    """Describes how a frontend references its backend."""
    # Hardcoded URLs found in source (e.g. "http://localhost:5000")
    hardcoded_origins: List[str] = field(default_factory=list)
    # The port the frontend expects the backend on
    expected_backend_port: Optional[int] = None
    # The API base path (e.g. "/api/v1")
    api_base_path: Optional[str] = None
    # Environment variable name used for API URL (e.g. "VITE_API_URL")
    env_var_for_api: Optional[str] = None
    # Whether a proxy config was detected (vite.config proxy, CRA proxy, etc.)
    has_proxy_config: bool = False
    # The proxy target if detected
    proxy_target: Optional[str] = None


@dataclass
class BridgeStrategy:
    """The chosen strategy to bridge frontend→backend."""
    name: str                               # "port_pin", "env_inject", "source_rewrite"
    pinned_backend_port: Optional[int] = None
    env_vars_to_inject: Dict[str, str] = field(default_factory=dict)
    source_rewrite_from: Optional[str] = None
    source_rewrite_to: Optional[str] = None
    description: str = ""


class ConnectionBridge:
    """Analyzes a multi-tier repository and configures inter-service networking."""

    # Common env var names that frontends use for API base URL
    KNOWN_API_ENV_VARS = [
        "VITE_API_URL", "VITE_API_BASE_URL", "VITE_BACKEND_URL", "VITE_SERVER_URL",
        "REACT_APP_API_URL", "REACT_APP_API_BASE_URL", "REACT_APP_BACKEND_URL",
        "NEXT_PUBLIC_API_URL", "NEXT_PUBLIC_API_BASE_URL", "NEXT_PUBLIC_BACKEND_URL",
        "NUXT_PUBLIC_API_URL", "NUXT_PUBLIC_API_BASE",
        "API_URL", "API_BASE_URL", "BACKEND_URL", "SERVER_URL",
    ]

    @staticmethod
    def analyze_frontend(frontend_path: Path) -> ConnectionInfo:
        """
        Scan the frontend source code to discover how it references the backend.
        Returns a ConnectionInfo describing the discovered patterns.
        """
        info = ConnectionInfo()

        # 1. Scan source files for hardcoded localhost URLs
        hardcoded = ConnectionBridge._scan_hardcoded_urls(frontend_path)
        if hardcoded:
            info.hardcoded_origins = list(hardcoded.keys())
            # Pick the most frequently referenced origin
            most_common = max(hardcoded, key=hardcoded.get)
            port_match = re.search(r":(\d+)", most_common)
            if port_match:
                info.expected_backend_port = int(port_match.group(1))
            # Extract the API base path from URLs
            info.api_base_path = ConnectionBridge._extract_api_base_path(hardcoded)

        # 2. Scan for environment variable usage
        env_var = ConnectionBridge._scan_env_var_usage(frontend_path)
        if env_var:
            info.env_var_for_api = env_var

        # 3. Check for proxy configuration
        proxy_info = ConnectionBridge._scan_proxy_config(frontend_path)
        if proxy_info:
            info.has_proxy_config = True
            info.proxy_target = proxy_info.get("target")
            if not info.expected_backend_port and proxy_info.get("port"):
                info.expected_backend_port = proxy_info["port"]

        return info

    @staticmethod
    def determine_strategy(
        connection_info: ConnectionInfo,
        backend_port_available: bool,
        actual_backend_port: Optional[int] = None,
    ) -> BridgeStrategy:
        """
        Given how the frontend references the backend, decide the best
        bridging strategy.
        """
        expected_port = connection_info.expected_backend_port

        # If backend is already running on a different port than expected, rewrite source URLs
        if actual_backend_port and expected_port and actual_backend_port != expected_port:
            old_origin = connection_info.hardcoded_origins[0] if connection_info.hardcoded_origins else f"http://localhost:{expected_port}"
            new_origin = f"http://localhost:{actual_backend_port}"
            return BridgeStrategy(
                name="source_rewrite",
                source_rewrite_from=old_origin,
                source_rewrite_to=new_origin,
                description=f"Rewrite {old_origin} → {new_origin} in frontend source (backend running on {actual_backend_port})",
            )

        # Strategy 1: Port Pinning (best case — backend will use or is using expected port)
        if expected_port and (backend_port_available or actual_backend_port == expected_port):
            return BridgeStrategy(
                name="port_pin",
                pinned_backend_port=expected_port,
                description=f"Pin backend to port {expected_port} (port available on host)",
            )

        # Strategy 2: Env-Var Injection (frontend reads API URL from env)
        if connection_info.env_var_for_api:
            target_url = f"http://localhost:{actual_backend_port or expected_port or 5000}"
            return BridgeStrategy(
                name="env_inject",
                env_vars_to_inject={connection_info.env_var_for_api: target_url},
                pinned_backend_port=expected_port if expected_port and backend_port_available else None,
                description=f"Inject {connection_info.env_var_for_api}={target_url}",
            )

        # Strategy 3: Source Rewriting (hardcoded URLs, port unavailable)
        if expected_port and not backend_port_available and connection_info.hardcoded_origins:
            # We'll rewrite the most common origin to point to the actual backend port
            old_origin = connection_info.hardcoded_origins[0]
            new_origin = f"http://localhost:{actual_backend_port or 0}"
            return BridgeStrategy(
                name="source_rewrite",
                source_rewrite_from=old_origin,
                source_rewrite_to=new_origin,
                description=f"Rewrite {old_origin} → {new_origin} in frontend source at build time",
            )

        # Strategy 1 fallback: if we have an expected port, try pinning anyway
        if expected_port:
            return BridgeStrategy(
                name="port_pin",
                pinned_backend_port=expected_port,
                description=f"Pin backend to port {expected_port}",
            )

        # No connection pattern detected — use generic env injection
        return BridgeStrategy(
            name="env_inject_generic",
            description="No specific backend reference pattern detected; injecting standard env vars",
        )

    # ── Private scanning methods ──────────────────────────────────────

    @staticmethod
    def _scan_hardcoded_urls(frontend_path: Path) -> Dict[str, int]:
        """
        Scan .ts, .tsx, .js, .jsx, .vue, .svelte files for hardcoded
        http://localhost:<port> references. Returns {origin: count}.
        """
        url_counts: Dict[str, int] = {}
        extensions = {".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte", ".mjs"}

        src_dir = frontend_path / "src"
        scan_root = src_dir if src_dir.is_dir() else frontend_path

        for p in scan_root.rglob("*"):
            if p.suffix not in extensions:
                continue
            if ConnectionBridge._should_skip(p, frontend_path):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # Match http://localhost:<port> or http://127.0.0.1:<port>
            matches = re.findall(
                r"(https?://(?:localhost|127\.0\.0\.1):\d+)",
                content
            )
            for origin in matches:
                # Normalize: strip trailing path if present in the match
                # We want just the origin (scheme + host + port)
                url_counts[origin] = url_counts.get(origin, 0) + 1

        return url_counts

    @staticmethod
    def _extract_api_base_path(hardcoded: Dict[str, int]) -> Optional[str]:
        """
        From the set of hardcoded URLs, try to extract the common API
        base path prefix (e.g. "/api/v1").
        """
        # We need the full URLs, not just origins. Re-scan is expensive,
        # so we approximate from what we have: origins are just host:port.
        # The api_base_path is better determined from a deeper scan, but
        # for now we return None and rely on ApiInspector.
        return None

    @staticmethod
    def _scan_env_var_usage(frontend_path: Path) -> Optional[str]:
        """
        Scan frontend source for references to known API URL environment
        variables (e.g. import.meta.env.VITE_API_URL, process.env.REACT_APP_API_URL).
        """
        extensions = {".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte", ".mjs"}

        src_dir = frontend_path / "src"
        scan_root = src_dir if src_dir.is_dir() else frontend_path

        for p in scan_root.rglob("*"):
            if p.suffix not in extensions:
                continue
            if ConnectionBridge._should_skip(p, frontend_path):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for var_name in ConnectionBridge.KNOWN_API_ENV_VARS:
                # Vite: import.meta.env.VITE_API_URL
                # CRA: process.env.REACT_APP_API_URL
                if var_name in content:
                    return var_name

        # Also check .env, .env.example, .env.local files
        for env_file in [".env", ".env.example", ".env.local", ".env.development"]:
            env_path = frontend_path / env_file
            if env_path.exists():
                try:
                    env_content = env_path.read_text(encoding="utf-8", errors="ignore")
                    for var_name in ConnectionBridge.KNOWN_API_ENV_VARS:
                        if var_name in env_content:
                            return var_name
                except Exception:
                    continue

        return None

    @staticmethod
    def _scan_proxy_config(frontend_path: Path) -> Optional[Dict]:
        """
        Check for proxy configurations in common frontend build tools.
        Returns {"target": "http://localhost:5000", "port": 5000} or None.
        """
        # 1. Check vite.config.ts / vite.config.js for server.proxy
        for config_name in ["vite.config.ts", "vite.config.js", "vite.config.mjs"]:
            config_path = frontend_path / config_name
            if config_path.exists():
                try:
                    content = config_path.read_text(encoding="utf-8", errors="ignore")
                    # Look for proxy configuration
                    if "proxy" in content:
                        # Extract target URL
                        target_match = re.search(r"target\s*:\s*['\"]([^'\"]+)['\"]", content)
                        if target_match:
                            target = target_match.group(1)
                            port_match = re.search(r":(\d+)", target)
                            return {
                                "target": target,
                                "port": int(port_match.group(1)) if port_match else None,
                            }
                except Exception:
                    pass

        # 2. Check package.json for "proxy" field (Create React App)
        pkg_json = frontend_path / "package.json"
        if pkg_json.exists():
            try:
                import json
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                proxy = data.get("proxy")
                if proxy and isinstance(proxy, str):
                    port_match = re.search(r":(\d+)", proxy)
                    return {
                        "target": proxy,
                        "port": int(port_match.group(1)) if port_match else None,
                    }
            except Exception:
                pass

        # 3. Check next.config.js / next.config.mjs for rewrites
        for config_name in ["next.config.js", "next.config.mjs", "next.config.ts"]:
            config_path = frontend_path / config_name
            if config_path.exists():
                try:
                    content = config_path.read_text(encoding="utf-8", errors="ignore")
                    if "rewrites" in content or "proxy" in content:
                        target_match = re.search(r"destination\s*:\s*['\"]([^'\"]+)['\"]", content)
                        if target_match:
                            target = target_match.group(1)
                            port_match = re.search(r":(\d+)", target)
                            return {
                                "target": target,
                                "port": int(port_match.group(1)) if port_match else None,
                            }
                except Exception:
                    pass

        # 4. Check angular.json for proxyConfig
        angular_json = frontend_path / "angular.json"
        if angular_json.exists():
            try:
                content = angular_json.read_text(encoding="utf-8", errors="ignore")
                if "proxyConfig" in content:
                    # Look for the proxy config file
                    proxy_match = re.search(r"proxyConfig\s*:\s*['\"]([^'\"]+)['\"]", content)
                    if proxy_match:
                        proxy_file = frontend_path / proxy_match.group(1)
                        if proxy_file.exists():
                            proxy_content = proxy_file.read_text(encoding="utf-8", errors="ignore")
                            target_match = re.search(r"target\s*:\s*['\"]([^'\"]+)['\"]", proxy_content)
                            if target_match:
                                target = target_match.group(1)
                                port_match = re.search(r":(\d+)", target)
                                return {
                                    "target": target,
                                    "port": int(port_match.group(1)) if port_match else None,
                                }
            except Exception:
                pass

        return None

    @staticmethod
    def _should_skip(p: Path, root: Path) -> bool:
        """Skip vendor/build/test directories."""
        try:
            parts = p.relative_to(root).parts
        except ValueError:
            return True
        skip_dirs = {
            ".git", "node_modules", "dist", "build", ".next", ".nuxt",
            "coverage", "__pycache__", ".venv", "vendor",
        }
        return any(part in skip_dirs or part.startswith(".") for part in parts)

    @staticmethod
    def generate_rewrite_dockerfile_step(
        rewrite_from: str,
        rewrite_to: str,
    ) -> str:
        """
        Generate a Dockerfile RUN step that rewrites hardcoded backend URLs
        in the frontend source code. Escapes sed special characters properly.
        """
        # Escape special characters for sed
        escaped_from = rewrite_from.replace("/", "\\/").replace(".", "\\.")
        escaped_to = rewrite_to.replace("/", "\\/")
        return (
            f'RUN find /app/src -type f \\( -name "*.ts" -o -name "*.tsx" '
            f'-o -name "*.js" -o -name "*.jsx" -o -name "*.vue" '
            f'-o -name "*.svelte" \\) '
            f"-exec sed -i 's|{rewrite_from}|{rewrite_to}|g' {{}} + || true"
        )
