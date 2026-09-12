from dataclasses import dataclass
from pathlib import Path
@dataclass(frozen=True)
class Project:
    root: Path
    kind: str
    entrypoint: Path | None = None
    command: tuple[str, ...] | None = None
    port: int = 8080
    metadata: dict | None = None
