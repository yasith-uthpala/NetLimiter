@echo off
title Starting NetLimiter...
cd /d "%~dp0"

if exist "dist\NetLimiter\NetLimiter.exe" (
    start "" "dist\NetLimiter\NetLimiter.exe"
    exit /b
)

if exist "main.py" (
    start "" pythonw main.py
    exit /b
)

echo NetLimiter executable not found!
pause
