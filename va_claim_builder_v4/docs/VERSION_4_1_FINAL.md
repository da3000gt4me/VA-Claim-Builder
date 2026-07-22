# VA Claim Builder 4.1 Final

Version 4.1 closes the planned feature roadmap. It adds adversarial review, alternative claim-theory comparison, factual C&P preparation, accredited-representative export, final factual/file audit, and closeout gating.

## Desktop applications

The repository includes reproducible desktop build projects:

- Windows: `packaging/windows/build_windows.ps1` creates a PyInstaller application and, when Inno Setup is installed, a Setup EXE.
- macOS: `packaging/macos/build_macos.sh` creates an `.app` bundle and unsigned DMG.
- GitHub Actions: `.github/workflows/build-desktop.yml` builds both operating-system artifacts on native hosted runners.

Native applications must be built on the target operating system. Public macOS distribution requires Apple Developer signing and notarization. Public Windows distribution should use Authenticode signing to reduce SmartScreen warnings. Signing identities are not included.
