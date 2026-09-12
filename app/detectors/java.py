import re
from pathlib import Path
from typing import Optional, List
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType
from app.detectors.api_inspector import ApiInspector


class JavaDetector(Detector):
    def detect(self, path: Path) -> Optional[DetectorResult]:
        pom = path / "pom.xml"
        build_gradle = path / "build.gradle"
        build_gradle_kts = path / "build.gradle.kts"

        has_pom = pom.exists()
        has_gradle = build_gradle.exists() or build_gradle_kts.exists()

        if not has_pom and not has_gradle:
            return None

        framework = "Java"
        package_manager = "maven" if has_pom else "gradle"
        manifest_content = ""

        if has_pom:
            try:
                manifest_content = pom.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
        elif has_gradle:
            for g_file in [build_gradle, build_gradle_kts]:
                if g_file.exists():
                    try:
                        manifest_content += g_file.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        pass

        # Framework heuristics
        if "spring-boot" in manifest_content or "springframework.boot" in manifest_content:
            framework = "Spring Boot"
        elif "io.quarkus" in manifest_content:
            framework = "Quarkus"
        elif "io.micronaut" in manifest_content:
            framework = "Micronaut"

        # Commands
        if package_manager == "maven":
            has_mvnw = (path / "mvnw").exists()
            mvn_cmd = "./mvnw" if has_mvnw else "mvn"
            install_command = [mvn_cmd, "clean", "package", "-DskipTests"]
            run_command = [mvn_cmd, "spring-boot:run"] if framework == "Spring Boot" else ["java", "-jar", "target/app.jar"]
        else:
            has_gradlew = (path / "gradlew").exists()
            gradle_cmd = "./gradlew" if has_gradlew else "gradle"
            install_command = [gradle_cmd, "build", "-x", "test"]
            run_command = [gradle_cmd, "bootRun"] if framework == "Spring Boot" else ["java", "-jar", "build/libs/app.jar"]

        is_api, docs_url, api_endpoints = ApiInspector.inspect(path, framework)

        # Ensure default Spring Boot docs path if none detected
        if not docs_url and is_api:
            docs_url = "/swagger-ui/index.html"

        return DetectorResult(
            project_type=ProjectType.JAVA,
            framework=framework,
            package_manager=package_manager,
            install_command=install_command,
            run_command=run_command,
            expected_ports=[8080, 8000],
            confidence=0.9,
            is_backend_api=is_api,
            docs_url=docs_url,
            api_endpoints=api_endpoints
        )
