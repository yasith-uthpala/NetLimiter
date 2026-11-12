"""
RuleDialog: Modal dialog to configure incoming/outgoing bandwidth limits.
"""

from tkinter import filedialog
import customtkinter as ctk
from typing import Optional, Callable
from core.rules import LimitRule, format_rate, parse_rate_to_bps


class RuleDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        app_name: str,
        pid: Optional[int] = None,
        existing_rule: Optional[LimitRule] = None,
        on_save: Optional[Callable[[LimitRule], None]] = None,
        on_delete: Optional[Callable[[str, Optional[int]], None]] = None,
    ):
        super().__init__(parent)

        self.app_name = app_name.lower()
        self.pid = pid
        self.existing_rule = existing_rule
        self.on_save = on_save
        self.on_delete = on_delete

        self.title(f"Bandwidth Limit Rule — {self.app_name}")
        self.geometry("480x560")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._init_ui()

    def _init_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text=f"Rule Configuration: {self.app_name}",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title_lbl.pack(anchor="w")

        sub_text = f"Target PID: {self.pid}" if self.pid else "Target: All instances"
        sub_lbl = ctk.CTkLabel(header_frame, text=sub_text, font=ctk.CTkFont(size=12), text_color="gray")
        sub_lbl.pack(anchor="w")

        # Scope Selection
        scope_frame = ctk.CTkFrame(self)
        scope_frame.pack(fill="x", padx=20, pady=10)

        scope_lbl = ctk.CTkLabel(scope_frame, text="Scope:", font=ctk.CTkFont(size=13, weight="bold"))
        scope_lbl.pack(anchor="w", padx=15, pady=(10, 5))

        self.scope_var = ctk.StringVar(value="app" if not (self.existing_rule and self.existing_rule.pid) else "pid")
        self.radio_app = ctk.CTkRadioButton(
            scope_frame,
            text=f"All instances of {self.app_name}",
            variable=self.scope_var,
            value="app",
        )
        self.radio_app.pack(anchor="w", padx=15, pady=4)

        if self.pid:
            self.radio_pid = ctk.CTkRadioButton(
                scope_frame,
                text=f"Only this specific process (PID {self.pid})",
                variable=self.scope_var,
                value="pid",
            )
            self.radio_pid.pack(anchor="w", padx=15, pady=(4, 10))
        else:
            self.scope_var.set("app")

        # Inbound Limit (Download) Frame
        in_frame = ctk.CTkFrame(self)
        in_frame.pack(fill="x", padx=20, pady=10)

        self.in_enabled_var = ctk.BooleanVar(value=True if (self.existing_rule and self.existing_rule.inbound_bps > 0) else False)
        in_chk = ctk.CTkCheckBox(
            in_frame,
            text="Limit Download (Incoming)",
            variable=self.in_enabled_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._toggle_in_inputs,
        )
        in_chk.pack(anchor="w", padx=15, pady=(10, 8))

        in_input_frame = ctk.CTkFrame(in_frame, fg_color="transparent")
        in_input_frame.pack(fill="x", padx=15, pady=(0, 10))

        # Default values
        init_in_val = "1"
        init_in_unit = "MB/s"
        if self.existing_rule and self.existing_rule.inbound_bps > 0:
            bps = self.existing_rule.inbound_bps
            if bps >= 1024 * 1024:
                init_in_val = f"{bps / (1024 * 1024):g}"
                init_in_unit = "MB/s"
            else:
                init_in_val = f"{bps / 1024:g}"
                init_in_unit = "KB/s"

        self.in_entry = ctk.CTkEntry(in_input_frame, width=120)
        self.in_entry.insert(0, init_in_val)
        self.in_entry.pack(side="left", padx=(0, 10))

        self.in_unit_var = ctk.StringVar(value=init_in_unit)
        self.in_unit_menu = ctk.CTkOptionMenu(
            in_input_frame,
            values=["KB/s", "MB/s", "Mbps", "Kbps"],
            variable=self.in_unit_var,
            width=90,
        )
        self.in_unit_menu.pack(side="left")

        # Inbound Presets
        presets_in = ctk.CTkFrame(in_frame, fg_color="transparent")
        presets_in.pack(fill="x", padx=15, pady=(0, 10))
        for p_label, p_val, p_unit in [
            ("125 KB/s (1 Mbps)", "125", "KB/s"),
            ("250 KB/s (2 Mbps)", "250", "KB/s"),
            ("1 MB/s", "1", "MB/s"),
            ("5 MB/s", "5", "MB/s"),
        ]:
            btn = ctk.CTkButton(
                presets_in,
                text=p_label,
                height=24,
                font=ctk.CTkFont(size=11),
                fg_color="#333333",
                command=lambda v=p_val, u=p_unit: self._set_preset("in", v, u),
            )
            btn.pack(side="left", padx=3)

        # Outbound Limit (Upload) Frame
        out_frame = ctk.CTkFrame(self)
        out_frame.pack(fill="x", padx=20, pady=10)

        self.out_enabled_var = ctk.BooleanVar(value=True if (self.existing_rule and self.existing_rule.outbound_bps > 0) else False)
        out_chk = ctk.CTkCheckBox(
            out_frame,
            text="Limit Upload (Outgoing)",
            variable=self.out_enabled_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._toggle_out_inputs,
        )
        out_chk.pack(anchor="w", padx=15, pady=(10, 8))

        out_input_frame = ctk.CTkFrame(out_frame, fg_color="transparent")
        out_input_frame.pack(fill="x", padx=15, pady=(0, 10))

        init_out_val = "512"
        init_out_unit = "KB/s"
        if self.existing_rule and self.existing_rule.outbound_bps > 0:
            bps = self.existing_rule.outbound_bps
            if bps >= 1024 * 1024:
                init_out_val = f"{bps / (1024 * 1024):g}"
                init_out_unit = "MB/s"
            else:
                init_out_val = f"{bps / 1024:g}"
                init_out_unit = "KB/s"

        self.out_entry = ctk.CTkEntry(out_input_frame, width=120)
        self.out_entry.insert(0, init_out_val)
        self.out_entry.pack(side="left", padx=(0, 10))

        self.out_unit_var = ctk.StringVar(value=init_out_unit)
        self.out_unit_menu = ctk.CTkOptionMenu(
            out_input_frame,
            values=["KB/s", "MB/s", "Mbps", "Kbps"],
            variable=self.out_unit_var,
            width=90,
        )
        self.out_unit_menu.pack(side="left")

        # Outbound Presets
        presets_out = ctk.CTkFrame(out_frame, fg_color="transparent")
        presets_out.pack(fill="x", padx=15, pady=(0, 10))
        for p_label, p_val, p_unit in [
            ("64 KB/s", "64", "KB/s"),
            ("125 KB/s (1 Mbps)", "125", "KB/s"),
            ("512 KB/s", "512", "KB/s"),
            ("1 MB/s", "1", "MB/s"),
        ]:
            btn = ctk.CTkButton(
                presets_out,
                text=p_label,
                height=24,
                font=ctk.CTkFont(size=11),
                fg_color="#333333",
                command=lambda v=p_val, u=p_unit: self._set_preset("out", v, u),
            )
            btn.pack(side="left", padx=3)

        # Action Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(15, 20), side="bottom")

        save_btn = ctk.CTkButton(
            btn_frame,
            text="Apply Rule",
            fg_color="#1f538d",
            hover_color="#14375e",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._save_rule,
        )
        save_btn.pack(side="right", padx=(5, 0))

        if self.existing_rule:
            del_btn = ctk.CTkButton(
                btn_frame,
                text="Remove Rule",
                fg_color="#8d261f",
                hover_color="#5e1914",
                command=self._delete_rule,
            )
            del_btn.pack(side="right", padx=5)

        cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", fg_color="#3a3a3a", command=self.destroy)
        cancel_btn.pack(side="left")

        self._toggle_in_inputs()
        self._toggle_out_inputs()

    def _set_preset(self, direction: str, val: str, unit: str):
        if direction == "in":
            self.in_enabled_var.set(True)
            self._toggle_in_inputs()
            self.in_entry.delete(0, "end")
            self.in_entry.insert(0, val)
            self.in_unit_var.set(unit)
        else:
            self.out_enabled_var.set(True)
            self._toggle_out_inputs()
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, val)
            self.out_unit_var.set(unit)

    def _toggle_in_inputs(self):
        state = "normal" if self.in_enabled_var.get() else "disabled"
        self.in_entry.configure(state=state)
        self.in_unit_menu.configure(state=state)

    def _toggle_out_inputs(self):
        state = "normal" if self.out_enabled_var.get() else "disabled"
        self.out_entry.configure(state=state)
        self.out_unit_menu.configure(state=state)

    def _save_rule(self):
        in_bps = 0
        if self.in_enabled_var.get():
            try:
                val = float(self.in_entry.get())
                in_bps = parse_rate_to_bps(val, self.in_unit_var.get())
            except ValueError:
                in_bps = 0

        out_bps = 0
        if self.out_enabled_var.get():
            try:
                val = float(self.out_entry.get())
                out_bps = parse_rate_to_bps(val, self.out_unit_var.get())
            except ValueError:
                out_bps = 0

        rule_pid = self.pid if self.scope_var.get() == "pid" else None

        rule = LimitRule(
            app_name=self.app_name,
            pid=rule_pid,
            inbound_bps=in_bps,
            outbound_bps=out_bps,
            enabled=True,
        )

        if self.on_save:
            self.on_save(rule)

        self.destroy()

    def _delete_rule(self):
        rule_pid = self.pid if self.scope_var.get() == "pid" else None
        if self.on_delete:
            self.on_delete(self.app_name, rule_pid)
        self.destroy()


