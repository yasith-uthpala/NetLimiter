"""
TrayManager: Integrates NetLimiter into the Windows System Tray (Taskbar Notification area)
using pystray. Allows minimizing to tray so bandwidth shaping runs in background.
"""

import os
import threading
from typing import Callable, Optional
from PIL import Image
import pystray


class TrayManager:
    def __init__(
        self,
        icon_path: str,
        on_open: Callable[[], None],
        on_toggle_pause: Callable[[], None],
        on_exit: Callable[[], None],
        is_paused: Callable[[], bool],
    ):
        self.icon_path = icon_path
        self.on_open = on_open
        self.on_toggle_pause = on_toggle_pause
        self.on_exit = on_exit
        self.is_paused = is_paused

        self._tray_icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._tray_icon:
            return

        image = Image.open(self.icon_path) if os.path.exists(self.icon_path) else Image.new("RGBA", (64, 64), color="#0284c7")

        menu = pystray.Menu(
            pystray.MenuItem("Open NetLimiter", self._handle_open, default=True),
            pystray.MenuItem(self._get_pause_label, self._handle_toggle_pause),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit NetLimiter", self._handle_exit),
        )

        self._tray_icon = pystray.Icon(
            "NetLimiter",
            image,
            "NetLimiter — Bandwidth Controller",
            menu=menu,
        )

        self._thread = threading.Thread(target=self._tray_icon.run, daemon=True)
        self._thread.start()

    def _get_pause_label(self, item=None):
        return "Resume Limiting" if self.is_paused() else "Pause Limiting"

    def _handle_open(self, icon=None, item=None):
        self.on_open()

    def _handle_toggle_pause(self, icon=None, item=None):
        self.on_toggle_pause()
        if self._tray_icon:
            self._tray_icon.update_menu()

    def _handle_exit(self, icon=None, item=None):
        self.stop()
        self.on_exit()

    def stop(self):
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
