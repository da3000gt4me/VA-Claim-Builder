# VA Claim Builder Version 4.2.0 RC3

RC3 adds persistent GitHub Actions release artifacts. Independent Apple Silicon macOS and Windows x64 jobs build in minimal Python 3.12 environments, launch the frozen application, execute synthetic local project/export/backup/restore smoke tests, verify checksums, and upload 30-day workflow artifacts.

The macOS artifact remains labeled RC2. Windows is labeled RC3 and includes a portable ZIP; this pass does not add an installer. Optional GitHub prerelease publishing requires an explicit manual-dispatch input. No binaries are committed. RC3 remains prerelease software.

Validation run `29970394164` completed both jobs. The macOS ZIP is 57,784,015 bytes (`82af3d6b2ed690f3aefa300a07f73658b6902625323e4d4d205fb06161277327`). The Windows portable ZIP is 73,287,817 bytes (`5f934313f2403c5e560600dbea1816893a0f8d6741f7128240ac7629a295b8f2`). Both artifacts expire 2026-08-22 unless copied to an explicitly published prerelease.
