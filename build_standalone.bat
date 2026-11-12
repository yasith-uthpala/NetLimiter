@echo off
title Building Standalone NetLimiter.exe...
cd /d "%~dp0"

echo Installing/Checking PyInstaller...
python -m pip install pyinstaller >nul 2>&1

echo Building single-file standalone NetLimiter.exe...
python -m PyInstaller --noconfirm --onefile --windowed --uac-admin ^
    --icon "assets\icon.ico" ^
    --collect-all customtkinter ^
    --collect-all pydivert ^
    --add-data "drivers;drivers" ^
    --add-data "assets;assets" ^
    --name "NetLimiter" main.py

echo.
if exist "dist\NetLimiter.exe" (
    echo Build succeeded! Standalone executable: dist\NetLimiter.exe
) else (
    echo Build failed!
)
pause
