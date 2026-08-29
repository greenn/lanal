from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import __version__
from .database import Database
from .main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Lanal")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Lanal")

    database = Database()
    database.seed_demo_if_empty()

    window = MainWindow(database)
    window.show()
    return app.exec()
