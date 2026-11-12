"""
GraphWidget: Real-time network speed sparkline/graph for CustomTkinter.
Renders 30-second rolling download and upload traffic curves.
"""

import tkinter as tk
import customtkinter as ctk
from core.rules import format_rate


class BandwidthGraph(ctk.CTkFrame):
    def __init__(self, parent, width: int = 340, height: int = 50, **kwargs):
        super().__init__(parent, height=height, fg_color="#18181b", corner_radius=6, **kwargs)
        self.w = width
        self.h = height

        self.canvas = tk.Canvas(
            self,
            width=self.w,
            height=self.h,
            bg="#18181b",
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)

        # Labels overlay
        self.peak_lbl = ctk.CTkLabel(
            self,
            text="Peak: 0 B/s",
            font=ctk.CTkFont(size=9),
            text_color="#71717a",
            fg_color="transparent",
        )
        self.peak_lbl.place(x=8, y=2)

    def update_graph(self, in_data: list, out_data: list):
        self.canvas.delete("all")
        if not in_data or not out_data:
            return

        w = self.canvas.winfo_width() or self.w
        h = self.canvas.winfo_height() or self.h

        max_val = max(max(in_data, default=1), max(out_data, default=1), 1024)
        self.peak_lbl.configure(text=f"Peak: {format_rate(int(max_val))}")

        n = len(in_data)
        if n < 2:
            return

        dx = w / (n - 1)

        # Draw grid lines
        self.canvas.create_line(0, h // 2, w, h // 2, fill="#27272a", dash=(2, 4))
        self.canvas.create_line(0, h - 1, w, h - 1, fill="#27272a")

        # Inbound Points (Download - Emerald Green #10b981)
        in_pts = []
        for i, val in enumerate(in_data):
            x = i * dx
            y = h - (val / max_val) * (h - 6) - 2
            in_pts.extend([x, y])

        if len(in_pts) >= 4:
            self.canvas.create_line(in_pts, fill="#10b981", width=2, smooth=True)

        # Outbound Points (Upload - Violet/Indigo #818cf8)
        out_pts = []
        for i, val in enumerate(out_data):
            x = i * dx
            y = h - (val / max_val) * (h - 6) - 2
            out_pts.extend([x, y])

        if len(out_pts) >= 4:
            self.canvas.create_line(out_pts, fill="#818cf8", width=1.5, smooth=True)