class AddManualRuleDialog(ctk.CTkToplevel):
    """Dialog allowing user to enter an app name manually or browse for an .exe file."""
    def __init__(self, parent, on_save: Callable[[LimitRule], None]):
        super().__init__(parent)
        self.on_save = on_save
        self.title("Add New Application Rule")
        self.geometry("480x580")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._init_ui()

    def _init_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="Add Custom Application Rule",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title_lbl.pack(anchor="w")

        sub_lbl = ctk.CTkLabel(
            header_frame,
            text="Set bandwidth limits for any application, even if not running yet.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        sub_lbl.pack(anchor="w")

        # App Name Entry & Browse
        app_frame = ctk.CTkFrame(self)
        app_frame.pack(fill="x", padx=20, pady=10)

        app_lbl = ctk.CTkLabel(app_frame, text="Executable Name (e.g. chrome.exe, steam.exe):", font=ctk.CTkFont(size=13, weight="bold"))
        app_lbl.pack(anchor="w", padx=15, pady=(10, 5))

        entry_row = ctk.CTkFrame(app_frame, fg_color="transparent")
        entry_row.pack(fill="x", padx=15, pady=(0, 10))

        self.app_entry = ctk.CTkEntry(entry_row, placeholder_text="e.g. torrent.exe")
        self.app_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        browse_btn = ctk.CTkButton(entry_row, text="Browse .exe", width=90, command=self._browse_exe)
        browse_btn.pack(side="right")

        # Inbound Limit (Download) Frame
        in_frame = ctk.CTkFrame(self)
        in_frame.pack(fill="x", padx=20, pady=10)

        self.in_enabled_var = ctk.BooleanVar(value=True)
        in_chk = ctk.CTkCheckBox(
            in_frame,
            text="Limit Download (Incoming)",
            variable=self.in_enabled_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._toggle_in_inputs,
        )
        in_chk.pack(anchor="w", padx=15, pady=(10, 8))

        in_input_frame = ctk.CTkFrame(in_frame, fg_color="transparent")
        in_input_frame.pack(fill="x", padx=15, pady=(0, 10))

        self.in_entry = ctk.CTkEntry(in_input_frame, width=120)
        self.in_entry.insert(0, "1")
        self.in_entry.pack(side="left", padx=(0, 10))

        self.in_unit_var = ctk.StringVar(value="KB/s")
        self.in_unit_menu = ctk.CTkOptionMenu(
            in_input_frame,
            values=["KB/s", "MB/s", "Mbps", "Kbps"],
            variable=self.in_unit_var,
            width=90,
        )
        self.in_unit_menu.pack(side="left")

        # Presets In
        presets_in = ctk.CTkFrame(in_frame, fg_color="transparent")
        presets_in.pack(fill="x", padx=15, pady=(0, 10))
        for p_label, p_val, p_unit in [
            ("125 KB/s (1 Mbps)", "125", "KB/s"),
            ("250 KB/s (2 Mbps)", "250", "KB/s"),
            ("1 MB/s", "1", "MB/s"),
            ("5 MB/s", "5", "MB/s"),
        ]:
            btn = ctk.CTkButton(
                presets_in,
                text=p_label,
                height=24,
                font=ctk.CTkFont(size=11),
                fg_color="#333333",
                command=lambda v=p_val, u=p_unit: self._set_preset("in", v, u),
            )
            btn.pack(side="left", padx=3)

        # Outbound Limit (Upload) Frame
        out_frame = ctk.CTkFrame(self)
        out_frame.pack(fill="x", padx=20, pady=10)

        self.out_enabled_var = ctk.BooleanVar(value=False)
        out_chk = ctk.CTkCheckBox(
            out_frame,
            text="Limit Upload (Outgoing)",
            variable=self.out_enabled_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._toggle_out_inputs,
        )
        out_chk.pack(anchor="w", padx=15, pady=(10, 8))

        out_input_frame = ctk.CTkFrame(out_frame, fg_color="transparent")
        out_input_frame.pack(fill="x", padx=15, pady=(0, 10))

        self.out_entry = ctk.CTkEntry(out_input_frame, width=120)
        self.out_entry.insert(0, "512")
        self.out_entry.pack(side="left", padx=(0, 10))

        self.out_unit_var = ctk.StringVar(value="KB/s")
        self.out_unit_menu = ctk.CTkOptionMenu(
            out_input_frame,
            values=["KB/s", "MB/s", "Mbps", "Kbps"],
            variable=self.out_unit_var,
            width=90,
        )
        self.out_unit_menu.pack(side="left")

        # Presets Out
        presets_out = ctk.CTkFrame(out_frame, fg_color="transparent")
        presets_out.pack(fill="x", padx=15, pady=(0, 10))
        for p_label, p_val, p_unit in [
            ("64 KB/s", "64", "KB/s"),
            ("125 KB/s (1 Mbps)", "125", "KB/s"),
            ("512 KB/s", "512", "KB/s"),
            ("1 MB/s", "1", "MB/s"),
        ]:
            btn = ctk.CTkButton(
                presets_out,
                text=p_label,
                height=24,
                font=ctk.CTkFont(size=11),
                fg_color="#333333",
                command=lambda v=p_val, u=p_unit: self._set_preset("out", v, u),
            )
            btn.pack(side="left", padx=3)

        # Action Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(15, 20), side="bottom")

        save_btn = ctk.CTkButton(
            btn_frame,
            text="Create Rule",
            fg_color="#1f538d",
            hover_color="#14375e",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._save_rule,
        )
        save_btn.pack(side="right", padx=(5, 0))

        cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", fg_color="#3a3a3a", command=self.destroy)
        cancel_btn.pack(side="left")

        self._toggle_in_inputs()
        self._toggle_out_inputs()

    def _browse_exe(self):
        filepath = filedialog.askopenfilename(
            title="Select Application Executable",
            filetypes=[("Executable Files", "*.exe"), ("All Files", "*.*")],
        )
        if filepath:
            import os
            basename = os.path.basename(filepath)
            self.app_entry.delete(0, "end")
            self.app_entry.insert(0, basename)

    def _set_preset(self, direction: str, val: str, unit: str):
        if direction == "in":
            self.in_enabled_var.set(True)
            self._toggle_in_inputs()
            self.in_entry.delete(0, "end")
            self.in_entry.insert(0, val)
            self.in_unit_var.set(unit)
        else:
            self.out_enabled_var.set(True)
            self._toggle_out_inputs()
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, val)
            self.out_unit_var.set(unit)

    def _toggle_in_inputs(self):
        state = "normal" if self.in_enabled_var.get() else "disabled"
        self.in_entry.configure(state=state)
        self.in_unit_menu.configure(state=state)

    def _toggle_out_inputs(self):
        state = "normal" if self.out_enabled_var.get() else "disabled"
        self.out_entry.configure(state=state)
        self.out_unit_menu.configure(state=state)

    def _save_rule(self):
        app_name = self.app_entry.get().strip().lower()
        if not app_name:
            return

        if not app_name.endswith(".exe"):
            app_name += ".exe"

        in_bps = 0
        if self.in_enabled_var.get():
            try:
                val = float(self.in_entry.get())
                in_bps = parse_rate_to_bps(val, self.in_unit_var.get())
            except ValueError:
                in_bps = 0

        out_bps = 0
        if self.out_enabled_var.get():
            try:
                val = float(self.out_entry.get())
                out_bps = parse_rate_to_bps(val, self.out_unit_var.get())
            except ValueError:
                out_bps = 0

        rule = LimitRule(
            app_name=app_name,
            pid=None,
            inbound_bps=in_bps,
            outbound_bps=out_bps,
            enabled=True,
        )

        if self.on_save:
            self.on_save(rule)

        self.destroy()


