@echo off
title Infinisper
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [Infinisper] Virtual environment not found. Running setup...
    call install.bat
)

echo [Infinisper] Starting Infinisper...
start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0
