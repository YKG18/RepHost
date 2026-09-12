from .base import Detector
from .static import StaticDetector
from .node import NodeDetector
from .python import PythonDetector
from typing import List, Optional
from pathlib import Path
from app.core.models import DetectorResult

def detect_project(path: Path) -> Optional[DetectorResult]:
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
            
    return best_result
