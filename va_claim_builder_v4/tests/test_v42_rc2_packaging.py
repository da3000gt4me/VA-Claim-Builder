
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from core import resources
from core.projects import AppPaths, ProjectManager
from core.release_smoke import run_packaged_workflow
from core.version import BUILD_VERSION, DISPLAY_VERSION
from scripts import build_release
from scripts.smoke_macos_bundle import bundle_executable


def test_rc6_version_uses_bundled_authoritative_resource() -> None:
    assert BUILD_VERSION.startswith("4.2.0rc6")
    assert DISPLAY_VERSION == "4.2.0 RC6"


def test_resource_resolution_for_source_and_frozen(monkeypatch, tmp_path: Path) -> None:
    assert resources.resource_path("version.json").is_file()
    bundle = tmp_path / "bundle"
    (bundle / "docs").mkdir(parents=True)
    guide = bundle / "docs" / "USER_GUIDE.md"
    guide.write_text("guide", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    assert resources.documentation_path() == guide
    with pytest.raises(ValueError):
        resources.resource_path("..", "secret")


def test_writable_temp_path_supports_spaces_and_unicode(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "Temporary Résumé Files"
    monkeypatch.setenv("VCB_TEMP_DIR", str(target))
    assert resources.writable_temp_dir() == target.resolve()
    assert target.is_dir()


def test_build_command_is_bounded_to_explicit_paths(tmp_path: Path) -> None:
    command = build_release.build_command(tmp_path / "app.spec", tmp_path / "dist", tmp_path / "work", verbose=True)
    assert command[:3] == [sys.executable, "-m", "PyInstaller"]
    assert "--distpath" in command and "--workpath" in command
    assert "--log-level" in command


def test_spec_includes_resources_and_excludes_development_packages() -> None:
    root = Path(__file__).resolve().parents[1]
    spec = (root / "packaging" / "VAClaimBuilder.spec").read_text(encoding="utf-8")
    for required in ("version.json", "docs", "prompts", "PySide6.QtWidgets"):
        assert required in spec
    for excluded in ("pytest", "tests", "streamlit", "pandas", "pyarrow", "notebook"):
        assert f'"{excluded}"' in spec
    assert 'root / ".env"' not in spec and "credentials" not in spec


def test_checksum_and_architecture_report(tmp_path: Path) -> None:
    fixture = tmp_path / "artifact.bin"
    fixture.write_bytes(b"release artifact")
    assert build_release.checksum(fixture) == "133cfccb5b503cf4040c95f3dfad56d07c1574283a1e39066b594f6ee33711ba"
    report = build_release.architecture_report()
    assert report["host_machine"]
    assert report["python_version"]


def test_failed_build_preserves_previous_release(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "release"
    output.mkdir()
    previous = output / "VAClaimBuilder-4.2.0-RC2-macos-arm64"
    previous.mkdir()
    marker = previous / "valid.txt"
    marker.write_text("previous valid release", encoding="utf-8")
    monkeypatch.setattr(build_release.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(build_release.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(build_release, "run_logged", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("simulated")))
    assert build_release.main(["macos", "--skip-tests", "--output-dir", str(output)]) == 1
    assert marker.read_text(encoding="utf-8") == "previous valid release"
    assert not list(output.glob("*.incomplete-*"))


def test_packaged_smoke_helper_exercises_local_workflow(tmp_path: Path) -> None:
    manager = ProjectManager(AppPaths(root=tmp_path / "Application Data").ensure())
    output = tmp_path / "smoke result.json"
    result = run_packaged_workflow(manager, output)
    assert all(value for key, value in result.items() if key != "validation_count")
    assert json.loads(output.read_text(encoding="utf-8"))["backup_valid"] is True


def test_bundle_smoke_helper_requires_real_executable(tmp_path: Path) -> None:
    app = tmp_path / "VA Claim Builder.app"
    with pytest.raises(FileNotFoundError, match="Packaged executable"):
        bundle_executable(app)
    executable = app / "Contents" / "MacOS" / "VAClaimBuilder"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"binary")
    assert bundle_executable(app) == executable
