from .base import Detector
from .static import StaticDetector
from .node import NodeDetector
from .python import PythonDetector
from typing import List, Optional
from pathlib import Path
from app.core.models import DetectorResult

def _detect_single_path(path: Path, detectors: List[Detector]) -> Optional[DetectorResult]:
    from .environment import detect_environment_variables
    best_result = None
    best_confidence = -1.0
    
    for detector in detectors:
        result = detector.detect(path)
        if result and result.confidence > best_confidence:
            best_result = result
            best_confidence = result.confidence
            
    if best_result:
        env_vars = detect_environment_variables(path)
        if env_vars:
            best_result.env_vars.update(env_vars)
            
    return best_result

def detect_project(root_path: Path) -> List[DetectorResult]:
    """
    Scans the repository and returns a list of detected projects.
    Supports multi-tier architectures (e.g. backend/ and frontend/ folders).
    """
    detectors: List[Detector] = [
        NodeDetector(),
        PythonDetector(),
        StaticDetector()
    ]
    
    results = []
    
    # 1. Check root first
    root_result = _detect_single_path(root_path, detectors)
    if root_result and root_result.confidence > 0.5:
        # High confidence at root (e.g. package.json in root). 
        # Usually means a monolith or single-tier app.
        root_result.sub_path = "."
        results.append(root_result)
        # But we still check subdirectories for multi-tier (e.g. root has backend, frontend folder has UI)
        # Wait, if root has a clear project, we might just use that. Let's still scan.
        
    # 2. Check 1-level deep subdirectories for distinct projects
    for child in root_path.iterdir():
        if child.is_dir() and not child.name.startswith(".") and child.name not in ["node_modules", "venv", "__pycache__", "scratch"]:
            child_result = _detect_single_path(child, detectors)
            # Only accept high-confidence subprojects to avoid false positives
            if child_result and child_result.confidence > 0.5:
                child_result.sub_path = child.name
                results.append(child_result)
                
    # 3. Fallback: If no high-confidence projects found, see if root had a low-confidence one (e.g. Static File Server)
    if not results and root_result:
        root_result.sub_path = "."
        results.append(root_result)

    return results
