# Testing Guide

Run `python -m pytest -q tests/test_v42_rc1_hardening.py` for RC1 checks, `python -m pytest -q tests/test_v42_*.py` for Version 4.2, and `QT_QPA_PLATFORM=offscreen python -m pytest -q` for the full suite. Tests use temporary projects, generated content, mocked providers, and no network. Platform packaging commands are verified on their native operating system.
