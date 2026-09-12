@echo off
setlocal
set "PATH=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin;C:\Program Files\Docker\Docker\resources\bin;%PATH%"
set "PYTHONPATH=%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0cli\main.py" %*
