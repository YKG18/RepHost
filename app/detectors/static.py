import os
from pathlib import Path
from typing import Optional
from app.detectors.base import Detector
from app.core.models import DetectorResult, ProjectType

# Common places a static site's real entrypoint lives, in priority order.
# "." must stay first so a root-level index.html is preferred when present.
CANDIDATE_DIRS = [".", "public", "dist", "build", "docs", "site", "www", "out", "static", "src"]

# GitHub is case-sensitive but a surprising number of repos ship
# "Index.html" or similar. Check the common variants explicitly rather than
# relying on exact-case matches.
INDEX_NAMES = ["index.html", "Index.html", "INDEX.HTML", "index.htm", "home.html", "default.html"]

IGNORED_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__"}


class StaticDetector(Detector):
    def detect(self, path: Path) -> Optional[DetectorResult]:
        # 1) Look for a real index file in the common locations.
        for rel_dir in CANDIDATE_DIRS:
            base = path if rel_dir == "." else path / rel_dir
            if not base.is_dir():
                continue
            for name in INDEX_NAMES:
                if (base / name).exists():
                    confidence = 0.55 if rel_dir == "." else 0.5
                    return DetectorResult(
                        project_type=ProjectType.STATIC,
                        framework="HTML",
                        install_command=[],
                        run_command=["python", "-m", "http.server", "0", "--directory", str(base)],
                        confidence=confidence,
                    )

        # 2) No canonical index file anywhere we looked. If there's at least
        # one HTML file somewhere shallow in the tree, still serve the repo
        # so the user gets a working (if unindexed) page rather than nothing.
        best_dir = None
        best_count = 0
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")]
            depth = len(Path(dirpath).relative_to(path).parts)
            if depth > 2:
                dirnames[:] = []
                continue
            html_count = sum(1 for f in filenames if f.lower().endswith((".html", ".htm")))
            if html_count > best_count:
                best_count = html_count
                best_dir = dirpath

        if best_dir is not None:
            return DetectorResult(
                project_type=ProjectType.STATIC,
                framework="HTML",
                install_command=[],
                run_command=["python", "-m", "http.server", "0", "--directory", str(best_dir)],
                confidence=0.3,
            )

        return None
