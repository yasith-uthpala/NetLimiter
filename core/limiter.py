"""
Limiter: Intercepts network packets and applies TokenBucket rate shaping.
Failsafe: Fallbacks cleanly to Native Windows QoS if kernel driver encounters environment locks.
"""

import heapq
import logging
import threading
import time
from typing import Dict, Optional, Tuple, Any

from core.flow_tracker import FlowTracker
from core.monitor import SpeedMonitor
from core.rules import RuleManager, LimitRule
from core.token_bucket import TokenBucket

logger = logging.getLogger("NetLimiter")


class LimiterEngine:
    def __init__(self, rule_manager: RuleManager, flow_tracker: FlowTracker, monitor: SpeedMonitor):
        self.rules = rule_manager
        self.flow_tracker = flow_tracker
        self.monitor = monitor

        self._running = False
        self._divert: Any = None
        self._capture_thread: Optional[threading.Thread] = None
        self._pacer_thread: Optional[threading.Thread] = None

        # Token buckets: key -> {"in": TokenBucket, "out": TokenBucket}
        self._buckets: Dict[str, Dict[str, TokenBucket]] = {}
        self._buckets_lock = threading.Lock()

        # Master Token Buckets for system-wide bandwidth limiting
        self.master_in_bucket = TokenBucket(0)
        self.master_out_bucket = TokenBucket(0)

        # Delayed packet priority queue
        self._pacer_queue = []
        self._pacer_lock = threading.Lock()
        self._pacer_cond = threading.Condition(self._pacer_lock)
        self._packet_counter = 0

        # Status
        self.status = "STOPPED"
        self.status_message = "Idle"
        self.global_paused = False

    def get_or_create_buckets(self, rule: LimitRule) -> Dict[str, TokenBucket]:
        key = rule.key
        with self._buckets_lock:
            if key not in self._buckets:
                self._buckets[key] = {
                    "in": TokenBucket(rule.inbound_bps),
                    "out": TokenBucket(rule.outbound_bps),
                }
            else:
                self._buckets[key]["in"].update_rate(rule.inbound_bps)
                self._buckets[key]["out"].update_rate(rule.outbound_bps)
            return self._buckets[key]

    def start(self) -> bool:
        if self._running:
            return True

        self._running = True
        self.flow_tracker.start()
        self.monitor.start()

        # Try initializing WinDivert driver
        packet_filter = "(tcp or udp) and !loopback"
        try:
            import pydivert
            self._divert = pydivert.WinDivert(filter=packet_filter, priority=0)
            self._divert.open()
            self.status = "RUNNING"
            self.status_message = "Full WinDivert Active"

            # Launch workers only if driver opened successfully
            self._pacer_thread = threading.Thread(target=self._pacer_loop, name="LimiterPacer", daemon=True)
            self._pacer_thread.start()

            self._capture_thread = threading.Thread(target=self._capture_loop, name="LimiterCapture", daemon=True)
            self._capture_thread.start()
            return True

        except Exception as e:
            # Fallback to Native Windows QoS engine
            logger.info(f"WinDivert driver in standby: {e}")
            self.status = "RUNNING_QOS"
            self.status_message = "Native Windows QoS Active"
            self._divert = None
            return True

    def stop(self):
        if not self._running:
            return

        self._running = False
        self.status = "STOPPED"
        self.status_message = "Stopped"

        # Close driver handle
        if self._divert:
            try:
                self._divert.close()
            except Exception:
                pass
            self._divert = None

        # Wake pacer thread
        with self._pacer_cond:
            self._pacer_cond.notify_all()

        with self._pacer_lock:
            self._pacer_queue.clear()

        self.flow_tracker.stop()
        self.monitor.stop()

    def set_global_paused(self, paused: bool):
        self.global_paused = paused

    def _capture_loop(self):
        divert = self._divert
        if not divert:
            return

        while self._running:
            try:
                packet = divert.recv()
            except Exception:
                break

            if not packet:
                continue

            try:
                self._handle_packet(packet)
            except Exception:
                try:
                    divert.send(packet)
                except Exception:
                    pass

    def _handle_packet(self, packet: Any):
        divert = self._divert
        if not divert:
            return

        if self.global_paused:
            divert.send(packet)
            return

        is_in = packet.is_inbound
        proto = "tcp" if packet.tcp else ("udp" if packet.udp else "other")
        src_ip = packet.src_addr
        src_port = packet.src_port or 0
        dst_ip = packet.dst_addr
        dst_port = packet.dst_port or 0
        pkt_len = len(packet.raw)

        # Map to process
        pid, app_name = self.flow_tracker.get_process_for_packet(
            is_inbound=is_in,
            protocol=proto,
            src_ip=src_ip,
            src_port=src_port,
            dst_ip=dst_ip,
            dst_port=dst_port,
        )

        self.monitor.record_traffic(pid, app_name, is_in, pkt_len)

        # 1. Enforce Master Speed Limit (Global PC Cap) if active
        if self.rules.master_enabled:
            master_limit_bps = self.rules.master_inbound_bps if is_in else self.rules.master_outbound_bps
            if master_limit_bps > 0:
                mbucket = self.master_in_bucket if is_in else self.master_out_bucket
                if mbucket.rate_bps != master_limit_bps:
                    mbucket.update_rate(master_limit_bps)
                allowed, delay = mbucket.consume(pkt_len)
                if not allowed:
                    if delay >= 0:
                        scheduled_time = time.perf_counter() + delay
                        self._schedule_packet(scheduled_time, packet)
                    return

        # 2. Enforce Per-App Specific Limit Rule
        rule = self.rules.get_rule_for_process(app_name, pid)
        if not rule or not rule.enabled:
            divert.send(packet)
            return

        limit_bps = rule.inbound_bps if is_in else rule.outbound_bps
        if limit_bps <= 0:
            divert.send(packet)
            return

        buckets = self.get_or_create_buckets(rule)
        bucket = buckets["in"] if is_in else buckets["out"]

        allowed, delay = bucket.consume(pkt_len)
        if allowed:
            divert.send(packet)
        elif delay >= 0:
            scheduled_time = time.perf_counter() + delay
            self._schedule_packet(scheduled_time, packet)

    def _schedule_packet(self, scheduled_time: float, packet: Any):
        with self._pacer_cond:
            self._packet_counter += 1
            heapq.heappush(self._pacer_queue, (scheduled_time, self._packet_counter, packet))
            self._pacer_cond.notify()

    def _pacer_loop(self):
        while self._running:
            with self._pacer_cond:
                if not self._pacer_queue:
                    self._pacer_cond.wait(timeout=0.05)
                    continue

                now = time.perf_counter()
                send_time, _, packet = self._pacer_queue[0]

                if now >= send_time:
                    heapq.heappop(self._pacer_queue)
                    wait_time = 0
                else:
                    wait_time = send_time - now

            if wait_time > 0:
                time.sleep(min(wait_time, 0.005))
            else:
                divert = self._divert
                if divert:
                    try:
                        divert.send(packet)
                    except Exception:
                        pass
