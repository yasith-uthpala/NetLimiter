"""
Rule Manager: Stores, applies, and persists bandwidth limitation rules.
"""

from dataclasses import dataclass, asdict
import json
import os
import threading
from typing import Dict, List, Optional, Tuple
from core.qos import QosController

RULES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules.json")


def format_rate(bytes_per_sec: int) -> str:
    """Formats bytes/sec to human-readable string."""
    if bytes_per_sec <= 0:
        return "Unlimited"
    if bytes_per_sec >= 1024 * 1024:
        return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"
    if bytes_per_sec >= 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    return f"{bytes_per_sec} B/s"


def parse_rate_to_bps(val: float, unit: str) -> int:
    """
    Converts a value and unit ('B/s', 'KB/s', 'MB/s', 'Kbps', 'Mbps') to bytes/sec.
    Note: 1 Mbps = 1,000,000 bits/sec / 8 = 125,000 B/s (~125 KB/s).
    """
    unit_clean = unit.strip()
    if unit_clean == "Mbps":
        return int(val * 1_000_000 / 8)
    elif unit_clean == "Kbps":
        return int(val * 1_000 / 8)

    unit_upper = unit_clean.upper()
    if unit_upper.startswith("MB"):
        return int(val * 1024 * 1024)
    elif unit_upper.startswith("KB"):
        return int(val * 1024)
    elif unit_upper.startswith("B"):
        return int(val)
    return int(val)


@dataclass
class LimitRule:
    app_name: str  # Lowercase executable name (e.g. "chrome.exe")
    pid: Optional[int] = None  # Specific PID or None for all instances
    inbound_bps: int = 0  # 0 = unlimited
    outbound_bps: int = 0  # 0 = unlimited
    enabled: bool = True

    @property
    def key(self) -> str:
        """Unique key for dictionary lookup."""
        if self.pid is not None:
            return f"pid:{self.pid}"
        return f"app:{self.app_name.lower()}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LimitRule":
        return cls(
            app_name=data.get("app_name", "").lower(),
            pid=data.get("pid"),
            inbound_bps=int(data.get("inbound_bps", 0)),
            outbound_bps=int(data.get("outbound_bps", 0)),
            enabled=bool(data.get("enabled", True)),
        )


