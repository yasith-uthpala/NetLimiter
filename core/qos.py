"""
QoS: Native Windows Quality of Service Policy Controller.
Uses Windows NetQoS to enforce hardware-level bandwidth limits without third-party drivers.
"""

import subprocess
import logging

logger = logging.getLogger("NetLimiter.QoS")


class QosController:
    @staticmethod
    def _run_ps(cmd: str) -> bool:
        try:
            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return res.returncode == 0
        except Exception as e:
            logger.error(f"PowerShell error: {e}")
            return False

    @classmethod
    def set_master_throttle(cls, throttle_bytes_per_sec: int) -> bool:
        """
        Enforces a system-wide Master QoS throttle on all traffic leaving the PC.
        """
        policy_name = "NL_Master_Global"
        cls.remove_master_throttle()
        if throttle_bytes_per_sec <= 0:
            return True
        bits_per_sec = int(throttle_bytes_per_sec * 8)
        cmd = (
            f"New-NetQosPolicy -Name '{policy_name}' "
            f"-ThrottleRateActionBitsPerSecond {bits_per_sec} "
            f"-ErrorAction SilentlyContinue | Out-Null"
        )
        return cls._run_ps(cmd)

    @classmethod
    def remove_master_throttle(cls) -> bool:
        cmd = "Remove-NetQosPolicy -Name 'NL_Master_Global' -Confirm:$false -ErrorAction SilentlyContinue | Out-Null"
        return cls._run_ps(cmd)

    @classmethod
    def set_app_throttle(cls, app_name: str, throttle_bytes_per_sec: int) -> bool:
        """
        Enforces a native Windows QoS throttle rate on an application.
        :param app_name: e.g. "FortniteClient-Win64-Shipping.exe"
        :param throttle_bytes_per_sec: Rate in Bytes/sec (converted to Bits/sec for Windows QoS).
        """
        clean_name = app_name.strip()
        policy_name = f"NL_{clean_name.lower().replace('.', '_')}"

        # 1. Remove any existing policy
        cls.remove_app_throttle(clean_name)

        if throttle_bytes_per_sec <= 0:
            return True

        # Convert Bytes/sec to Bits/sec for NetQosPolicy (1 Byte = 8 Bits)
        bits_per_sec = int(throttle_bytes_per_sec * 8)

        cmd = (
            f"New-NetQosPolicy -Name '{policy_name}' "
            f"-AppPathNameMatchCondition '{clean_name}' "
            f"-ThrottleRateActionBitsPerSecond {bits_per_sec} "
            f"-ErrorAction SilentlyContinue | Out-Null"
        )
        return cls._run_ps(cmd)

    @classmethod
    def remove_app_throttle(cls, app_name: str) -> bool:
        clean_name = app_name.strip()
        policy_name = f"NL_{clean_name.lower().replace('.', '_')}"
        cmd = f"Remove-NetQosPolicy -Name '{policy_name}' -Confirm:$false -ErrorAction SilentlyContinue | Out-Null"
        return cls._run_ps(cmd)

    @classmethod
    def remove_all(cls) -> bool:
        cmd = "Get-NetQosPolicy -Name 'NL_*' -ErrorAction SilentlyContinue | Remove-NetQosPolicy -Confirm:$false -ErrorAction SilentlyContinue | Out-Null"
        return cls._run_ps(cmd)
