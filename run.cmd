@echo off
rem ============================================================
rem   Gemini PC Interactive — Launcher (Windows CMD)
rem ============================================================
title Gemini PC Interactive
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo.
echo ============================================================
echo   Starting Gemini PC Interactive...
echo ============================================================
echo.

"%PYTHON_EXE%" app.py %*

if errorlevel 1 (
    echo.
    echo Process exited with code %ERRORLEVEL%.
    pause
)
