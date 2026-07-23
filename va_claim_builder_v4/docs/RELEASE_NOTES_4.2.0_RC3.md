# VA Claim Builder Version 4.2.0 RC3

RC3 adds persistent GitHub Actions release artifacts. Independent Apple Silicon macOS and Windows x64 jobs build in minimal Python 3.12 environments, launch the frozen application, execute synthetic local project/export/backup/restore smoke tests, verify checksums, and upload 30-day workflow artifacts.

The macOS artifact remains labeled RC2. Windows is labeled RC3 and includes a portable ZIP; this pass does not add an installer. Optional GitHub prerelease publishing requires an explicit manual-dispatch input. No binaries are committed. RC3 remains prerelease software.
