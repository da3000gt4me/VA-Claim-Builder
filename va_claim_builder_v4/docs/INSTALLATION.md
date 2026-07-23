# Installation

Source execution requires Python 3.11 or 3.12 and `requirements.txt`.

The verified macOS RC2 artifact is a thin arm64 `.app`. Extract the ZIP, optionally move the app to Applications, then open it. RC2 is ad hoc signed but not notarized. If Gatekeeper blocks first launch, verify the checksum, Control-click the app, choose **Open**, and confirm. User data and logs are under `~/Library/Application Support/VA Claim Builder`. Back up projects before uninstalling.

Download builds through **GitHub repository → Actions → Build VA Claim Builder 4.2 RC → completed run → Artifacts**. Choose the macOS RC2 or Windows RC3 artifact. Artifacts are retained for 30 days. Explicitly published prereleases also appear under GitHub Releases.
