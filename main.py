#!/usr/bin/env python3
"""Main entry point for My AI Cycling Coach"""
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from src.ui import MainWindow


def main():
    """Run the application"""
    app = QApplication(sys.argv)
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
