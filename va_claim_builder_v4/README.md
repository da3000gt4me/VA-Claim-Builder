
# VA Claim Builder Version 4.2.0 RC4

RC4 adds local-first automated intake. With **Automatically analyze imported
documents** enabled (the default), files proceed from fingerprinting and text
extraction through draft evidence, claim matching, claim suggestions, medical
timeline events, relationship indicators, contradictions, and gaps. Results
remain review items and never replace confirmed user text.

Use **Automation Review** for progress, failures, and bulk
accept/reject/defer actions. Cloud enhancement is disabled by default; importing
a document never sends it to a provider.

VA Claim Builder is a local-first PySide6 desktop application for organizing documents, OCR, claims, evidence, timelines, nexus and DBQ preparation, rating strategy, optimization, and local submission packages.

RC2 is packaged and smoke-tested on Apple Silicon macOS. It remains Release Candidate software, not a final production release, and provides neither medical/legal advice nor outcome guarantees.

Source execution requires Python 3.11 or 3.12. The verified macOS artifact is an ad hoc signed arm64 `.app`, not universal2 or notarized. After verifying its SHA-256 checksum, Gatekeeper may require Control-click > **Open**. User data is stored under `~/Library/Application Support/VA Claim Builder`. Windows and Linux builders remain configured but unverified.

See [User Guide](docs/USER_GUIDE.md), [Installation](docs/INSTALLATION.md), [Privacy](docs/PRIVACY_DATA_HANDLING.md), and [RC2 Release Notes](docs/RELEASE_NOTES_4.2.0_RC2.md).

## Download persistent builds

Open the GitHub repository, choose **Actions**, select **Build VA Claim Builder 4.2 RC**, open a completed run, then download either platform artifact from **Artifacts**. Workflow artifacts are retained for 30 days. Explicitly published prereleases also appear on the Releases page.
