import os
import sys
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def build():
    print("=" * 60)
    print("Building standalone desktop executable for Gemini PC Interactive...")
    print("=" * 60)

    # 1. Ensure icon exists
    icon_path = BASE_DIR / "icon.ico"
    if not icon_path.exists():
        from generate_icon import create_app_icon
        create_app_icon()

    # 2. PyInstaller command
    pyinstaller_exe = BASE_DIR / "venv" / "Scripts" / "pyinstaller.exe"
    cmd_exec = str(pyinstaller_exe) if pyinstaller_exe.exists() else "pyinstaller"

    cmd = [
        cmd_exec,
        "--name=GeminiPCInteractive",
        "--onefile",
        f"--icon={str(icon_path)}",
        f"--add-data={str(BASE_DIR / 'web')};web",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.loops.asyncio",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.http.h11_impl",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.protocols.websockets.websockets_impl",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=pynput.keyboard._win32",
        "--hidden-import=pynput.mouse._win32",
        "--hidden-import=google.genai",
        "--clean",
        "--noconfirm",
        str(BASE_DIR / "app.py")
    ]

    print(f"Executing: {' '.join(cmd)}\n")
    ret = subprocess.run(cmd, cwd=str(BASE_DIR))
    if ret.returncode == 0:
        exe_path = BASE_DIR / "dist" / "GeminiPCInteractive.exe"
        print("\n" + "=" * 60)
        print(f"[SUCCESS] Standalone desktop executable built successfully!")
        print(f"Location: {exe_path}")
        print("=" * 60)

        # Copy .env into dist folder so the standalone .exe has initial credentials
        dist_dir = BASE_DIR / "dist"
        if (BASE_DIR / ".env").exists():
            shutil.copy(BASE_DIR / ".env", dist_dir / ".env")
            print("Copied active .env to dist/ folder for portable execution.")
        elif (BASE_DIR / ".env.example").exists():
            shutil.copy(BASE_DIR / ".env.example", dist_dir / ".env")
            print("Copied .env.example to dist/.env.")
    else:
        print(f"\n[ERROR] PyInstaller build failed with exit code {ret.returncode}")
        sys.exit(ret.returncode)

if __name__ == "__main__":
    build()
