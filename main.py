#!/usr/bin/env python3
"""Main entry point for FIT Data Visualizer"""
import sys
from PyQt6.QtWidgets import QApplication

from src.ui import MainWindow


def main():
    """Run the application"""
    app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
