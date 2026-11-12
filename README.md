# ⚡ NetLimiter — Lightweight Bandwidth Traffic Controller for Windows

A modern, lightweight Windows desktop application inspired by **NetLimiter** that discovers all running applications using your network and allows you to enforce **Download (Inbound)** and **Upload (Outbound)** bandwidth limits in **KB/s, MB/s, Kbps, or Mbps** — per application or across your **entire PC**.

---

## ✨ Features

- **🌐 Master PC Speed Limit**: Enforce a global bandwidth cap across your entire computer (e.g., cap total PC download to `5 MB/s` or `10 MB/s`).
- **🚀 Dual-Engine Architecture (WinDivert + Native Windows QoS)**:
  - **WinDivert Packet Pacer**: Intercepts TCP/UDP packets and uses a smooth **Token Bucket** delay queue for accurate bi-directional rate shaping without dropping connections.
  - **Native Windows QoS Fallback**: Automatically applies hardware-level NDIS policies (`NetQoSPolicy`) so limits always take effect reliably.
- **🗂️ Smart Application Grouping & Icons**:
  - Automatically groups multi-process apps (like Chrome, Discord, Edge) into a single clean card with aggregated speeds and socket counts.
  - Extracts authentic Windows application icons natively via Win32 API.
  - Expandable tree view (`▶`) to inspect or limit individual Process IDs (PIDs).
- **📈 Real-Time Bandwidth Sparkline**: Live 30-second rolling graph showing system download and upload throughput.
- **⚡ Ultra-Lightweight & Clean Exit**: Near-zero CPU footprint (`1.0s` polling with in-memory caching) and terminates completely on close with zero background lingering processes.
- **🔄 Automatic UAC Elevation**: Prompts for Windows Administrator privileges required for network-level shaping.

---

## 🚀 Quick Start

### 1. Prerequisites
- Windows 10 or Windows 11 (64-bit)
- Python 3.10+

### 2. Installation
```powershell
git clone https://github.com/yasith-uthpala/NetLimiter.git
cd NetLimiter
pip install -r requirements.txt
```

### 3. Run the Application
```powershell
python main.py
```
*(Accept the Windows UAC Administrator prompt when starting.)*

---

## 📦 Building a Standalone `.exe`

To package NetLimiter into a standalone Windows executable with an embedded icon and UAC manifest:

```powershell
pip install pyinstaller
python -m PyInstaller --noconfirm --onedir --windowed --uac-admin --icon "assets\icon.ico" --collect-all customtkinter --collect-all pydivert --add-data "drivers;drivers" --add-data "assets;assets" --name "NetLimiter" main.py
```

Copy `drivers\WinDivert.dll` and `drivers\WinDivert64.sys` into `dist\NetLimiter\`.

---

## 🛠️ Project Structure

```
NetLimiter/
├── assets/
│   ├── icon.ico               # Application executable & window icon
│   └── icon.png               # High-res icon asset
├── core/
│   ├── flow_tracker.py        # Socket-to-PID resolver (iphlpapi.dll) & grouping
│   ├── icon_extractor.py      # Native Windows .exe icon extractor
│   ├── limiter.py             # WinDivert packet interception & token bucket pacer
│   ├── monitor.py             # Real-time speed calculator & history buffer
│   ├── qos.py                 # Native Windows NetQoSPolicy controller
│   ├── rules.py               # Rule manager, master cap & JSON persistence
│   └── token_bucket.py        # High-precision token bucket algorithm
├── drivers/
│   ├── WinDivert.dll          # 64-bit WinDivert DLL
│   └── WinDivert64.sys        # Digitally signed 64-bit kernel driver
├── gui/
│   ├── app.py                 # Main CustomTkinter dark-mode dashboard
│   ├── graph_widget.py        # Live 30s bandwidth sparkline canvas
│   └── rule_dialog.py         # Per-app, manual, and master limit dialogs
├── main.py                    # Entrypoint with UAC elevation & clean exit
└── requirements.txt           # Python dependencies
```

---

## 📄 License

MIT License
