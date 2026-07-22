from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from core.projects import ProjectManager
from core.settings import SettingsManager
from ui_qt import MainWindow, ProjectDialog


def configure_logging(manager: ProjectManager) -> None:
    logging.basicConfig(
        filename=manager.paths.logs / "va_claim_builder.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("VA Claim Builder")
    app.setOrganizationName("VA Claim Builder")

    manager = ProjectManager()
    configure_logging(manager)
    SettingsManager(manager.paths).apply_to_environment()
    try:
        project = ProjectDialog.choose_or_create(None, manager)
    except Exception as exc:
        logging.exception("Unable to open project")
        QMessageBox.critical(None, "VA Claim Builder", str(exc))
        return 1
    if project is None:
        return 0

    window = MainWindow(project)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
