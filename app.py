import os
import sys
import webbrowser
import threading
import time
import uvicorn
from gemini_pc.config import settings

import socket

def find_available_port(host: str, start_port: int) -> int:
    for port in range(start_port, start_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return start_port

def open_browser():
    time.sleep(1.2)
    url = f"http://{settings.HOST}:{settings.PORT}"
    print(f"\n[Gemini PC Interactive] Dashboard ready at {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass

def main():
    # Detect available port
    actual_port = find_available_port(settings.HOST, settings.PORT)
    settings.PORT = actual_port

    print("=" * 60)
    print("       GEMINI PC INTERACTIVE - AI DESKTOP AGENT")
    print("=" * 60)
    print(f"Host: {settings.HOST} | Port: {settings.PORT}")
    print(f"Default Model: {settings.DEFAULT_MODEL}")
    print(f"API Key Configured: {bool(settings.GEMINI_API_KEY)}")
    print("=" * 60)

    # Launch browser automatically
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    # Run Uvicorn server
    uvicorn.run(
        "gemini_pc.server:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
        reload=False
    )

if __name__ == "__main__":
    main()
