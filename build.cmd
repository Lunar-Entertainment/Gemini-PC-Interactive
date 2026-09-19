@echo off
rem ============================================================
rem   Gemini PC Interactive — Build Standalone Desktop .EXE
rem ============================================================
title Build Gemini PC Interactive EXE
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo.
echo ============================================================
echo   Building GeminiPCInteractive.exe...
echo ============================================================
echo.

"%PYTHON_EXE%" build_exe.py %*

if errorlevel 1 (
    echo.
    echo Build failed with code %ERRORLEVEL%.
    pause
) else (
    echo.
    echo Standalone executable is ready in:
    echo   dist\GeminiPCInteractive.exe
    echo.
    pause
)
