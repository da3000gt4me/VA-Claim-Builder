from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    home: Path
    projects: Path
    logs: Path
    backups: Path
    settings_file: Path

    def ensure(self) -> "AppPaths":
        for path in (self.home, self.projects, self.logs, self.backups):
            path.mkdir(parents=True, exist_ok=True)
        return self


def _default_home() -> Path:
    override = os.environ.get("VCB_HOME")
    if override:
        return Path(override).expanduser().resolve()

    system = platform.system().lower()
    if system == "windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif system == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "VA Claim Builder"


def resolve_app_paths() -> AppPaths:
    home = _default_home()
    return AppPaths(
        home=home,
        projects=home / "Projects",
        logs=home / "Logs",
        backups=home / "Backups",
        settings_file=home / "settings.json",
    ).ensure()
