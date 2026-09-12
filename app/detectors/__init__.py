from .base import Detector
from .static import StaticDetector
from .node import NodeDetector
from .python import PythonDetector
from typing import List, Optional
from pathlib import Path
from app.core.models import DetectorResult

def detect_project(path: Path) -> Optional[DetectorResult]:
    from .environment import detect_environment_variables
    detectors: List[Detector] = [
        NodeDetector(),
        PythonDetector(),
        StaticDetector()
    ]
    
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
