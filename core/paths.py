"""
Path helpers for both development mode and PyInstaller standalone (--onefile / --onedir) builds.
"""

import os
import sys


def get_resource_path(relative_path: str) -> str:
    """
    Returns path to bundled read-only resources (assets, drivers).
    Works in normal Python and PyInstaller (_MEIPASS).
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def get_app_data_path(filename: str) -> str:
    """
    Returns writable path for persistent user data (e.g., rules.json).
    Places it next to the .exe for portable standalone use, falling back to %APPDATA%/NetLimiter
    if the exe directory is not writable (e.g., Program Files).
    """
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        if os.access(exe_dir, os.W_OK):
            return os.path.join(exe_dir, filename)
        appdata_dir = os.path.join(os.environ.get("APPDATA", exe_dir), "NetLimiter")
        os.makedirs(appdata_dir, exist_ok=True)
        return os.path.join(appdata_dir, filename)
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, filename)
