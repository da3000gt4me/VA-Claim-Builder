@echo off
python "%~dp0build_release.py" windows --clean --release-version 4.2.0rc3 --display-version "4.2.0 RC3" %*
if errorlevel 1 exit /b 1
