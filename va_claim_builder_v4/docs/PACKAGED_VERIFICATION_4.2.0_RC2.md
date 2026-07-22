# macOS Packaged Verification — 4.2.0 RC2

Verified 2026-07-22 on macOS 26.5.2 (25F84), Apple Silicon arm64, with Python 3.12.13 arm64, PyInstaller 6.21.0, and PySide6 6.10.2.

Build: `scripts/build_macos.sh --skip-tests --adhoc-sign --timeout 900`. Smoke test: `.build-env-macos/bin/python scripts/smoke_macos_bundle.py "dist/release/VAClaimBuilder-4.2.0-RC2-macos-arm64/VA Claim Builder.app" --timeout 90`.

The final build took 20.6 seconds total and 17.051 seconds in PyInstaller. The app is 142,568 KiB. The ZIP is 57,604,709 bytes with SHA-256 `81b53a5e673a2ea3e4cf6a27700fd49e523e54fdd101efcb860243a342dced50`. The executable is thin arm64. Automated checks confirmed window visibility/title, 11 workspaces, project creation/reopen/validation, claim/evidence creation, submission export, backup validation, restore, and restored-project open.

Signing is ad hoc; notarization was not attempted. Finder/Gatekeeper on another Mac, Intel, Windows, and Linux are untested. No live AI calls or real medical data were used.
