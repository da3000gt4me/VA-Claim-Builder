from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True, init=False)
class AppPaths:
    home: Path
    projects: Path
    logs: Path
    backups: Path
    settings_file: Path

    def __init__(
        self,
        home: Path | None = None,
        projects: Path | None = None,
        logs: Path | None = None,
        backups: Path | None = None,
        settings_file: Path | None = None,
        *,
        root: Path | None = None,
    ) -> None:
        """Accept both the original ``home`` name and the V4.2 ``root`` alias."""
        base = Path(home or root) if (home is not None or root is not None) else _default_home()
        object.__setattr__(self, "home", base)
        object.__setattr__(self, "projects", Path(projects or base / "Projects"))
        object.__setattr__(self, "logs", Path(logs or base / "Logs"))
        object.__setattr__(self, "backups", Path(backups or base / "Backups"))
        object.__setattr__(self, "settings_file", Path(settings_file or base / "settings.json"))

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
