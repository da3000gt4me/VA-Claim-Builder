from pathlib import Path
import os
import sys
from PyInstaller.utils.hooks import collect_dynamic_libs

root = Path(os.environ.get("VCB_SOURCE_ROOT", Path.cwd())).resolve()
import json
version_file = Path(os.environ.get("VCB_VERSION_FILE", root / "version.json")).resolve()
version_data = json.loads(version_file.read_text(encoding="utf-8"))
documentation = ["USER_GUIDE.md", "QUICK_START.md", "INSTALLATION.md", "BACKUP_RESTORE.md", "PRIVACY_DATA_HANDLING.md", "TROUBLESHOOTING.md", "KNOWN_LIMITATIONS.md", "OCR_GUIDE.md", "RELEASE_NOTES_4.2.0_RC1.md", "RELEASE_NOTES_4.2.0_RC2.md", "RELEASE_NOTES_4.2.0_RC4.md", "RELEASE_NOTES_4.2.0_RC6.md", "RELEASE_CHECKLIST_4.2.0_RC6.md", "RC4_INTAKE_AUDIT.md"]
datas = [(str(version_file), "."), (str(root / "prompts"), "prompts")]
datas += [(str(root / "docs" / name), "docs") for name in documentation]
binaries = collect_dynamic_libs("numpy")
hiddenimports = [
    "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
    "numpy.core._multiarray_umath",
    "pypdfium2", "pytesseract",
]

analysis = Analysis(
    [str(root / "desktop_app.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "pytest", "tests", "streamlit", "pandas", "pyarrow",
        "matplotlib", "IPython", "notebook", "jupyter", "tkinter",
        "sqlalchemy.testing", "setuptools", "pip",
    ],
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
