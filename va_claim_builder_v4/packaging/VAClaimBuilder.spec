from pathlib import Path
import sys

root = Path(SPECPATH).parent
import json
version_data = json.loads((root / "version.json").read_text(encoding="utf-8"))
datas = [
    (str(root / "version.json"), "."),
    (str(root / "docs"), "docs"),
    (str(root / "prompts"), "prompts"),
]
binaries = []
hiddenimports = ["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]

analysis = Analysis(
    [str(root / "desktop_app.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "tests", "streamlit"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="VAClaimBuilder",
    console=False,
    disable_windowed_traceback=False,
)
bundle = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="VAClaimBuilder")
if sys.platform == "darwin":
    app = BUNDLE(
        bundle,
        name="VA Claim Builder.app",
        bundle_identifier="com.vaclaimbuilder.desktop",
        info_plist={"CFBundleShortVersionString": version_data["display_version"], "CFBundleVersion": version_data["version"], "LSMinimumSystemVersion": "12.0"},
    )
