"""
NetLimiter Main Entrypoint.
Checks for Administrator elevation, initializes engine, and launches GUI.
Completely terminates all background workers and processes upon closing.
"""

import sys
import os
import ctypes

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.rules import RuleManager
from core.flow_tracker import FlowTracker
from core.monitor import SpeedMonitor
from core.limiter import LimiterEngine
from gui.app import NetLimiterApp


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run_as_admin():
    """Relaunches the current script with Administrator elevation (UAC prompt)."""
    script = os.path.abspath(sys.argv[0])
    params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
    ret = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        f'"{script}" {params}',
        None,
        1,  # SW_SHOWNORMAL
    )
    return ret > 32


def main():
    # If not admin and not explicitly disabled, ask for UAC elevation
    if not is_admin() and "--no-elevate" not in sys.argv:
        print("[NetLimiter] Requesting Administrator privileges...")
        elevated = run_as_admin()
        if elevated:
            sys.exit(0)
        else:
            print("[NetLimiter] Running in standard mode...")

    # Initialize Core Services (1.0s interval for near-zero CPU footprint)
    rules = RuleManager()
    flow_tracker = FlowTracker(refresh_interval=1.0)
    monitor = SpeedMonitor(window_size=1.0)
    engine = LimiterEngine(rules, flow_tracker, monitor)

    # Start Limiter Engine
    engine.start()

    # Launch GUI
    app = NetLimiterApp(engine, rules, flow_tracker, monitor)

    def on_closing():
        """Cleanly and completely terminates the application and all background threads."""
        try:
            engine.stop()
        except Exception:
            pass
        try:
            app.destroy()
        except Exception:
            pass
        # os._exit guarantees immediate process termination without lingering background threads
        os._exit(0)

    app.protocol("WM_DELETE_WINDOW", on_closing)

    try:
        app.mainloop()
    except Exception:
        pass
    finally:
        on_closing()


if __name__ == "__main__":
    main()
