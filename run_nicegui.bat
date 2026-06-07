@echo off
setlocal
title Shadow Stock ERP (NiceGUI)

color 0B

echo ======================================================
echo       SHADOW STOCK ERP  --  NICEGUI DASHBOARD
echo ======================================================

cd /d "%~dp0"

set VENV_PYTHON="%~dp0venv\Scripts\python.exe"

if not exist %VENV_PYTHON% (
    color 0C
    echo [ERROR] venv not found!
    echo [FIX]   Run: python -m venv venv
    pause
    exit /b 1
)

echo [INFO]  Starting NiceGUI server on port 8080...
echo [INFO]  Open in browser: http://localhost:8080
echo [INFO]  Press Ctrl+C to stop
echo ------------------------------------------------------

%VENV_PYTHON% src\main.py

if errorlevel 1 (
    color 0C
    echo.
    echo [ERROR] Startup failed. Check the logs above.
    pause
)
