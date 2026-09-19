<#
.SYNOPSIS
    Builds the standalone Gemini PC Interactive Windows Desktop Executable (.exe).
.DESCRIPTION
    Runs PyInstaller via build_exe.py to create dist/GeminiPCInteractive.exe.
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   Gemini PC Interactive — Build Standalone Desktop .EXE" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan

$PythonExe = Join-Path $ScriptDir "venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

Write-Host "`nInvoking build_exe.py using $PythonExe...`n" -ForegroundColor DarkGray

& $PythonExe build_exe.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n============================================================" -ForegroundColor Green
    Write-Host " Build succeeded! Your desktop executable is ready:" -ForegroundColor Green
    Write-Host "   $(Join-Path $ScriptDir 'dist\GeminiPCInteractive.exe')" -ForegroundColor Yellow
    Write-Host "============================================================`n" -ForegroundColor Green
} else {
    Write-Host "`n[ERROR] Build exited with code $LASTEXITCODE" -ForegroundColor Red
}
