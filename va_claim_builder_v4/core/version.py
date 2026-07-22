from __future__ import annotations

import json
import os
from pathlib import Path

_DATA = json.loads(
    (Path(__file__).resolve().parent.parent / "version.json").read_text(encoding="utf-8")
)
VERSION = str(_DATA["version"])
DISPLAY_VERSION = str(_DATA["display_version"])
APP_NAME = "VA Claim Builder"
FULL_NAME = f"{APP_NAME} Version {DISPLAY_VERSION}"
BUILD_METADATA = os.environ.get("VCB_BUILD_METADATA", "").strip()
BUILD_VERSION = VERSION + (f"+{BUILD_METADATA}" if BUILD_METADATA else "")
