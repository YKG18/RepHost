# RepoHost

RepoHost takes a public GitHub repository URL, automatically determines how the repository should be run, launches it locally, exposes the running application through a temporary public tunnel, and provides the user with a shareable URL.

## Phase 1 Implementation

This is the initial Phase 1 release of RepoHost. It currently implements:
- Git cloning to temporary workspaces
- Automatic framework detection (Static HTML, Node.js, Python)
- Dependency installation
- Process management & Port detection
- Health checks

## Usage

```bash
# Ensure dependencies are installed
pip install -r requirements.txt

# Run the CLI using python
set PYTHONPATH=.
python cli/main.py https://github.com/octocat/Spoon-Knife.git
```
