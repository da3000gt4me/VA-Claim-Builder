
# Installation

## Local OCR requirement

Scanned PDFs and images require Tesseract. Install with `brew install
tesseract` on macOS or `choco install tesseract` on Windows. Missing engines
produce an explicit page failure. Native PDF, DOCX, and text extraction remains
available.

Source execution requires Python 3.11 or 3.12 and `requirements.txt`.

The verified macOS RC2 artifact is a thin arm64 `.app`. Extract the ZIP, optionally move the app to Applications, then open it. RC2 is ad hoc signed but not notarized. If Gatekeeper blocks first launch, verify the checksum, Control-click the app, choose **Open**, and confirm. User data and logs are under `~/Library/Application Support/VA Claim Builder`. Back up projects before uninstalling.

Download builds through **GitHub repository → Actions → Build VA Claim Builder 4.2 RC → completed run → Artifacts**. Choose the macOS RC2 or Windows RC3 artifact. Artifacts are retained for 30 days. Explicitly published prereleases also appear under GitHub Releases.
# RC4 intake prerequisites

Text PDFs, DOCX, and plain text work locally. Image-only files require Tesseract.
When OCR is unavailable, the document shows a retryable failure instead of being
silently skipped. No AI provider is required for automatic pre-population.
