@echo off
python "%~dp0build_release.py" windows --clean
if errorlevel 1 exit /b 1
