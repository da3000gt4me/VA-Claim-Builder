from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_numpy_is_an_explicit_pinned_runtime_dependency() -> None:
    requirements = (ROOT / "requirements-runtime.txt").read_text(encoding="utf-8")
    assert "numpy==2.2.6" in requirements


def test_pyinstaller_collects_numpy_instead_of_excluding_it() -> None:
    spec = (ROOT / "packaging" / "VAClaimBuilder.spec").read_text(encoding="utf-8")
    assert 'collect_dynamic_libs("numpy")' in spec
    assert '"numpy.core._multiarray_umath"' in spec
    excludes = spec.split("excludes=[", 1)[1].split("]", 1)[0]
    assert '"numpy"' not in excludes


def test_dependency_preflight_imports_compiled_numpy_runtime() -> None:
    script = (ROOT / "scripts" / "verify_packaging_dependencies.py").read_text(encoding="utf-8")
    assert "assert numpy.ndarray is not None" in script
    assert "import numpy.core._multiarray_umath" in script
    assert "import pypdf" in script
    assert "import cryptography" in script


def test_source_runtime_diagnostic_records_numpy_resolution(tmp_path: Path) -> None:
    from desktop_app import write_packaged_runtime_diagnostic

    output = tmp_path / "runtime.json"
    assert write_packaged_runtime_diagnostic(str(output))
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["numpy_ndarray_available"] is True
    assert report["numpy_multiarray_imported"] is True
    assert report["numpy_file"]
    assert report["numpy_spec"]


def test_windows_workflow_runs_preflight_inventory_and_frozen_diagnostic() -> None:
    workflow = (ROOT.parent / ".github" / "workflows" / "build-v42-rc.yml").read_text(encoding="utf-8")
    assert "verify_packaging_dependencies.py" in workflow
    assert "inspect_packaged_numpy.py" in workflow
    assert "--diagnostic" in workflow
    smoke = (ROOT / "scripts" / "smoke_macos_bundle.py").read_text(encoding="utf-8")
    assert "VCB_PACKAGED_RUNTIME_DIAGNOSTIC" in smoke
