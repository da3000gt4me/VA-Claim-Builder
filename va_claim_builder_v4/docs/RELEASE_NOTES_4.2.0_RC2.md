# VA Claim Builder Version 4.2.0 RC2

RC2 completes Apple Silicon macOS packaging. A clean Python 3.12 environment builds an arm64 PyInstaller app in about 20 seconds instead of scanning the full development environment. The release includes an ad hoc signed `.app`, ZIP, checksums, manifest, dependency report, build log, and packaged smoke result.

The frozen app displayed all 11 workspaces and completed a synthetic project, claim, evidence, submission export, validation, backup, restore, and reopen workflow without cloud access. It is not notarized or universal2. Windows and Linux remain unverified. RC2 is not final production software.
