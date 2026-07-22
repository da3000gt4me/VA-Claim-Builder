# Dependencies

Runtime dependencies are constrained in `requirements.txt`; PyInstaller is isolated in `requirements-packaging.txt`. PySide6 supplies the desktop interface, SQLite is provided by Python, python-docx creates review packets, pypdf handles non-destructive PDF merging, cryptography protects credentials at rest, and provider SDKs support optional cloud AI. Run the diagnostic export for installed versions. System PDF/DOCX conversion tools are optional and are not silently invoked.
