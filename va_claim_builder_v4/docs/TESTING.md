# Testing Guide

Run `python -m pytest -q tests/test_v42_rc2_packaging.py`, `python -m pytest -q tests/test_v42_rc1_hardening.py`, and `QT_QPA_PLATFORM=offscreen python -m pytest -q`. After building, run `python scripts/smoke_macos_bundle.py "dist/release/.../VA Claim Builder.app" --timeout 90`. Tests use temporary synthetic projects and mocked providers; normal tests need no network.

Run `python -m pytest -q tests/test_v42_rc3_release_ci.py` to validate workflow jobs, artifact retention/uploads, output checks, Windows naming, and manifest/checksum generation.
