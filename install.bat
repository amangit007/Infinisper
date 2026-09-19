@echo off
title Infinisper Installer
cd /d "%~dp0"

echo ========================================================
echo                 Infinisper Setup
echo   On-device AI Dictation for Windows
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.12 or newer is required but was not found in PATH.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

python -c "import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] < (3, 15) else 1)" >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Infinisper needs Python 3.12, 3.13 or 3.14. You have:
    python --version
    echo Install a supported version from https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [1/3] Creating Python virtual environment...
    python -m venv .venv
)

echo [2/3] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo [3/3] Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Installing dependencies failed. The message above says why.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   Installation completed successfully!
echo   Run 'run.bat' or 'python main.py' to start Infinisper.
echo ========================================================
echo.
pause
