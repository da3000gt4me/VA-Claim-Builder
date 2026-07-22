from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from core.projects.paths import AppPaths, resolve_app_paths


@dataclass(slots=True)
class AISettings:
    provider: str = "openai"
    fallback_provider: str = ""
    openai_api_key: str = ""
    xai_api_key: str = ""
    local_only: bool = False
    redact_before_cloud: bool = True
    model_openai: str = "gpt-4o-mini"
    model_xai: str = "grok-3-mini"


class SettingsManager:
    """Stores application settings and encrypts API credentials at rest."""

    def __init__(self, paths: AppPaths | None = None) -> None:
        self.paths = paths or resolve_app_paths()
        self.settings_path = self.paths.home / "ai_settings.enc"
        self.key_path = self.paths.home / ".settings.key"

    APP_DEFAULTS = {
        "settings_version": 1,
        "backup_retention": 10,
        "backup_include_sources": True,
        "log_level": "INFO",
        "last_workspace": "",
        "last_export_path": "",
        "window_geometry": "",
        "splitter_state": "",
    }

    def load_app_settings(self) -> dict:
        try:
            payload = json.loads(self.paths.settings_file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
        except (OSError, ValueError, json.JSONDecodeError):
            payload = {}
        return {**self.APP_DEFAULTS, **payload}

    def save_app_settings(self, settings: dict) -> None:
        allowed = {key: settings.get(key, value) for key, value in self.APP_DEFAULTS.items()}
        self.paths.home.mkdir(parents=True, exist_ok=True)
        temp = self.paths.settings_file.with_suffix(".tmp")
        temp.write_text(json.dumps(allowed, indent=2), encoding="utf-8")
        temp.replace(self.paths.settings_file)

    def reset_app_settings(self) -> None:
        self.save_app_settings(dict(self.APP_DEFAULTS))

    def export_settings(self, destination: str | Path) -> Path:
        ai = asdict(self.load_ai_settings())
        ai.pop("openai_api_key", None)
        ai.pop("xai_api_key", None)
        output = Path(destination)
        output.write_text(
            json.dumps({"application": self.load_app_settings(), "ai": ai}, indent=2),
            encoding="utf-8",
        )
        return output

    def import_settings(self, source: str | Path) -> None:
        payload = json.loads(Path(source).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Settings file must contain an object.")
        self.save_app_settings(payload.get("application", {}))
        ai_payload = payload.get("ai", {})
        current = self.load_ai_settings()
        for key, value in ai_payload.items():
            if key in AISettings.__dataclass_fields__ and key not in {"openai_api_key", "xai_api_key"}:
                setattr(current, key, value)
        self.save_ai_settings(current)

    def load_ai_settings(self) -> AISettings:
        if not self.settings_path.exists():
            return AISettings()
        try:
            encrypted = self.settings_path.read_bytes()
            payload = json.loads(self._fernet().decrypt(encrypted).decode("utf-8"))
        except (OSError, InvalidToken, json.JSONDecodeError, UnicodeDecodeError):
            return AISettings()
        allowed = AISettings.__dataclass_fields__
        return AISettings(**{key: value for key, value in payload.items() if key in allowed})

    def save_ai_settings(self, settings: AISettings) -> None:
        self.paths.home.mkdir(parents=True, exist_ok=True)
        data = json.dumps(asdict(settings), indent=2).encode("utf-8")
        temp = self.settings_path.with_suffix(".tmp")
        temp.write_bytes(self._fernet().encrypt(data))
        temp.replace(self.settings_path)
        self._restrict_permissions(self.settings_path)

    def clear_api_keys(self) -> AISettings:
        settings = self.load_ai_settings()
        settings.openai_api_key = ""
        settings.xai_api_key = ""
        self.save_ai_settings(settings)
        return settings

    def apply_to_environment(self, settings: AISettings | None = None) -> AISettings:
        settings = settings or self.load_ai_settings()
        self._set_or_clear("OPENAI_API_KEY", settings.openai_api_key)
        self._set_or_clear("XAI_API_KEY", settings.xai_api_key)
        self._set_or_clear("VCB_AI_PROVIDER", settings.provider)
        self._set_or_clear("VCB_AI_FALLBACK", settings.fallback_provider)
        self._set_or_clear("VCB_OPENAI_MODEL", settings.model_openai)
        self._set_or_clear("VCB_XAI_MODEL", settings.model_xai)
        os.environ["VCB_LOCAL_ONLY"] = str(settings.local_only).lower()
        os.environ["VCB_REDACT_BEFORE_CLOUD"] = str(settings.redact_before_cloud).lower()
        return settings

    def _fernet(self) -> Fernet:
        if not self.key_path.exists():
            self.key_path.write_bytes(Fernet.generate_key())
            self._restrict_permissions(self.key_path)
        return Fernet(self.key_path.read_bytes())

    @staticmethod
    def _set_or_clear(name: str, value: str) -> None:
        if value:
            os.environ[name] = value
        else:
            os.environ.pop(name, None)

    @staticmethod
    def _restrict_permissions(path: Path) -> None:
        try:
            path.chmod(0o600)
        except OSError:
            pass