class MasterLimitDialog(ctk.CTkToplevel):
    """Dialog allowing user to configure system-wide Master Bandwidth Limits for the whole PC."""
    def __init__(
        self,
        parent,
        current_in_bps: int,
        current_out_bps: int,
        enabled: bool,
        on_save: Callable[[int, int, bool], None],
    ):
        super().__init__(parent)
        self.on_save = on_save
        self.title("Global PC Master Speed Limit")
        self.geometry("490x530")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.init_in_bps = current_in_bps
        self.init_out_bps = current_out_bps
        self.init_enabled = enabled

        self._init_ui()

    def _init_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="🌐 Master Speed Limit (Entire PC)",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#38bdf8",
        )
        title_lbl.pack(anchor="w")

        sub_lbl = ctk.CTkLabel(
            header_frame,
            text="Caps total internet bandwidth for all applications combined on this computer.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        sub_lbl.pack(anchor="w")

        # Inbound Limit (Download) Frame
        in_frame = ctk.CTkFrame(self)
        in_frame.pack(fill="x", padx=20, pady=10)

        self.in_enabled_var = ctk.BooleanVar(value=True if self.init_in_bps > 0 else True)
        in_chk = ctk.CTkCheckBox(
            in_frame,
            text="Cap Total PC Download Speed",
            variable=self.in_enabled_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._toggle_in_inputs,
        )
        in_chk.pack(anchor="w", padx=15, pady=(10, 8))

        in_input_frame = ctk.CTkFrame(in_frame, fg_color="transparent")
        in_input_frame.pack(fill="x", padx=15, pady=(0, 10))

        init_in_val = "5"
        init_in_unit = "MB/s"
        if self.init_in_bps > 0:
            bps = self.init_in_bps
            if bps >= 1024 * 1024:
                init_in_val = f"{bps / (1024 * 1024):g}"
                init_in_unit = "MB/s"
            else:
                init_in_val = f"{bps / 1024:g}"
                init_in_unit = "KB/s"

        self.in_entry = ctk.CTkEntry(in_input_frame, width=120)
        self.in_entry.insert(0, init_in_val)
        self.in_entry.pack(side="left", padx=(0, 10))

        self.in_unit_var = ctk.StringVar(value=init_in_unit)
        self.in_unit_menu = ctk.CTkOptionMenu(
            in_input_frame,
            values=["KB/s", "MB/s", "Mbps", "Kbps"],
            variable=self.in_unit_var,
            width=90,
        )
        self.in_unit_menu.pack(side="left")

        # Presets In
        presets_in = ctk.CTkFrame(in_frame, fg_color="transparent")
        presets_in.pack(fill="x", padx=15, pady=(0, 10))
        for p_label, p_val, p_unit in [
            ("1 MB/s", "1", "MB/s"),
            ("2 MB/s", "2", "MB/s"),
            ("5 MB/s", "5", "MB/s"),
            ("10 MB/s", "10", "MB/s"),
        ]:
            btn = ctk.CTkButton(
                presets_in,
                text=p_label,
                height=24,
                font=ctk.CTkFont(size=11),
                fg_color="#333333",
                command=lambda v=p_val, u=p_unit: self._set_preset("in", v, u),
            )
            btn.pack(side="left", padx=3)

        # Outbound Limit (Upload) Frame
        out_frame = ctk.CTkFrame(self)
        out_frame.pack(fill="x", padx=20, pady=10)

        self.out_enabled_var = ctk.BooleanVar(value=True if self.init_out_bps > 0 else False)
        out_chk = ctk.CTkCheckBox(
            out_frame,
            text="Cap Total PC Upload Speed",
            variable=self.out_enabled_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._toggle_out_inputs,
        )
        out_chk.pack(anchor="w", padx=15, pady=(10, 8))

        out_input_frame = ctk.CTkFrame(out_frame, fg_color="transparent")
        out_input_frame.pack(fill="x", padx=15, pady=(0, 10))

        init_out_val = "1"
        init_out_unit = "MB/s"
        if self.init_out_bps > 0:
            bps = self.init_out_bps
            if bps >= 1024 * 1024:
                init_out_val = f"{bps / (1024 * 1024):g}"
                init_out_unit = "MB/s"
            else:
                init_out_val = f"{bps / 1024:g}"
                init_out_unit = "KB/s"

        self.out_entry = ctk.CTkEntry(out_input_frame, width=120)
        self.out_entry.insert(0, init_out_val)
        self.out_entry.pack(side="left", padx=(0, 10))

        self.out_unit_var = ctk.StringVar(value=init_out_unit)
        self.out_unit_menu = ctk.CTkOptionMenu(
            out_input_frame,
            values=["KB/s", "MB/s", "Mbps", "Kbps"],
            variable=self.out_unit_var,
            width=90,
        )
        self.out_unit_menu.pack(side="left")

        # Presets Out
        presets_out = ctk.CTkFrame(out_frame, fg_color="transparent")
        presets_out.pack(fill="x", padx=15, pady=(0, 10))
        for p_label, p_val, p_unit in [
            ("256 KB/s", "256", "KB/s"),
            ("512 KB/s", "512", "KB/s"),
            ("1 MB/s", "1", "MB/s"),
            ("2 MB/s", "2", "MB/s"),
        ]:
            btn = ctk.CTkButton(
                presets_out,
                text=p_label,
                height=24,
                font=ctk.CTkFont(size=11),
                fg_color="#333333",
                command=lambda v=p_val, u=p_unit: self._set_preset("out", v, u),
            )
            btn.pack(side="left", padx=3)

        # Action Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(15, 20), side="bottom")

        save_btn = ctk.CTkButton(
            btn_frame,
            text="Apply Master Limit",
            fg_color="#0284c7",
            hover_color="#0369a1",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._save_master,
        )
        save_btn.pack(side="right", padx=(5, 0))

        if self.init_enabled:
            disable_btn = ctk.CTkButton(
                btn_frame,
                text="Turn Off Master Limit",
                fg_color="#8d261f",
                hover_color="#5e1914",
                command=self._disable_master,
            )
            disable_btn.pack(side="right", padx=5)

        cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", fg_color="#3a3a3a", command=self.destroy)
        cancel_btn.pack(side="left")

        self._toggle_in_inputs()
        self._toggle_out_inputs()

    def _set_preset(self, direction: str, val: str, unit: str):
        if direction == "in":
            self.in_enabled_var.set(True)
            self._toggle_in_inputs()
            self.in_entry.delete(0, "end")
            self.in_entry.insert(0, val)
            self.in_unit_var.set(unit)
        else:
            self.out_enabled_var.set(True)
            self._toggle_out_inputs()
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, val)
            self.out_unit_var.set(unit)

    def _toggle_in_inputs(self):
        state = "normal" if self.in_enabled_var.get() else "disabled"
        self.in_entry.configure(state=state)
        self.in_unit_menu.configure(state=state)

    def _toggle_out_inputs(self):
        state = "normal" if self.out_enabled_var.get() else "disabled"
        self.out_entry.configure(state=state)
        self.out_unit_menu.configure(state=state)

    def _save_master(self):
        in_bps = 0
        if self.in_enabled_var.get():
            try:
                val = float(self.in_entry.get())
                in_bps = parse_rate_to_bps(val, self.in_unit_var.get())
            except ValueError:
                in_bps = 0

        out_bps = 0
        if self.out_enabled_var.get():
            try:
                val = float(self.out_entry.get())
                out_bps = parse_rate_to_bps(val, self.out_unit_var.get())
            except ValueError:
                out_bps = 0

        if self.on_save:
            self.on_save(in_bps, out_bps, True)

        self.destroy()

    def _disable_master(self):
        if self.on_save:
            self.on_save(0, 0, False)
        self.destroy()
