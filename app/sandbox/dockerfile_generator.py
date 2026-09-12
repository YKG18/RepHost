import os
from pathlib import Path
from app.core.models import ProjectType, DetectorResult

class DockerfileGenerator:
    @staticmethod
    def generate(workspace_path: Path, result: DetectorResult) -> str:
        """
        Generates a Dockerfile string based on the detected project type.
        """
        if result.project_type == ProjectType.PYTHON:
            return DockerfileGenerator._generate_python(workspace_path, result)
        elif result.project_type == ProjectType.NODE:
            return DockerfileGenerator._generate_node(workspace_path, result)
        elif result.project_type == ProjectType.STATIC:
            return DockerfileGenerator._generate_static(workspace_path, result)
        else:
            raise ValueError(f"Unsupported project type for Docker isolation: {result.project_type}")

    @staticmethod
    def _generate_python(workspace_path: Path, result: DetectorResult) -> str:
        base_image = "python:3.11-slim"
        req_file = workspace_path / "requirements.txt"

        # Build standard Dockerfile
        lines = [
            f"FROM {base_image}",
            "WORKDIR /app",
            "COPY . /app",
            "RUN apt-get update && apt-get install -y gcc g++ libffi-dev make",
        ]
        
        # Determine install command (default to requirements.txt if available)
        if req_file.exists():
            lines.append("RUN pip install --no-cache-dir --upgrade pip")
            # If standard installation fails (due to ancient pins failing to build on modern python),
            # aggressively strip the version pins and install the latest versions.
            lines.append("RUN pip install --no-cache-dir -r requirements.txt || (sed -i 's/[=<>~].*//g' requirements.txt && pip install --no-cache-dir -r requirements.txt)")
        else:
            if result.install_command:
                lines.append(f"RUN {' '.join(result.install_command)}")

        # Expose all common ports for flexibility, process manager will detect dynamically
        lines.append("EXPOSE 3000 5000 8000 8080")
        
        # Run command
        if result.run_command:
            cmd_str = ", ".join(f'"{c}"' for c in result.run_command)
            lines.append(f"CMD [{cmd_str}]")
            
        return "\n".join(lines)

    @staticmethod
    def _generate_node(workspace_path: Path, result: DetectorResult) -> str:
        base_image = "node:18-slim"
        
        lines = [
            f"FROM {base_image}",
            "WORKDIR /app",
            'ENV HOST="0.0.0.0"',
            "COPY package*.json ./",
        ]
        
        # Use appropriate package manager
        pkg_manager = result.package_manager or "npm"
        if pkg_manager == "yarn":
            lines.append("COPY yarn.lock ./")
            lines.append("RUN yarn install")
        elif pkg_manager == "pnpm":
            lines.append("RUN npm install -g pnpm")
            lines.append("COPY pnpm-lock.yaml ./")
            lines.append("RUN pnpm install")
        else:
            lines.append("RUN npm install")
            
        lines.append("COPY . .")
        lines.append("EXPOSE 3000 4000 5173 8080")
        
        if result.run_command:
            cmd_str = ", ".join(f'"{c}"' for c in result.run_command)
            lines.append(f"CMD [{cmd_str}]")
            
        return "\n".join(lines)

    @staticmethod
    def _generate_static(workspace_path: Path, result: DetectorResult) -> str:
        lines = [
            "FROM python:3.11-slim",
            "WORKDIR /app",
            "COPY . /app",
            "EXPOSE 8000"
        ]
        if result.run_command:
            # StaticDetector uses python -m http.server 0
            # Let's force it to a known port inside the container, e.g., 8000
            run_cmd = list(result.run_command)
            if run_cmd[-1] == "0":
                run_cmd[-1] = "8000"
            cmd_str = ", ".join(f'"{c}"' for c in run_cmd)
            lines.append(f"CMD [{cmd_str}]")
            
        return "\n".join(lines)
