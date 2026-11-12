"""
FlowTracker: Lightweight, high-efficiency socket-to-process resolver.
Uses Windows IP Helper API (iphlpapi.dll) with in-memory caching for near-zero CPU usage.
"""

import ctypes
from ctypes import wintypes
import socket
import threading
import time
from typing import Dict, Tuple, Optional, List, Any
import psutil

# Windows Constants
AF_INET = 2
AF_INET6 = 23
TCP_TABLE_OWNER_PID_ALL = 5
UDP_TABLE_OWNER_PID = 1

iphlpapi = ctypes.WinDLL("iphlpapi.dll")


class MIB_TCPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwRemoteAddr", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class MIB_UDPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class IN6_ADDR(ctypes.Structure):
    _fields_ = [("Byte", ctypes.c_ubyte * 16)]


class MIB_TCP6ROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("ucLocalAddr", IN6_ADDR),
        ("dwLocalScopeId", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("ucRemoteAddr", IN6_ADDR),
        ("dwRemoteScopeId", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwState", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class MIB_UDP6ROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("ucLocalAddr", IN6_ADDR),
        ("dwLocalScopeId", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


def _format_ipv4(addr_dword: int) -> str:
    try:
        return socket.inet_ntoa(addr_dword.to_bytes(4, "little"))
    except Exception:
        return "0.0.0.0"


def _format_ipv6(in6_bytes) -> str:
    try:
        return socket.inet_ntop(socket.AF_INET6, bytes(in6_bytes))
    except Exception:
        return "::"


class FlowTracker:
    def __init__(self, refresh_interval: float = 1.0):
        self.refresh_interval = max(0.5, refresh_interval)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Fast lookups:
        # (protocol, local_port) -> (pid, process_name)
        self._port_map: Dict[Tuple[str, int], Tuple[int, str]] = {}
        # (protocol, local_ip, local_port, remote_ip, remote_port) -> (pid, process_name)
        self._exact_map: Dict[Tuple[str, str, int, str, int], Tuple[int, str]] = {}
        # pid -> {"name": str, "exe": str, "active_sockets": int, "last_seen": float}
        self._process_cache: Dict[int, Dict[str, Any]] = {}
        self._last_cache_cleanup = time.time()

    def start(self):
        if self._running:
            return
        self._running = True
        try:
            self._update_tables()
        except Exception:
            pass
        self._thread = threading.Thread(target=self._run_loop, name="FlowTrackerWorker", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run_loop(self):
        while self._running:
            try:
                self._update_tables()
            except Exception:
                pass
            time.sleep(self.refresh_interval)

    def _get_process_name(self, pid: int) -> Tuple[str, str]:
        """Resolves PID to (process_name, exe_path) with long-term caching for zero CPU waste."""
        if pid == 0:
            return "System Idle", ""
        if pid == 4:
            return "System", "ntoskrnl.exe"

        cached = self._process_cache.get(pid)
        now = time.time()
        # Cache valid for 60 seconds
        if cached and (now - cached.get("last_checked", 0) < 60.0):
            cached["last_seen"] = now
            return cached["name"], cached["exe"]

        name = f"PID_{pid}"
        exe = ""
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            try:
                exe = proc.exe()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                exe = ""
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            if cached:
                return cached["name"], cached["exe"]

        self._process_cache[pid] = {
            "name": name,
            "exe": exe,
            "last_checked": now,
            "last_seen": now,
            "active_sockets": 0,
        }
        return name, exe

    def _query_tcp4(self) -> List[Tuple[str, str, int, str, int, int]]:
        results = []
        size = wintypes.DWORD(0)
        iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), True, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
        if size.value == 0:
            return results
        buf = (ctypes.c_byte * size.value)()
        if iphlpapi.GetExtendedTcpTable(ctypes.byref(buf), ctypes.byref(size), True, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0) != 0:
            return results

        b_data = bytes(buf)
        num_entries = int.from_bytes(b_data[:4], "little")
        row_size = ctypes.sizeof(MIB_TCPROW_OWNER_PID)
        for i in range(num_entries):
            offset = 4 + i * row_size
            row = MIB_TCPROW_OWNER_PID.from_buffer_copy(b_data[offset : offset + row_size])
            lport = socket.ntohs(row.dwLocalPort & 0xFFFF)
            rport = socket.ntohs(row.dwRemotePort & 0xFFFF)
            laddr = _format_ipv4(row.dwLocalAddr)
            raddr = _format_ipv4(row.dwRemoteAddr)
            results.append(("tcp", laddr, lport, raddr, rport, row.dwOwningPid))
        return results

    def _query_udp4(self) -> List[Tuple[str, str, int, str, int, int]]:
        results = []
        size = wintypes.DWORD(0)
        iphlpapi.GetExtendedUdpTable(None, ctypes.byref(size), True, AF_INET, UDP_TABLE_OWNER_PID, 0)
        if size.value == 0:
            return results
        buf = (ctypes.c_byte * size.value)()
        if iphlpapi.GetExtendedUdpTable(ctypes.byref(buf), ctypes.byref(size), True, AF_INET, UDP_TABLE_OWNER_PID, 0) != 0:
            return results

        b_data = bytes(buf)
        num_entries = int.from_bytes(b_data[:4], "little")
        row_size = ctypes.sizeof(MIB_UDPROW_OWNER_PID)
        for i in range(num_entries):
            offset = 4 + i * row_size
            row = MIB_UDPROW_OWNER_PID.from_buffer_copy(b_data[offset : offset + row_size])
            lport = socket.ntohs(row.dwLocalPort & 0xFFFF)
            laddr = _format_ipv4(row.dwLocalAddr)
            results.append(("udp", laddr, lport, "0.0.0.0", 0, row.dwOwningPid))
        return results

    def _query_tcp6(self) -> List[Tuple[str, str, int, str, int, int]]:
        results = []
        size = wintypes.DWORD(0)
        iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), True, AF_INET6, TCP_TABLE_OWNER_PID_ALL, 0)
        if size.value == 0:
            return results
        buf = (ctypes.c_byte * size.value)()
        if iphlpapi.GetExtendedTcpTable(ctypes.byref(buf), ctypes.byref(size), True, AF_INET6, TCP_TABLE_OWNER_PID_ALL, 0) != 0:
            return results

        b_data = bytes(buf)
        num_entries = int.from_bytes(b_data[:4], "little")
        row_size = ctypes.sizeof(MIB_TCP6ROW_OWNER_PID)
        for i in range(num_entries):
            offset = 4 + i * row_size
            row = MIB_TCP6ROW_OWNER_PID.from_buffer_copy(b_data[offset : offset + row_size])
            lport = socket.ntohs(row.dwLocalPort & 0xFFFF)
            rport = socket.ntohs(row.dwRemotePort & 0xFFFF)
            laddr = _format_ipv6(row.ucLocalAddr.Byte)
            raddr = _format_ipv6(row.ucRemoteAddr.Byte)
            results.append(("tcp", laddr, lport, raddr, rport, row.dwOwningPid))
        return results

    def _query_udp6(self) -> List[Tuple[str, str, int, str, int, int]]:
        results = []
        size = wintypes.DWORD(0)
        iphlpapi.GetExtendedUdpTable(None, ctypes.byref(size), True, AF_INET6, UDP_TABLE_OWNER_PID, 0)
        if size.value == 0:
            return results
        buf = (ctypes.c_byte * size.value)()
        if iphlpapi.GetExtendedUdpTable(ctypes.byref(buf), ctypes.byref(size), True, AF_INET6, UDP_TABLE_OWNER_PID, 0) != 0:
            return results

        b_data = bytes(buf)
        num_entries = int.from_bytes(b_data[:4], "little")
        row_size = ctypes.sizeof(MIB_UDP6ROW_OWNER_PID)
        for i in range(num_entries):
            offset = 4 + i * row_size
            row = MIB_UDP6ROW_OWNER_PID.from_buffer_copy(b_data[offset : offset + row_size])
            lport = socket.ntohs(row.dwLocalPort & 0xFFFF)
            laddr = _format_ipv6(row.ucLocalAddr.Byte)
            results.append(("udp", laddr, lport, "::", 0, row.dwOwningPid))
        return results

    def _update_tables(self):
        new_port_map: Dict[Tuple[str, int], Tuple[int, str]] = {}
        new_exact_map: Dict[Tuple[str, str, int, str, int], Tuple[int, str]] = {}
        pid_socket_counts: Dict[int, int] = {}

        all_conns = []
        try:
            all_conns.extend(self._query_tcp4())
            all_conns.extend(self._query_udp4())
            all_conns.extend(self._query_tcp6())
            all_conns.extend(self._query_udp6())
        except Exception:
            return

        for proto, laddr, lport, raddr, rport, pid in all_conns:
            pname, exe = self._get_process_name(pid)
            new_port_map[(proto, lport)] = (pid, pname)
            if rport > 0:
                new_exact_map[(proto, laddr, lport, raddr, rport)] = (pid, pname)
            pid_socket_counts[pid] = pid_socket_counts.get(pid, 0) + 1

        with self._lock:
            self._port_map = new_port_map
            self._exact_map = new_exact_map

            # Reset counts and apply new counts
            for info in self._process_cache.values():
                info["active_sockets"] = 0
            for pid, count in pid_socket_counts.items():
                if pid in self._process_cache:
                    self._process_cache[pid]["active_sockets"] = count

            # Clean cache every 30 seconds
            now = time.time()
            if now - self._last_cache_cleanup > 30.0:
                self._last_cache_cleanup = now
                dead_pids = [
                    pid for pid, inf in self._process_cache.items()
                    if (now - inf.get("last_seen", 0) > 45.0) and inf.get("active_sockets", 0) == 0
                ]
                for p in dead_pids:
                    del self._process_cache[p]

    def get_process_for_packet(
        self,
        is_inbound: bool,
        protocol: str,
        src_ip: str,
        src_port: int,
        dst_ip: str,
        dst_port: int,
    ) -> Tuple[int, str]:
        proto = protocol.lower()
        if is_inbound:
            local_ip, local_port = dst_ip, dst_port
            remote_ip, remote_port = src_ip, src_port
        else:
            local_ip, local_port = src_ip, src_port
            remote_ip, remote_port = dst_ip, dst_port

        with self._lock:
            exact_key = (proto, local_ip, local_port, remote_ip, remote_port)
            if exact_key in self._exact_map:
                return self._exact_map[exact_key]

            port_key = (proto, local_port)
            if port_key in self._port_map:
                return self._port_map[port_key]

        return 0, "Unknown"

    def get_active_processes(self) -> List[Dict[str, Any]]:
        active_list = []
        with self._lock:
            for pid, info in list(self._process_cache.items()):
                if info.get("active_sockets", 0) > 0:
                    active_list.append({
                        "pid": pid,
                        "name": info.get("name", f"PID_{pid}"),
                        "exe": info.get("exe", ""),
                        "active_sockets": info.get("active_sockets", 0),
                    })

        active_list.sort(key=lambda x: (x["name"].lower(), x["pid"]))
        return active_list

    def get_grouped_processes(self) -> List[Dict[str, Any]]:
        flat_list = self.get_active_processes()
        groups: Dict[str, Dict[str, Any]] = {}

        for p in flat_list:
            app_name = p["name"].lower()
            if app_name not in groups:
                groups[app_name] = {
                    "name": p["name"],
                    "exe": p["exe"],
                    "total_sockets": 0,
                    "pids": [],
                }
            groups[app_name]["total_sockets"] += p["active_sockets"]
            groups[app_name]["pids"].append({
                "pid": p["pid"],
                "active_sockets": p["active_sockets"],
            })
            if not groups[app_name]["exe"] and p["exe"]:
                groups[app_name]["exe"] = p["exe"]

        return list(groups.values())
