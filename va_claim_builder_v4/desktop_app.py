from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import json
import importlib.util
import platform
import traceback
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from core.projects import ProjectManager
from core.settings import SettingsManager
from core.version import APP_NAME, BUILD_VERSION


def write_packaged_runtime_diagnostic(output: str) -> bool:
    """Verify the frozen numerical runtime before importing the application UI."""
    report = {
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "python_architecture": platform.architecture()[0],
        "machine": platform.machine(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "sys_path": list(sys.path),
    }
    try:
        import importlib.metadata
        import numpy
        import numpy.core._multiarray_umath
        import cryptography
        import pypdf

        spec = importlib.util.find_spec("numpy")
        report.update({
            "passed": True,
            "numpy_version": importlib.metadata.version("numpy"),
            "numpy_file": getattr(numpy, "__file__", None),
            "numpy_spec": repr(spec),
            "numpy_ndarray_available": getattr(numpy, "ndarray", None) is not None,
            "numpy_multiarray_imported": True,
            "cryptography_version": importlib.metadata.version("cryptography"),
            "pypdf_version": importlib.metadata.version("pypdf"),
        })
    except Exception:
        report.update({"passed": False, "traceback": traceback.format_exc()})
    Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return bool(report["passed"])


def configure_logging(manager: ProjectManager) -> None:
    handler = RotatingFileHandler(
        manager.paths.logs / "va_claim_builder.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if os.environ.get("VCB_DEBUG") == "1" else logging.INFO)
    root.addHandler(handler)
    logging.info("application_start version=%s", BUILD_VERSION)


def main() -> int:
    runtime_diagnostic = os.environ.get("VCB_PACKAGED_RUNTIME_DIAGNOSTIC")
    if runtime_diagnostic:
        return 0 if write_packaged_runtime_diagnostic(runtime_diagnostic) else 3

    from ui_qt import MainWindow, ProjectDialog

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(BUILD_VERSION)
    app.setOrganizationName(APP_NAME)

    manager = ProjectManager()
    configure_logging(manager)
    SettingsManager(manager.paths).apply_to_environment()
    smoke_output = os.environ.get("VCB_PACKAGED_SMOKE_OUTPUT")
    if smoke_output:
        from core.release_smoke import run_packaged_workflow

        try:
            result = run_packaged_workflow(manager, smoke_output)
            logging.info("packaged_smoke_complete checks=%s", len(result))
            return 0 if all(value for key, value in result.items() if key != "validation_count") else 2
        except Exception:
            logging.exception("packaged_smoke_failed")
            return 2
    extraction_smoke_output = os.environ.get("VCB_PACKAGED_EXTRACTION_SMOKE_OUTPUT")
    if extraction_smoke_output:
        from core.release_smoke import run_packaged_extraction_workflow
        try:
            result = run_packaged_extraction_workflow(manager, extraction_smoke_output)
            logging.info("packaged_extraction_smoke_complete checks=%s", len(result))
            return 0 if all(result.values()) else 2
        except Exception:
            logging.exception("packaged_extraction_smoke_failed")
            return 2
    ui_smoke_marker = os.environ.get("VCB_PACKAGED_UI_SMOKE_MARKER")
    if ui_smoke_marker:
        project = manager.create_project("RC6 UI Smoke")
        window = MainWindow(project)
        window.show()

        def complete_ui_smoke() -> None:
            marker = {
                "window_visible": window.isVisible(),
                "window_title": window.windowTitle(),
                "tab_count": window.tabs.count(),
                "tab_names": [window.tabs.tabText(index) for index in range(window.tabs.count())],
                "log_path": str(manager.paths.logs / "va_claim_builder.log"),
            }
            from pathlib import Path
            import json

            Path(ui_smoke_marker).write_text(json.dumps(marker, indent=2), encoding="utf-8")
            window.close()
            app.quit()

        QTimer.singleShot(1500, complete_ui_smoke)
        return app.exec()
    try:
        project = ProjectDialog.choose_or_create(None, manager)
    except Exception as exc:
        logging.exception("Unable to open project")
        message = QMessageBox(QMessageBox.Critical, "Project Could Not Be Opened", "VA Claim Builder could not open this project safely. Verify the path and permissions, or restore a validated backup.")
        message.setDetailedText(f"{type(exc).__name__}: {exc}")
        message.exec()
        return 1
    if project is None:
        return 0

    window = MainWindow(project)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
