
# Testing Guide

## RC6 defect tests

Run `python -m pytest -q tests/test_v42_rc6_ocr_extraction.py`. GitHub Actions
also runs installed macOS and Windows extraction smokes with seven synthetic
documents and writes `extraction-smoke-result.json`.

Run `python -m pytest -q tests/test_v42_rc2_packaging.py`, `python -m pytest -q tests/test_v42_rc1_hardening.py`, and `QT_QPA_PLATFORM=offscreen python -m pytest -q`. After building, run `python scripts/smoke_macos_bundle.py "dist/release/.../VA Claim Builder.app" --timeout 90`. Tests use temporary synthetic projects and mocked providers; normal tests need no network.

Run `python -m pytest -q tests/test_v42_rc3_release_ci.py` to validate workflow jobs, artifact retention/uploads, output checks, Windows naming, and manifest/checksum generation.
# RC4 automated-intake validation

Run `python -m pytest -q`. RC4 uses synthetic records only and validates local
extraction, state transitions, cancellation/recovery, failure visibility,
deduplication, decision preservation, traceability, matching, draft
pre-population, evidence/timeline creation, persistence, and no provider calls.

The packaged smoke succeeds only when a synthetic import creates evidence,
timeline data, a claim match or suggestion, and Automation Review items.
