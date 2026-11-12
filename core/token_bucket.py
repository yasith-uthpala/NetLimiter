"""
TokenBucket: High-precision token bucket rate limiter for packet shaping.
"""

import time
import threading
from typing import Tuple


class TokenBucket:
    def __init__(self, rate_bps: int, burst_size: int = 0):
        """
        :param rate_bps: Rate limit in bytes per second. (0 = unlimited)
        :param burst_size: Maximum tokens that can accumulate.
        """
        self.rate_bps = max(0, rate_bps)
        # Default burst size: 1.5 seconds worth of tokens, minimum 64 KB, max 5 MB
        if burst_size > 0:
            self.capacity = burst_size
        else:
            self.capacity = max(64 * 1024, min(int(self.rate_bps * 1.5), 5 * 1024 * 1024)) if self.rate_bps > 0 else 64 * 1024

        self.tokens = float(self.capacity)
        self.last_update = time.perf_counter()
        self._lock = threading.Lock()

    def update_rate(self, new_rate_bps: int):
        with self._lock:
            self._refill()
            self.rate_bps = max(0, new_rate_bps)
            if self.rate_bps > 0:
                self.capacity = max(64 * 1024, min(int(self.rate_bps * 1.5), 5 * 1024 * 1024))
            self.tokens = min(self.tokens, float(self.capacity))

    def _refill(self):
        now = time.perf_counter()
        elapsed = now - self.last_update
        self.last_update = now
        if self.rate_bps > 0:
            self.tokens = min(float(self.capacity), self.tokens + elapsed * self.rate_bps)

    def consume(self, packet_bytes: int) -> Tuple[bool, float]:
        """
        Consumes tokens for a packet.
        Returns:
            (allow_immediate: bool, delay_seconds: float)
            If delay_seconds < 0, packet should be dropped (buffer overrun).
        """
        if self.rate_bps <= 0:
            return True, 0.0

        with self._lock:
            self._refill()

            if self.tokens >= packet_bytes:
                self.tokens -= packet_bytes
                return True, 0.0

            # Calculate required delay
            needed = packet_bytes - self.tokens
            delay = needed / self.rate_bps

            # Max delay tolerance before dropping (avoid extreme queue buildup)
            if delay > 2.5:
                return False, -1.0  # Drop packet

            # Reserve tokens for scheduled transmission
            self.tokens -= packet_bytes
            return False, delay
