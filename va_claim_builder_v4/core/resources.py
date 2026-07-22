from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def resource_root() -> Path:
    """Return the read-only resource root for source and PyInstaller execution."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    root = resource_root()
    if any(Path(part).is_absolute() or ".." in Path(part).parts for part in parts):
        raise ValueError("Resource path must remain inside the application resources.")
    # PyInstaller's macOS bundle intentionally uses symlinks from Frameworks
    # to Resources. Do not resolve those symlinks or a valid bundled resource
    # appears to leave the read-only resource root.
    return root.joinpath(*parts)


def documentation_path(name: str = "USER_GUIDE.md") -> Path:
    return resource_path("docs", name)


def writable_temp_dir() -> Path:
    override = os.environ.get("VCB_TEMP_DIR")
    path = Path(override).expanduser() if override else Path(tempfile.gettempdir()) / "VA Claim Builder"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()
