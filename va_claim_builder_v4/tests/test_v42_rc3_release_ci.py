from __future__ import annotations

import json
from pathlib import Path

from scripts import build_release


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "build-v42-rc.yml"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_release_workflow_has_manual_tag_and_platform_jobs() -> None:
    text = workflow_text()
    assert "workflow_dispatch:" in text
    assert '"v4.2.0-rc*"' in text
    assert "macos-arm64:" in text and "runs-on: macos-14" in text
    assert "windows-x64:" in text and "runs-on: windows-2022" in text


def test_release_workflow_uploads_persistent_named_artifacts() -> None:
    text = workflow_text()
    assert text.count("actions/upload-artifact@v4") == 2
    assert "retention-days: 30" in text
    assert "VA-Claim-Builder-4.2.0-RC2-macOS-arm64" in text
    assert "VA-Claim-Builder-4.2.0-RC3-Windows-x64" in text
    assert text.count("if-no-files-found: error") == 2


def test_release_workflow_validates_required_outputs_and_smokes() -> None:
    text = workflow_text()
    for required in ("SHA256SUMS.txt", "release-manifest.json", "build.log", "dependency-versions.json", "packaged-smoke-result.json"):
        assert required in text
    assert text.count("scripts/smoke_macos_bundle.py") == 2
    assert "VAClaimBuilder.exe" in text
    assert "shasum -a 256 -c" in text
    assert "Get-FileHash -Algorithm SHA256" in text


def test_prerelease_is_explicit_and_secret_safe() -> None:
    text = workflow_text()
    assert "inputs.publish_prerelease" in text
    assert "--prerelease" in text
    assert "github.token" in text
    assert "API_KEY" not in text and "OPENAI" not in text and "XAI" not in text


def test_windows_release_names_are_deterministic() -> None:
    assert build_release.machine_label("AMD64") == "x64"
    assert build_release.machine_label("x86_64") == "x64"
    assert build_release.release_directory_name("4.2.0 RC3", "windows", "AMD64") == "VAClaimBuilder-4.2.0-RC3-Windows-x64"
    assert build_release.release_directory_name("4.2.0 RC2", "macos", "arm64") == "VAClaimBuilder-4.2.0-RC2-macOS-arm64"


def test_fake_windows_build_creates_portable_zip_manifest_and_checksums(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "release"
    monkeypatch.setattr(build_release.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(build_release.importlib.util, "find_spec", lambda name: object())

    def fake_run(command, **kwargs):
        kwargs["log"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["log"].write_text("synthetic build log", encoding="utf-8")
        if "PyInstaller" in command:
            dist = Path(command[command.index("--distpath") + 1])
            collection = dist / "VAClaimBuilder"
            collection.mkdir(parents=True)
            (collection / "VAClaimBuilder.exe").write_bytes(b"synthetic executable")
        return 0.25

    monkeypatch.setattr(build_release, "run_logged", fake_run)
    result = build_release.main([
        "windows", "--skip-tests", "--output-dir", str(output),
        "--release-version", "4.2.0rc3", "--display-version", "4.2.0 RC3",
    ])
    assert result == 0
    release = output / "VAClaimBuilder-4.2.0-RC3-Windows-x64"
    archive = release / "VA Claim Builder-4.2.0-RC3-Windows-x64.zip"
    assert archive.is_file()
    manifest = json.loads((release / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "4.2.0rc3"
    assert any(item["name"] == archive.name for item in manifest["artifacts"])
    assert archive.name in (release / "SHA256SUMS.txt").read_text(encoding="utf-8")