class RuleManager:
    def __init__(self, filepath: str = RULES_FILE):
        self.filepath = filepath
        self._lock = threading.Lock()
        self._rules: Dict[str, LimitRule] = {}

        # Master Limit settings (System-wide PC bandwidth cap)
        self.master_enabled: bool = False
        self.master_inbound_bps: int = 0
        self.master_outbound_bps: int = 0

        self.load()

    def set_master_limit(self, inbound_bps: int, outbound_bps: int, enabled: bool = True):
        with self._lock:
            self.master_inbound_bps = max(0, inbound_bps)
            self.master_outbound_bps = max(0, outbound_bps)
            self.master_enabled = enabled
        self.save()

        # Sync with Windows QoS
        if self.master_enabled:
            rate = self.master_outbound_bps or self.master_inbound_bps
            if rate > 0:
                QosController.set_master_throttle(rate)
        else:
            QosController.remove_master_throttle()

    def toggle_master_limit(self) -> bool:
        with self._lock:
            self.master_enabled = not self.master_enabled
            state = self.master_enabled
        self.save()
        if state:
            rate = self.master_outbound_bps or self.master_inbound_bps
            if rate > 0:
                QosController.set_master_throttle(rate)
        else:
            QosController.remove_master_throttle()
        return state

    def get_master_limit(self) -> Tuple[bool, int, int]:
        with self._lock:
            return self.master_enabled, self.master_inbound_bps, self.master_outbound_bps

    def load(self):
        with self._lock:
            self._rules.clear()
            if not os.path.exists(self.filepath):
                return
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                    if isinstance(data, dict):
                        # New structure with master_limit
                        m = data.get("master_limit", {})
                        self.master_enabled = bool(m.get("enabled", False))
                        self.master_inbound_bps = int(m.get("inbound_bps", 0))
                        self.master_outbound_bps = int(m.get("outbound_bps", 0))

                        rules_list = data.get("rules", [])
                        for item in rules_list:
                            rule = LimitRule.from_dict(item)
                            self._rules[rule.key] = rule
                    elif isinstance(data, list):
                        # Legacy list structure
                        for item in data:
                            rule = LimitRule.from_dict(item)
                            self._rules[rule.key] = rule
            except Exception as e:
                print(f"[RuleManager] Error loading rules: {e}")

        # Sync active rules with Windows QoS
        for rule in list(self._rules.values()):
            if rule.enabled and not rule.pid:
                rate = rule.outbound_bps if rule.outbound_bps > 0 else rule.inbound_bps
                if rate > 0:
                    QosController.set_app_throttle(rule.app_name, rate)

        if self.master_enabled:
            rate = self.master_outbound_bps or self.master_inbound_bps
            if rate > 0:
                QosController.set_master_throttle(rate)

    def save(self):
        with self._lock:
            try:
                data = {
                    "master_limit": {
                        "enabled": self.master_enabled,
                        "inbound_bps": self.master_inbound_bps,
                        "outbound_bps": self.master_outbound_bps,
                    },
                    "rules": [rule.to_dict() for rule in self._rules.values()],
                }
                with open(self.filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"[RuleManager] Error saving rules: {e}")

    def set_rule(self, app_name: str, pid: Optional[int], inbound_bps: int, outbound_bps: int, enabled: bool = True) -> LimitRule:
        rule = LimitRule(
            app_name=app_name.lower(),
            pid=pid,
            inbound_bps=max(0, inbound_bps),
            outbound_bps=max(0, outbound_bps),
            enabled=enabled,
        )
        with self._lock:
            self._rules[rule.key] = rule
        self.save()

        # Apply Native Windows QoS policy as kernel-level throttle
        if enabled:
            # Throttle limit in bytes per second (using outbound or inbound limit)
            throttle_rate = rule.outbound_bps if rule.outbound_bps > 0 else rule.inbound_bps
            if throttle_rate > 0:
                QosController.set_app_throttle(rule.app_name, throttle_rate)
        else:
            QosController.remove_app_throttle(rule.app_name)

        return rule

    def remove_rule(self, app_name: str, pid: Optional[int] = None):
        key = f"pid:{pid}" if pid is not None else f"app:{app_name.lower()}"
        with self._lock:
            if key in self._rules:
                del self._rules[key]
        self.save()
        QosController.remove_app_throttle(app_name)

    def toggle_rule(self, app_name: str, pid: Optional[int] = None) -> Optional[bool]:
        key = f"pid:{pid}" if pid is not None else f"app:{app_name.lower()}"
        with self._lock:
            if key in self._rules:
                self._rules[key].enabled = not self._rules[key].enabled
                state = self._rules[key].enabled
                self.save()
                if state:
                    throttle_rate = self._rules[key].outbound_bps or self._rules[key].inbound_bps
                    if throttle_rate > 0:
                        QosController.set_app_throttle(app_name, throttle_rate)
                else:
                    QosController.remove_app_throttle(app_name)
                return state
        return None

    def get_all_rules(self) -> List[LimitRule]:
        with self._lock:
            return list(self._rules.values())

    def get_rule_for_process(self, app_name: str, pid: int) -> Optional[LimitRule]:
        """
        Looks up an active rule. PID-specific rules take precedence over general app rules.
        """
        app_name = app_name.lower()
        with self._lock:
            # 1. Check PID specific
            pid_key = f"pid:{pid}"
            if pid_key in self._rules:
                r = self._rules[pid_key]
                if r.enabled:
                    return r

            # 2. Check App name
            app_key = f"app:{app_name}"
            if app_key in self._rules:
                r = self._rules[app_key]
                if r.enabled:
                    return r

        return None
