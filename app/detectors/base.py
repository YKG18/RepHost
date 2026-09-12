from abc import ABC, abstractmethod
from typing import Optional
from pathlib import Path
from app.core.models import DetectorResult

class Detector(ABC):
    @abstractmethod
    def detect(self, path: Path) -> Optional[DetectorResult]:
        """Inspect the directory and return a DetectorResult if applicable."""
        pass
