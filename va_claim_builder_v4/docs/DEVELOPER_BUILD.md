# Developer Build Guide

Install `requirements.txt` and `requirements-packaging.txt`. Run tests before packaging. Use `scripts/build_macos.sh`, `build_linux.sh`, `build_windows.bat`, or `build_portable.sh` on the matching host. The builder cleans output, runs tests, invokes PyInstaller, and writes `release-manifest.json` and `SHA256SUMS.txt` under `dist`. Do not commit generated binaries, credentials, virtual environments, caches, or test artifacts.
