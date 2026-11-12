"""
Monitor: Lightweight real-time network speed calculator with history buffers.
"""

import time
import threading
from typing import Dict, Tuple, Optional


class SpeedMonitor:
    def __init__(self, window_size: float = 1.0):
        self.window_size = max(0.5, window_size)
        self._lock = threading.Lock()

        # Temporary byte accumulators
        self._accum: Dict[int, Dict[str, Any]] = {}
        # Computed rates in bytes/sec
        self._rates: Dict[int, Dict[str, float]] = {}
        self._name_rates: Dict[str, Dict[str, float]] = {}

        # System totals
        self._total_accum = {"in": 0, "out": 0}
        self._total_rates = {"in_rate": 0.0, "out_rate": 0.0}

        # 30-sample history for sparkline graph
        self.history_len = 30
        self.in_history = [0.0] * self.history_len
        self.out_history = [0.0] * self.history_len

        self.last_tick = time.time()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._tick_loop, name="SpeedMonitorWorker", daemon=True)
        self._worker_thread.start()

    def stop(self):
        self._running = False

    def record_traffic(self, pid: int, app_name: str, is_inbound: bool, num_bytes: int):
        direction = "in" if is_inbound else "out"
        with self._lock:
            if pid not in self._accum:
                self._accum[pid] = {"in": 0, "out": 0, "name": app_name.lower()}
            self._accum[pid][direction] += num_bytes
            self._total_accum[direction] += num_bytes

    def _tick_loop(self):
        while self._running:
            time.sleep(self.window_size)
            try:
                self._compute_rates()
            except Exception:
                pass

    def _compute_rates(self):
        now = time.time()
        with self._lock:
            elapsed = max(0.001, now - self.last_tick)
            self.last_tick = now

            self._total_rates["in_rate"] = self._total_accum["in"] / elapsed
            self._total_rates["out_rate"] = self._total_accum["out"] / elapsed
            self._total_accum = {"in": 0, "out": 0}

            self.in_history.append(self._total_rates["in_rate"])
            if len(self.in_history) > self.history_len:
                self.in_history.pop(0)

            self.out_history.append(self._total_rates["out_rate"])
            if len(self.out_history) > self.history_len:
                self.out_history.pop(0)

            new_rates: Dict[int, Dict[str, float]] = {}
            new_name_rates: Dict[str, Dict[str, float]] = {}

            for pid, data in list(self._accum.items()):
                in_rate = data["in"] / elapsed
                out_rate = data["out"] / elapsed
                name = data.get("name", "")

                new_rates[pid] = {"in_rate": in_rate, "out_rate": out_rate}

                if name:
                    if name not in new_name_rates:
                        new_name_rates[name] = {"in_rate": 0.0, "out_rate": 0.0}
                    new_name_rates[name]["in_rate"] += in_rate
                    new_name_rates[name]["out_rate"] += out_rate

                # Reset accumulator
                data["in"] = 0
                data["out"] = 0

            self._rates = new_rates
            self._name_rates = new_name_rates

    def get_process_speed(self, pid: int) -> Tuple[float, float]:
        with self._lock:
            r = self._rates.get(pid)
            if r:
                return r["in_rate"], r["out_rate"]
        return 0.0, 0.0

    def get_app_speed(self, app_name: str) -> Tuple[float, float]:
        with self._lock:
            r = self._name_rates.get(app_name.lower())
            if r:
                return r["in_rate"], r["out_rate"]
        return 0.0, 0.0

    def get_total_speed(self) -> Tuple[float, float]:
        with self._lock:
            return self._total_rates["in_rate"], self._total_rates["out_rate"]

    def get_history(self) -> Tuple[list, list]:
        with self._lock:
            return list(self.in_history), list(self.out_history)
