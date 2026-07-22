# VA Claim Builder Version 4.2.0 RC1

VA Claim Builder is a local-first PySide6 desktop application for organizing a VA claim project. Version 4.2 includes project and document management, OCR, claims, evidence review and association, advisory AI evidence analysis, a medical timeline, nexus-draft preparation, DBQ preparation, rating strategy, claim optimization, and local submission-package generation.

This is Release Candidate software for real-world testing, not a final production release. It assists organization and review; it is not legal representation, a medical determination, or a guarantee of a VA outcome.

## Start

Use Python 3.11 or 3.12, create a virtual environment, install `requirements.txt`, and run:

```shell
python desktop_app.py
```

Cloud AI is optional. API credentials are encrypted in the platform application-data directory. Enable **Local-only** to prevent cloud provider calls. Package generation, backups, restore, diagnostics, and project validation operate locally.

## Release verification

```shell
python -m pytest -q tests/test_v42_rc1_hardening.py
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

See [Quick Start](docs/QUICK_START.md), [User Guide](docs/USER_GUIDE.md), [Installation](docs/INSTALLATION.md), [Privacy](docs/PRIVACY_DATA_HANDLING.md), [Backup and Restore](docs/BACKUP_RESTORE.md), [Troubleshooting](docs/TROUBLESHOOTING.md), and [RC1 Release Notes](docs/RELEASE_NOTES_4.2.0_RC1.md).
