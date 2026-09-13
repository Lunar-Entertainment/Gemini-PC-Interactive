@echo off
title Gemini PC Interactive
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting Gemini PC Interactive...
"%PYTHON_EXE%" app.py
pause
