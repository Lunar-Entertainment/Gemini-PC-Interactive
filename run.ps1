<#
.SYNOPSIS
    Launches Gemini PC Interactive (FastAPI server + Web Dashboard).
.DESCRIPTION
    Detects the virtual environment, resolves configuration, and starts app.py.
#>

[CmdletBinding()]
param(
    [string]$Port,
    [string]$HostAddress
)

$ErrorActionPreference = "Stop"

# Set Window Title
try {
    $Host.UI.RawUI.WindowTitle = "Gemini PC Interactive"
} catch {
    # Non-fatal if host doesn't support setting window title
}

# Resolve script directory
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
}
Set-Location -Path $ScriptDir

# Welcome Banner
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "         GEMINI PC INTERACTIVE - AI DESKTOP CONTROLLER      " -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Locate Python Executable
$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
    Write-Host "[+] Virtual environment detected: venv" -ForegroundColor Green
} else {
    $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCmd) {
        $PythonCmd = Get-Command py -ErrorAction SilentlyContinue
    }
    if (-not $PythonCmd) {
        Write-Host "[!] Error: Python executable not found. Please install Python 3.10+ or configure venv." -ForegroundColor Red
        if ($Host.Name -eq "ConsoleHost") {
            Read-Host "Press Enter to exit..."
        }
        exit 1
    }
    $PythonExe = $PythonCmd.Source
    Write-Host "[!] Notice: 'venv' not found. Falling back to system Python: $PythonExe" -ForegroundColor Yellow
}

# Ensure .env exists if .env.example is present
$EnvFile = Join-Path $ScriptDir ".env"
$EnvExample = Join-Path $ScriptDir ".env.example"
if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
    Write-Host "[*] Creating .env from .env.example..." -ForegroundColor Cyan
    Copy-Item $EnvExample $EnvFile
}

# Pass optional overrides via environment variables
if ($Port) { $env:PORT = $Port }
if ($HostAddress) { $env:HOST = $HostAddress }

# Start Application
Write-Host "[*] Starting server and opening dashboard in default browser..." -ForegroundColor Cyan
Write-Host ""

try {
    & $PythonExe (Join-Path $ScriptDir "app.py") @args
} catch {
    Write-Host ""
    Write-Host "[!] Error during execution: $_" -ForegroundColor Red
} finally {
    if ($Host.Name -eq "ConsoleHost") {
        Write-Host ""
        Write-Host "Process stopped." -ForegroundColor DarkGray
    }
}
