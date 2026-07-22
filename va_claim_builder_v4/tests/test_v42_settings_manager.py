from __future__ import annotations

import os

from core.projects.paths import AppPaths
from core.settings import AISettings, SettingsManager


def _paths(tmp_path):
    return AppPaths(
        home=tmp_path,
        projects=tmp_path / "Projects",
        logs=tmp_path / "Logs",
        backups=tmp_path / "Backups",
        settings_file=tmp_path / "settings.json",
    ).ensure()


def test_ai_settings_are_encrypted_and_round_trip(tmp_path):
    manager = SettingsManager(_paths(tmp_path))
    expected = AISettings(
        provider="xai",
        fallback_provider="openai",
        openai_api_key="openai-secret",
        xai_api_key="xai-secret",
        local_only=False,
        redact_before_cloud=True,
        model_openai="gpt-test",
        model_xai="grok-test",
    )

    manager.save_ai_settings(expected)

    raw = manager.settings_path.read_bytes()
    assert b"openai-secret" not in raw
    assert b"xai-secret" not in raw
    assert manager.load_ai_settings() == expected


def test_apply_settings_updates_environment(tmp_path, monkeypatch):
    manager = SettingsManager(_paths(tmp_path))
    settings = AISettings(
        provider="openai",
        fallback_provider="xai",
        openai_api_key="oa-key",
        xai_api_key="xa-key",
        local_only=True,
        redact_before_cloud=False,
    )

    manager.apply_to_environment(settings)

    assert os.environ["OPENAI_API_KEY"] == "oa-key"
    assert os.environ["XAI_API_KEY"] == "xa-key"
    assert os.environ["VCB_AI_PROVIDER"] == "openai"
    assert os.environ["VCB_AI_FALLBACK"] == "xai"
    assert os.environ["VCB_LOCAL_ONLY"] == "true"
    assert os.environ["VCB_REDACT_BEFORE_CLOUD"] == "false"


def test_clear_api_keys_preserves_non_secret_settings(tmp_path):
    manager = SettingsManager(_paths(tmp_path))
    manager.save_ai_settings(
        AISettings(provider="xai", openai_api_key="one", xai_api_key="two", local_only=True)
    )

    cleared = manager.clear_api_keys()

    assert cleared.provider == "xai"
    assert cleared.local_only is True
    assert cleared.openai_api_key == ""
    assert cleared.xai_api_key == ""
