"""
IconExtractor: Extracts high-resolution application icons on Windows using Win32 API.
Provides in-memory caching and fallback icons for CustomTkinter.
"""

import os
from typing import Dict, Optional, Tuple
from PIL import Image, ImageDraw
import customtkinter as ctk

try:
    import win32gui
    import win32ui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


class IconExtractor:
    def __init__(self, icon_size: Tuple[int, int] = (22, 22)):
        self.icon_size = icon_size
        self._cache: Dict[str, ctk.CTkImage] = {}
        self._default_icon = self._create_default_icon()

    def _create_default_icon(self) -> ctk.CTkImage:
        w, h = self.icon_size
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Draw a clean rounded app glyph
        draw.rounded_rectangle([1, 1, w - 2, h - 2], radius=4, fill="#334155", outline="#475569", width=1)
        # Small screen/network dot
        draw.ellipse([w // 2 - 3, h // 2 - 3, w // 2 + 3, h // 2 + 3], fill="#38bdf8")
        return ctk.CTkImage(light_image=img, dark_image=img, size=self.icon_size)

    def get_icon(self, app_name: str, exe_path: Optional[str] = None) -> ctk.CTkImage:
        app_name_lower = app_name.lower()
        if app_name_lower in self._cache:
            return self._cache[app_name_lower]

        pil_img = None
        if HAS_WIN32 and exe_path and os.path.exists(exe_path):
            pil_img = self._extract_from_exe(exe_path)

        # Fallback if no direct exe or failed extraction
        if not pil_img:
            ctk_img = self._default_icon
        else:
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=self.icon_size)

        self._cache[app_name_lower] = ctk_img
        return ctk_img

    def _extract_from_exe(self, exe_path: str) -> Optional[Image.Image]:
        try:
            large, small = win32gui.ExtractIconEx(exe_path, 0)
            hicon = small[0] if small else (large[0] if large else None)
            if not hicon:
                return None

            w, h = self.icon_size
            hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
            hbmp = win32ui.CreateBitmap()
            hbmp.CreateCompatibleBitmap(hdc, w, h)
            hdc_mem = hdc.CreateCompatibleDC()
            hdc_mem.SelectObject(hbmp)

            win32gui.DrawIconEx(hdc_mem.GetSafeHdc(), 0, 0, hicon, w, h, 0, None, win32con.DI_NORMAL)
            bmpinfo = hbmp.GetInfo()
            bmpstr = hbmp.GetBitmapBits(True)
            img = Image.frombuffer("RGBA", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRA", 0, 1)

            # Cleanup
            for h in large:
                try:
                    win32gui.DestroyIcon(h)
                except Exception:
                    pass
            for h in small:
                try:
                    win32gui.DestroyIcon(h)
                except Exception:
                    pass

            hdc_mem.DeleteDC()
            hdc.DeleteDC()
            win32gui.DeleteObject(hbmp.GetHandle())

            return img
        except Exception:
            return None
