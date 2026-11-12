"""
NetLimiter GUI: Optimized, ultra-lightweight desktop interface.
Features:
- Windows application icon extraction
- Process deduplication & application grouping
- Real-time rolling bandwidth graph
- Sort by speed, name, or connection count
- Fully closes on exit (zero background lingering)
"""

import os
import sys
import tkinter as tk
from tkinter import messagebox
from typing import Dict, List, Optional, Any
import customtkinter as ctk

from core.flow_tracker import FlowTracker
from core.limiter import LimiterEngine
from core.monitor import SpeedMonitor
from core.rules import RuleManager, LimitRule, format_rate
from core.icon_extractor import IconExtractor
from gui.graph_widget import BandwidthGraph
from gui.rule_dialog import RuleDialog, AddManualRuleDialog, MasterLimitDialog

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class NetLimiterApp(ctk.CTk):
    def __init__(self, engine: LimiterEngine, rules: RuleManager, flow_tracker: FlowTracker, monitor: SpeedMonitor):
        super().__init__()

        self.engine = engine
        self.rules = rules
        self.flow_tracker = flow_tracker
        self.monitor = monitor

        self.title("NetLimiter — Bandwidth Traffic Controller")
        self.geometry("1040x680")
        self.minsize(880, 560)

        # Asset Paths
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.icon_path_ico = os.path.join(self.base_dir, "assets", "icon.ico")
        self.icon_path_png = os.path.join(self.base_dir, "assets", "icon.png")

        if os.path.exists(self.icon_path_ico):
            try:
                self.iconbitmap(self.icon_path_ico)
            except Exception:
                pass

        self.icon_extractor = IconExtractor(icon_size=(24, 24))

        # UI State
        self._active_tab = "processes"
        self._search_query = ""
        self._sort_mode = "Download Speed"
        self._expanded_apps = set()
        self._group_row_widgets = {}

        self._init_layout()
        self._start_refresh_timer()

    def _init_layout(self):
        # 1. Top Bar
        top_bar = ctk.CTkFrame(self, height=68, corner_radius=0, fg_color="#18181b")
        top_bar.pack(fill="x", side="top")

        # Left: Brand & Status
        title_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        title_box.pack(side="left", padx=20, pady=10)

        app_icon_img = self.icon_extractor.get_icon("netlimiter", self.icon_path_png)
        logo_lbl = ctk.CTkLabel(title_box, image=app_icon_img, text="")
        logo_lbl.pack(side="left", padx=(0, 8))

        brand_lbl = ctk.CTkLabel(
            title_box,
            text="NetLimiter",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#38bdf8",
        )
        brand_lbl.pack(side="left")

        self.status_badge = ctk.CTkLabel(
            title_box,
            text="● Limiter Active",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#10b981",
            padx=10,
        )
        self.status_badge.pack(side="left", padx=(10, 0))

        # Right: Speed Graph & Meter Cards
        meters_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        meters_box.pack(side="right", padx=20, pady=8)

        # Real-time Bandwidth Sparkline Graph
        self.graph = BandwidthGraph(meters_box, width=220, height=46)
        self.graph.pack(side="left", padx=(0, 15))

        # Download Meter Card
        down_card = ctk.CTkFrame(meters_box, fg_color="#0f291e", corner_radius=8, width=130, height=44)
        down_card.pack(side="left", padx=4)
        down_card.pack_propagate(False)

        down_sub = ctk.CTkLabel(down_card, text="DOWNLOAD", font=ctk.CTkFont(size=9, weight="bold"), text_color="#059669")
        down_sub.pack(pady=(3, 0))
        self.down_speed_lbl = ctk.CTkLabel(
            down_card,
            text="↓ 0.0 KB/s",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#34d399",
        )
        self.down_speed_lbl.pack(pady=(0, 4))

        # Upload Meter Card
        up_card = ctk.CTkFrame(meters_box, fg_color="#1e1b4b", corner_radius=8, width=130, height=44)
        up_card.pack(side="left", padx=4)
        up_card.pack_propagate(False)

        up_sub = ctk.CTkLabel(up_card, text="UPLOAD", font=ctk.CTkFont(size=9, weight="bold"), text_color="#6366f1")
        up_sub.pack(pady=(3, 0))
        self.up_speed_lbl = ctk.CTkLabel(
            up_card,
            text="↑ 0.0 KB/s",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#818cf8",
        )
        self.up_speed_lbl.pack(pady=(0, 4))

        # 2. Control Toolbar
        toolbar = ctk.CTkFrame(self, height=50, fg_color="#202023", corner_radius=0)
        toolbar.pack(fill="x", side="top", padx=0, pady=0)

        # Tab Selector
        self.tab_selector = ctk.CTkSegmentedButton(
            toolbar,
            values=["Active Applications", "Configured Rules"],
            command=self._on_tab_changed,
            width=270,
        )
        self.tab_selector.set("Active Applications")
        self.tab_selector.pack(side="left", padx=20, pady=10)

        # Search Box
        self.search_entry = ctk.CTkEntry(
            toolbar,
            placeholder_text="Search application name or PID...",
            width=240,
        )
        self.search_entry.pack(side="left", padx=10, pady=10)
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)

        # Sort Mode Dropdown
        sort_lbl = ctk.CTkLabel(toolbar, text="Sort by:", font=ctk.CTkFont(size=11), text_color="#94a3b8")
        sort_lbl.pack(side="left", padx=(10, 4))

        self.sort_menu = ctk.CTkOptionMenu(
            toolbar,
            values=["Download Speed", "Upload Speed", "Application Name", "Socket Count"],
            command=self._on_sort_changed,
            width=150,
            fg_color="#27272a",
            button_color="#3f3f46",
        )
        self.sort_menu.set("Download Speed")
        self.sort_menu.pack(side="left", padx=4)

        # Master PC Speed Limit Button
        self.master_btn = ctk.CTkButton(
            toolbar,
            text="🌐 Master Limit: OFF",
            width=165,
            fg_color="#27272a",
            hover_color="#3f3f46",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._open_master_limit_dialog,
        )
        self.master_btn.pack(side="left", padx=(12, 4))

        # Action Buttons (Clean & Generic)
        self.pause_btn = ctk.CTkButton(
            toolbar,
            text="Pause Limiter",
            fg_color="#3f3f46",
            hover_color="#52525b",
            width=115,
            command=self._toggle_pause,
        )
        self.pause_btn.pack(side="right", padx=15, pady=10)

        add_rule_btn = ctk.CTkButton(
            toolbar,
            text="+ Add App Rule",
            fg_color="#0284c7",
            hover_color="#0369a1",
            width=125,
            command=self._open_add_rule_dialog,
        )
        add_rule_btn.pack(side="right", padx=(0, 6), pady=10)

        # 3. Content Area
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self._init_processes_view()
        self._init_rules_view()

        # 4. Status Bar
        status_bar = ctk.CTkFrame(self, height=28, fg_color="#18181b", corner_radius=0)
        status_bar.pack(fill="x", side="bottom")

        self.footer_status = ctk.CTkLabel(
            status_bar,
            text="Limiter Service: Ready | High-Performance Engine",
            font=ctk.CTkFont(size=11),
            text_color="#71717a",
        )
        self.footer_status.pack(side="left", padx=15, pady=4)

        self.footer_stats = ctk.CTkLabel(
            status_bar,
            text="0 Applications | 0 Rules Configured",
            font=ctk.CTkFont(size=11),
            text_color="#71717a",
        )
        self.footer_stats.pack(side="right", padx=15, pady=4)

    def _init_processes_view(self):
        self.proc_container = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.proc_container.pack(fill="both", expand=True)

        header = ctk.CTkFrame(self.proc_container, height=36, fg_color="#27272a", corner_radius=6)
        header.pack(fill="x", pady=(0, 6))

        cols = [
            ("Application", 0.35, "w"),
            ("Sockets", 0.09, "center"),
            ("Download Speed", 0.15, "center"),
            ("Upload Speed", 0.15, "center"),
            ("Active Bandwidth Rule", 0.15, "center"),
            ("Action", 0.11, "center"),
        ]
        for name, relwidth, anchor in cols:
            lbl = ctk.CTkLabel(
                header,
                text=name,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#a1a1aa",
                anchor=anchor,
            )
            lbl.place(relx=sum([c[1] for c in cols[:cols.index((name, relwidth, anchor))]]), rely=0.15, relwidth=relwidth)

        self.proc_scroll = ctk.CTkScrollableFrame(self.proc_container, fg_color="transparent")
        self.proc_scroll.pack(fill="both", expand=True)

    def _init_rules_view(self):
        self.rules_container = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.rules_scroll = ctk.CTkScrollableFrame(self.rules_container, fg_color="transparent")
        self.rules_scroll.pack(fill="both", expand=True)

    def _on_tab_changed(self, choice: str):
        if choice == "Active Applications":
            self._active_tab = "processes"
            self.rules_container.pack_forget()
            self.proc_container.pack(fill="both", expand=True)
            self._update_process_list(force=True)
        else:
            self._active_tab = "rules"
            self.proc_container.pack_forget()
            self.rules_container.pack(fill="both", expand=True)
            self._update_rules_list()

    def _on_search_changed(self, event=None):
        self._search_query = self.search_entry.get().strip().lower()
        if self._active_tab == "processes":
            self._update_process_list(force=True)
        else:
            self._update_rules_list()

    def _on_sort_changed(self, choice: str):
        self._sort_mode = choice
        self._update_process_list(force=True)

    def _toggle_pause(self):
        if self.engine.global_paused:
            self.engine.set_global_paused(False)
            self.pause_btn.configure(text="Pause Limiter", fg_color="#3f3f46")
        else:
            self.engine.set_global_paused(True)
            self.pause_btn.configure(text="Resume Limiter", fg_color="#b45309")

    def _open_master_limit_dialog(self):
        enabled, in_bps, out_bps = self.rules.get_master_limit()
        MasterLimitDialog(
            self,
            current_in_bps=in_bps,
            current_out_bps=out_bps,
            enabled=enabled,
            on_save=self._on_master_limit_saved,
        )

    def _on_master_limit_saved(self, in_bps: int, out_bps: int, enabled: bool):
        self.rules.set_master_limit(in_bps, out_bps, enabled)
        self._refresh_ui()

    def _open_add_rule_dialog(self):
        AddManualRuleDialog(self, on_save=self._on_rule_saved)

    def _on_rule_saved(self, rule: LimitRule):
        self.rules.set_rule(rule.app_name, rule.pid, rule.inbound_bps, rule.outbound_bps, rule.enabled)
        if self._active_tab == "processes":
            self._update_process_list(force=True)
        else:
            self._update_rules_list()

    def _on_rule_deleted(self, app_name: str, pid: Optional[int]):
        self.rules.remove_rule(app_name, pid)
        if self._active_tab == "processes":
            self._update_process_list(force=True)
        else:
            self._update_rules_list()

    def _start_refresh_timer(self):
        self._refresh_ui()

    def _refresh_ui(self):
        try:
            # 1. Update Master Limit Button
            m_enabled, m_in, m_out = self.rules.get_master_limit()
            if m_enabled:
                in_s = format_rate(m_in)
                out_s = format_rate(m_out)
                self.master_btn.configure(
                    text=f"🌐 Master PC Cap: ↓ {in_s}",
                    fg_color="#b45309",
                    hover_color="#92400e",
                )
            else:
                self.master_btn.configure(
                    text="🌐 Master Limit: OFF",
                    fg_color="#27272a",
                    hover_color="#3f3f46",
                )

            # 2. Update engine status badge
            if m_enabled:
                self.status_badge.configure(text=f"● Master PC Cap Active ({format_rate(m_in)})", text_color="#f59e0b")
            elif self.engine.status == "RUNNING":
                if self.engine.global_paused:
                    self.status_badge.configure(text="● Limiter Paused", text_color="#f59e0b")
                else:
                    self.status_badge.configure(text="● Engine Active", text_color="#10b981")
            elif self.engine.status == "RUNNING_QOS":
                if self.engine.global_paused:
                    self.status_badge.configure(text="● Limiter Paused", text_color="#f59e0b")
                else:
                    self.status_badge.configure(text="● Native QoS Active", text_color="#38bdf8")
            else:
                self.status_badge.configure(text=f"● {self.engine.status_message}", text_color="#94a3b8")

            # 3. Update Total Speeds & Sparkline Graph
            total_in, total_out = self.monitor.get_total_speed()
            self.down_speed_lbl.configure(text=f"↓ {format_rate(int(total_in))}")
            self.up_speed_lbl.configure(text=f"↑ {format_rate(int(total_out))}")

            in_hist, out_hist = self.monitor.get_history()
            self.graph.update_graph(in_hist, out_hist)

            # 3. Refresh Active View
            if self._active_tab == "processes":
                self._update_process_list(force=False)
            else:
                self._update_rules_list()

        except Exception:
            pass

        # Schedule next tick every 1000ms (lightweight, minimal CPU impact)
        self.after(1000, self._refresh_ui)

    def _update_process_list(self, force: bool = False):
        grouped = self.flow_tracker.get_grouped_processes()

        for g in grouped:
            in_s, out_s = self.monitor.get_app_speed(g["name"])
            g["in_speed"] = in_s
            g["out_speed"] = out_s

        if self._search_query:
            grouped = [
                g for g in grouped
                if self._search_query in g["name"].lower()
                or any(self._search_query in str(p["pid"]) for p in g["pids"])
            ]

        if self._sort_mode == "Download Speed":
            grouped.sort(key=lambda x: x["in_speed"], reverse=True)
        elif self._sort_mode == "Upload Speed":
            grouped.sort(key=lambda x: x["out_speed"], reverse=True)
        elif self._sort_mode == "Socket Count":
            grouped.sort(key=lambda x: x["total_sockets"], reverse=True)
        else:
            grouped.sort(key=lambda x: x["name"].lower())

        rules_count = len(self.rules.get_all_rules())
        total_pids = sum(len(g["pids"]) for g in grouped)
        self.footer_stats.configure(
            text=f"{len(grouped)} Applications ({total_pids} Processes) | {rules_count} Rules Configured"
        )

        current_app_names = {g["name"].lower() for g in grouped}

        if force:
            for widget in self.proc_scroll.winfo_children():
                widget.destroy()
            self._group_row_widgets.clear()
        else:
            for app_key in list(self._group_row_widgets.keys()):
                if app_key not in current_app_names:
                    row_frame = self._group_row_widgets[app_key]["frame"]
                    row_frame.destroy()
                    del self._group_row_widgets[app_key]

        for g in grouped:
            name = g["name"]
            app_key = name.lower()
            exe = g["exe"]
            total_sockets = g["total_sockets"]
            pids = g["pids"]
            in_speed = g["in_speed"]
            out_speed = g["out_speed"]

            rule = self.rules.get_rule_for_process(name, 0)
            in_speed_str = format_rate(int(in_speed))
            out_speed_str = format_rate(int(out_speed))

            if rule and rule.enabled:
                in_lim = format_rate(rule.inbound_bps)
                out_lim = format_rate(rule.outbound_bps)
                limit_text = f"↓ {in_lim} | ↑ {out_lim}"
                limit_color = "#38bdf8"
            elif rule and not rule.enabled:
                limit_text = "Rule Disabled"
                limit_color = "#71717a"
            else:
                limit_text = "Unlimited"
                limit_color = "#94a3b8"

            instances_count = len(pids)
            sub_text = f"{instances_count} processes" if instances_count > 1 else f"PID {pids[0]['pid']}"

            if app_key in self._group_row_widgets:
                w = self._group_row_widgets[app_key]
                w["sockets_lbl"].configure(text=str(total_sockets))
                w["down_lbl"].configure(text=f"↓ {in_speed_str}", text_color="#34d399" if in_speed > 0 else "#64748b")
                w["up_lbl"].configure(text=f"↑ {out_speed_str}", text_color="#818cf8" if out_speed > 0 else "#64748b")
                w["limit_lbl"].configure(text=limit_text, text_color=limit_color)
                w["sub_lbl"].configure(text=sub_text)

                if app_key in self._expanded_apps and "children_frame" in w:
                    self._update_children_pids(w["children_frame"], name, pids)
            else:
                group_card = ctk.CTkFrame(self.proc_scroll, fg_color="#1f1f23", corner_radius=6)
                group_card.pack(fill="x", pady=2)

                row_frame = ctk.CTkFrame(group_card, height=48, fg_color="transparent")
                row_frame.pack(fill="x")

                cols = [0.35, 0.09, 0.15, 0.15, 0.15, 0.11]

                name_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
                name_frame.place(relx=0.0, rely=0.05, relwidth=cols[0], relheight=0.90)

                if instances_count > 1:
                    exp_text = "▼" if app_key in self._expanded_apps else "▶"
                    exp_btn = ctk.CTkButton(
                        name_frame,
                        text=exp_text,
                        width=20,
                        height=20,
                        fg_color="transparent",
                        text_color="#94a3b8",
                        hover_color="#27272a",
                        command=lambda k=app_key: self._toggle_expand(k),
                    )
                    exp_btn.pack(side="left", padx=(6, 2))
                else:
                    exp_btn = None
                    pad = ctk.CTkFrame(name_frame, width=20, height=20, fg_color="transparent")
                    pad.pack(side="left", padx=(6, 2))

                icon_img = self.icon_extractor.get_icon(name, exe)
                icon_lbl = ctk.CTkLabel(name_frame, image=icon_img, text="")
                icon_lbl.pack(side="left", padx=(2, 8))

                text_box = ctk.CTkFrame(name_frame, fg_color="transparent")
                text_box.pack(side="left", fill="x", expand=True)

                app_title = ctk.CTkLabel(
                    text_box,
                    text=name,
                    font=ctk.CTkFont(size=13, weight="bold"),
                    anchor="w",
                )
                app_title.pack(anchor="w")

                sub_lbl = ctk.CTkLabel(
                    text_box,
                    text=sub_text,
                    font=ctk.CTkFont(size=10),
                    text_color="#71717a",
                    anchor="w",
                )
                sub_lbl.pack(anchor="w")

                x_pos = cols[0]
                sockets_lbl = ctk.CTkLabel(row_frame, text=str(total_sockets), font=ctk.CTkFont(size=12), text_color="#94a3b8")
                sockets_lbl.place(relx=x_pos, rely=0.25, relwidth=cols[1])

                x_pos += cols[1]
                down_lbl = ctk.CTkLabel(
                    row_frame,
                    text=f"↓ {in_speed_str}",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="#34d399" if in_speed > 0 else "#64748b",
                )
                down_lbl.place(relx=x_pos, rely=0.25, relwidth=cols[2])

                x_pos += cols[2]
                up_lbl = ctk.CTkLabel(
                    row_frame,
                    text=f"↑ {out_speed_str}",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="#818cf8" if out_speed > 0 else "#64748b",
                )
                up_lbl.place(relx=x_pos, rely=0.25, relwidth=cols[3])

                x_pos += cols[3]
                limit_lbl = ctk.CTkLabel(
                    row_frame,
                    text=limit_text,
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color=limit_color,
                )
                limit_lbl.place(relx=x_pos, rely=0.25, relwidth=cols[4])

                x_pos += cols[4]
                btn_action = ctk.CTkButton(
                    row_frame,
                    text="Set Limit",
                    width=75,
                    height=28,
                    font=ctk.CTkFont(size=11, weight="bold"),
                    fg_color="#0284c7" if rule else "#374151",
                    hover_color="#0369a1" if rule else "#4b5563",
                    command=lambda p_name=name: self._open_rule_dialog(p_name, None),
                )
                btn_action.place(relx=x_pos + 0.01, rely=0.20, relwidth=cols[5] - 0.02)

                children_frame = None
                if app_key in self._expanded_apps:
                    children_frame = ctk.CTkFrame(group_card, fg_color="#18181b", corner_radius=4)
                    children_frame.pack(fill="x", padx=10, pady=(0, 6))
                    self._update_children_pids(children_frame, name, pids)

                self._group_row_widgets[app_key] = {
                    "frame": group_card,
                    "sockets_lbl": sockets_lbl,
                    "down_lbl": down_lbl,
                    "up_lbl": up_lbl,
                    "limit_lbl": limit_lbl,
                    "sub_lbl": sub_lbl,
                    "exp_btn": exp_btn,
                    "children_frame": children_frame,
                }

    def _toggle_expand(self, app_key: str):
        if app_key in self._expanded_apps:
            self._expanded_apps.remove(app_key)
        else:
            self._expanded_apps.add(app_key)
        self._update_process_list(force=True)

    def _update_children_pids(self, container: ctk.CTkFrame, app_name: str, pids: list):
        for w in container.winfo_children():
            w.destroy()

        for p in pids:
            pid = p["pid"]
            sockets = p["active_sockets"]
            in_s, out_s = self.monitor.get_process_speed(pid)
            pid_rule = self.rules.get_rule_for_process(app_name, pid)

            crow = ctk.CTkFrame(container, height=28, fg_color="transparent")
            crow.pack(fill="x", padx=15, pady=2)

            lbl_pid = ctk.CTkLabel(
                crow,
                text=f"↳ PID {pid}",
                font=ctk.CTkFont(size=11),
                text_color="#94a3b8",
                width=180,
                anchor="w",
            )
            lbl_pid.pack(side="left")

            lbl_soc = ctk.CTkLabel(crow, text=f"{sockets} sockets", font=ctk.CTkFont(size=11), text_color="#71717a", width=100)
            lbl_soc.pack(side="left")

            lbl_in = ctk.CTkLabel(
                crow,
                text=f"↓ {format_rate(int(in_s))}",
                font=ctk.CTkFont(size=11),
                text_color="#34d399" if in_s > 0 else "#64748b",
                width=120,
            )
            lbl_in.pack(side="left")

            lbl_out = ctk.CTkLabel(
                crow,
                text=f"↑ {format_rate(int(out_s))}",
                font=ctk.CTkFont(size=11),
                text_color="#818cf8" if out_s > 0 else "#64748b",
                width=120,
            )
            lbl_out.pack(side="left")

            btn_pid = ctk.CTkButton(
                crow,
                text="Limit PID",
                width=65,
                height=22,
                font=ctk.CTkFont(size=10),
                fg_color="#0284c7" if pid_rule else "#27272a",
                command=lambda p_id=pid: self._open_rule_dialog(app_name, p_id),
            )
            btn_pid.pack(side="right", padx=5)

    def _update_rules_list(self):
        for widget in self.rules_scroll.winfo_children():
            widget.destroy()

        all_rules = self.rules.get_all_rules()
        if self._search_query:
            all_rules = [
                r for r in all_rules
                if self._search_query in r.app_name or (r.pid and self._search_query in str(r.pid))
            ]

        if not all_rules:
            empty_lbl = ctk.CTkLabel(
                self.rules_scroll,
                text="No configured rules yet.\nClick '+ Add App Rule' or select an application from Active Applications.",
                font=ctk.CTkFont(size=13),
                text_color="#71717a",
            )
            empty_lbl.pack(pady=40)
            return

        for rule in all_rules:
            row_frame = ctk.CTkFrame(self.rules_scroll, height=56, fg_color="#1f1f23", corner_radius=6)
            row_frame.pack(fill="x", pady=3)

            info_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            info_frame.pack(side="left", padx=15, pady=8)

            icon_img = self.icon_extractor.get_icon(rule.app_name)
            icon_lbl = ctk.CTkLabel(info_frame, image=icon_img, text="")
            icon_lbl.pack(side="left", padx=(0, 10))

            text_col = ctk.CTkFrame(info_frame, fg_color="transparent")
            text_col.pack(side="left")

            target_str = f"{rule.app_name} (PID {rule.pid})" if rule.pid else f"{rule.app_name} (All instances)"
            name_lbl = ctk.CTkLabel(text_col, text=target_str, font=ctk.CTkFont(size=14, weight="bold"), anchor="w")
            name_lbl.pack(anchor="w")

            in_str = format_rate(rule.inbound_bps)
            out_str = format_rate(rule.outbound_bps)
            caps_lbl = ctk.CTkLabel(
                text_col,
                text=f"Download: {in_str}  |  Upload: {out_str}",
                font=ctk.CTkFont(size=12),
                text_color="#38bdf8",
                anchor="w",
            )
            caps_lbl.pack(anchor="w")

            right_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            right_frame.pack(side="right", padx=15, pady=8)

            del_btn = ctk.CTkButton(
                right_frame,
                text="Delete",
                width=65,
                height=28,
                fg_color="#8d261f",
                hover_color="#5e1914",
                command=lambda r=rule: self._delete_rule_direct(r),
            )
            del_btn.pack(side="right", padx=(8, 0))

            edit_btn = ctk.CTkButton(
                right_frame,
                text="Edit",
                width=65,
                height=28,
                fg_color="#374151",
                hover_color="#4b5563",
                command=lambda r=rule: self._open_rule_dialog(r.app_name, r.pid),
            )
            edit_btn.pack(side="right", padx=8)

            switch = ctk.CTkSwitch(
                right_frame,
                text="Enabled" if rule.enabled else "Disabled",
                command=lambda r=rule: self._toggle_rule_direct(r),
            )
            if rule.enabled:
                switch.select()
            else:
                switch.deselect()
            switch.pack(side="right", padx=8)

    def _delete_rule_direct(self, rule: LimitRule):
        self.rules.remove_rule(rule.app_name, rule.pid)
        self._update_rules_list()

    def _toggle_rule_direct(self, rule: LimitRule):
        self.rules.toggle_rule(rule.app_name, rule.pid)
        self._update_rules_list()

    def _open_rule_dialog(self, app_name: str, pid: Optional[int]):
        existing = self.rules.get_rule_for_process(app_name, pid or 0)
        RuleDialog(
            self,
            app_name=app_name,
            pid=pid,
            existing_rule=existing,
            on_save=self._on_rule_saved,
            on_delete=self._on_rule_deleted,
        )
