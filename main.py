#!/usr/bin/env python3
"""Main entry point for My AI Cycling Coach"""
import sys
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from src.ui import MainWindow

_ICON_PATH = Path(__file__).parent / "assets" / "icon.svg"


def main():
    """Run the application"""
    app = QApplication(sys.argv)
    app.setDesktopFileName("my-ai-cycling-coach")
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    if _ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(_ICON_PATH)))

    window = MainWindow()
    if _ICON_PATH.exists():
        window.setWindowIcon(QIcon(str(_ICON_PATH)))
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
