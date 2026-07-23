# Developer Build Guide

Run `scripts/build_macos.sh --skip-tests --adhoc-sign --verbose`. It creates `.build-env-macos` from `requirements-runtime.txt` plus pinned PyInstaller dependencies and atomically writes `dist/release`. Run tests separately before `--skip-tests`. Options include `--output-dir`, `--timeout`, `--keep-work`, `--diagnostic`, and `--verbose`.

Future distribution requires Developer ID signing with hardened runtime, `xcrun notarytool`, and `xcrun stapler`. RC2 is only ad hoc signed. Windows and Linux must be built on native hosts. Never commit environments, binaries, caches, credentials, or medical data.

CI builds are defined in `.github/workflows/build-v42-rc.yml`. Manually dispatch the workflow from GitHub Actions. Its macOS and Windows jobs verify checksums and packaged synthetic workflows before uploading artifacts. Prerelease attachment occurs only when `publish_prerelease` is explicitly selected.
