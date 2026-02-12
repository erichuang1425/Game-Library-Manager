"""
Test configuration - mock platform-specific modules unavailable on Linux CI.
"""
import sys
from types import ModuleType
from unittest.mock import MagicMock

# Mock Windows-only modules before any app imports
for mod_name in [
    "pythoncom",
    "win32com",
    "win32com.shell",
    "win32com.shell.shell",
    "winreg",
    "PySide6",
    "PySide6.QtWidgets",
    "PySide6.QtCore",
    "PySide6.QtGui",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()
