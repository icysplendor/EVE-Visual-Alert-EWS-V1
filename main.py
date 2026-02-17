import sys
import os
import ctypes
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow

# Hi-DPI Fix
def apply_dpi_fix():
    if os.name == 'nt':
        try: ctypes.windll.shcore.SetProcessDpiAwareness(2) 
        except: pass

if __name__ == "__main__":
    apply_dpi_fix()
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
