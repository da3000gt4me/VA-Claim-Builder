from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from core.projects import ProjectManager
from core.settings import SettingsManager
from ui_qt import MainWindow, ProjectDialog
from core.version import APP_NAME, BUILD_VERSION


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
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(BUILD_VERSION)
    app.setOrganizationName(APP_NAME)

    manager = ProjectManager()
    configure_logging(manager)
    SettingsManager(manager.paths).apply_to_environment()
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
