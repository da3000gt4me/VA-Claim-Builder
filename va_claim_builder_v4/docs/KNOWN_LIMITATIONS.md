
# Known Limitations

RC2 is not a final production release. macOS verification covers Apple Silicon arm64 only; it is not universal2, Developer ID signed, or notarized. Windows and Linux builds remain unverified. DOCX/image conversion to PDF is not universally available. AI remains advisory, redaction cannot guarantee de-identification, and backup restore does not synchronize copies. The application does not provide medical/legal advice or guarantee outcomes.

Windows RC3 provides a portable ZIP; this pass does not produce an Inno Setup installer. Neither platform artifact has commercial code signing.
# RC4 automation limitations

- Local rules are conservative; poor scans and unusual formatting need review.
- Diagnoses and relationships are suggestions, not medical findings or nexus
  opinions.
- Tesseract is a separate prerequisite for image-only OCR.
- Cloud AI never runs silently.
- Term-overlap claim matching can need manual linking when terminology differs.
- Complex merges and clinician-authored opinions still require manual review.
