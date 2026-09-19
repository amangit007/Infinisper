@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   Building Infinisper Standalone Package & Installer
echo ===================================================

REM Ensure virtual environment is active or exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

echo [1/3] Installing PyInstaller...
pip install pyinstaller --upgrade --quiet

echo [2/3] Building Standalone Application with PyInstaller...
pyinstaller --noconfirm --clean infinisper.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    exit /b 1
)

echo [3/3] Checking for Inno Setup Compiler (iscc)...
where iscc >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Compiling Windows Installer with Inno Setup...
    iscc installer.iss
    if errorlevel 1 (
        echo [ERROR] Inno Setup compilation failed.
        exit /b 1
    )
    echo ===================================================
    echo SUCCESS: Installer generated in dist-installer\
    echo ===================================================
) else (
    echo [INFO] Inno Setup (iscc) not found on PATH.
    echo Standalone application binary created in dist\Infinisper\
    echo To build the setup installer, install Inno Setup 6 from https://jrsoftware.org/isdl.php
)

endlocal
