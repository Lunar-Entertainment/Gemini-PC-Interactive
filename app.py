import os
import sys
import socket
import threading
import time
import webbrowser
import multiprocessing
import uvicorn
from gemini_pc.config import settings

# Safely handle stdout/stderr when running as a windowed application without a console
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

def find_available_port(host: str, start_port: int) -> int:
    for port in range(start_port, start_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return start_port

def wait_for_server(host: str, port: int, timeout: float = 6.0) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.05)
    return False

def main():
    multiprocessing.freeze_support()

    # Detect available port
    actual_port = find_available_port(settings.HOST, settings.PORT)
    settings.PORT = actual_port

    target_url = f"http://{settings.HOST}:{settings.PORT}"

    use_browser_mode = "--browser" in sys.argv
    use_headless_mode = "--headless" in sys.argv

    # Start Uvicorn in background daemon thread
    def run_uvicorn():
        from gemini_pc.server import app as fastapi_app
        config = uvicorn.Config(
            fastapi_app,
            host=settings.HOST,
            port=settings.PORT,
            log_level="warning",
            reload=False
        )
        server = uvicorn.Server(config)
        server.run()

    server_thread = threading.Thread(target=run_uvicorn, daemon=True)
    server_thread.start()

    # Wait for local server to accept connections
    wait_for_server(settings.HOST, settings.PORT)

    if use_headless_mode:
        print(f"[Gemini PC Interactive] Server running at {target_url} (Headless)")
        server_thread.join()
        return

    if use_browser_mode:
        webbrowser.open(target_url)
        print(f"[Gemini PC Interactive] Browser opened at {target_url}")
        server_thread.join()
        return

    # Default: Native standalone desktop application window
    try:
        import webview
        window = webview.create_window(
            title="Gemini PC Interactive",
            url=target_url,
            width=1440,
            height=900,
            min_size=(1024, 700),
            background_color="#090d16",
            text_select=True
        )
        webview.start()
    except Exception as ex:
        # Fallback to browser if webview has any system-level issue
        webbrowser.open(target_url)
        server_thread.join()

if __name__ == "__main__":
    main()
