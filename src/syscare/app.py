from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import APP_NAME
from .core.config import setup_logging
from .ui.icons import window_icon
from .ui.main_window import MainWindow
from .ui.theme import QSS


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(window_icon())
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
