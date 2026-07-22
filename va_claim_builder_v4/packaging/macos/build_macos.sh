#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean packaging/VAClaimBuilder.spec
mkdir -p dist/dmg
cp -R "dist/VA Claim Builder.app" dist/dmg/
hdiutil create -volname "VA Claim Builder" -srcfolder dist/dmg -ov -format UDZO "dist/VA_Claim_Builder_4.1.0_macOS.dmg"
echo "Unsigned DMG created. For distribution, sign the app with codesign and notarize it with Apple credentials."
