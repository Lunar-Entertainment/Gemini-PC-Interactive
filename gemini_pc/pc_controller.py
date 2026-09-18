import os
import sys
import time
import subprocess
import ctypes
from ctypes import wintypes
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image, ImageGrab
import pyautogui
import pyperclip
import psutil

# Safe PyAutoGUI settings
pyautogui.FAILSAFE = True  # Move mouse to top-left corner (0,0) to abort
pyautogui.PAUSE = 0.02     # Ultra-minimal delay between actions for maximum speed

class DesktopAttacher:
    """Ensures the calling thread is attached to the interactive desktop and sets DPI awareness."""
    _initialized = False

    @classmethod
    def ensure_desktop_access(cls):
        if sys.platform != "win32":
            return

        try:
            # Set Per-Monitor DPI Awareness v2
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

        try:
            user32 = ctypes.windll.user32
            # Check if already connected or try opening Default desktop
            hdesk = user32.OpenDesktopW("Default", 0, False, 0x10000000 | 0x01FF)
            if not hdesk:
                hdesk = user32.OpenInputDesktop(0, False, 0x10000000 | 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception as e:
            # Non-fatal if already in correct desktop
            pass
        cls._initialized = True


class PCController:
    """Controls mouse, keyboard, screen, applications, and OS commands on Windows."""

    def __init__(self):
        DesktopAttacher.ensure_desktop_access()

    def get_screen_size(self) -> Tuple[int, int]:
        DesktopAttacher.ensure_desktop_access()
        width, height = pyautogui.size()
        return width, height

    def get_mouse_position(self) -> Tuple[int, int]:
        DesktopAttacher.ensure_desktop_access()
        x, y = pyautogui.position()
        return x, y

    def take_screenshot(self) -> Image.Image:
        """Captures the current desktop screen."""
        DesktopAttacher.ensure_desktop_access()
        try:
            im = ImageGrab.grab(all_screens=False)
            return im
        except Exception:
            # Fallback to PyAutoGUI screenshot
            return pyautogui.screenshot()

    def mouse_move(self, x: int, y: int, duration: float = 0.05):
        DesktopAttacher.ensure_desktop_access()
        sw, sh = self.get_screen_size()
        x = max(0, min(int(round(x)), sw - 1))
        y = max(0, min(int(round(y)), sh - 1))
        pyautogui.moveTo(x, y, duration=duration)

    def mouse_click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1):
        DesktopAttacher.ensure_desktop_access()
        if x is not None and y is not None:
            sw, sh = self.get_screen_size()
            x = max(0, min(int(round(x)), sw - 1))
            y = max(0, min(int(round(y)), sh - 1))
            pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        else:
            pyautogui.click(button=button, clicks=clicks)

    def mouse_double_click(self, x: Optional[int] = None, y: Optional[int] = None):
        self.mouse_click(x=x, y=y, button="left", clicks=2)

    def mouse_right_click(self, x: Optional[int] = None, y: Optional[int] = None):
        self.mouse_click(x=x, y=y, button="right", clicks=1)

    def drag(self, from_x: int, from_y: int, to_x: int, to_y: int, duration: float = 0.15):
        DesktopAttacher.ensure_desktop_access()
        sw, sh = self.get_screen_size()
        from_x = max(0, min(int(round(from_x)), sw - 1))
        from_y = max(0, min(int(round(from_y)), sh - 1))
        to_x = max(0, min(int(round(to_x)), sw - 1))
        to_y = max(0, min(int(round(to_y)), sh - 1))
        self.mouse_move(from_x, from_y, duration=0.05)
        pyautogui.dragTo(to_x, to_y, duration=duration, button="left")

    def scroll(self, amount: int, x: Optional[int] = None, y: Optional[int] = None):
        """Scroll vertical: positive is up, negative is down."""
        DesktopAttacher.ensure_desktop_access()
        if x is not None and y is not None:
            pyautogui.scroll(amount, x=x, y=y)
        else:
            pyautogui.scroll(amount)

    def type_text(self, text: str, press_enter: bool = False):
        DesktopAttacher.ensure_desktop_access()
        # Check if text contains non-ASCII characters or emojis
        is_ascii = all(ord(c) < 128 for c in text)
        if is_ascii and len(text) < 40:
            pyautogui.write(text, interval=0.015)
        else:
            # Use clipboard paste for fast, 100% reliable Unicode / emoji support
            old_clip = pyperclip.paste()
            try:
                pyperclip.copy(text)
                time.sleep(0.05)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.05)
            finally:
                # Restore clipboard shortly after
                pass

        if press_enter:
            time.sleep(0.05)
            pyautogui.press("enter")

    def press_key(self, key: str):
        DesktopAttacher.ensure_desktop_access()
        key_map = {
            "enter": "enter",
            "return": "enter",
            "esc": "esc",
            "escape": "esc",
            "tab": "tab",
            "space": "space",
            "backspace": "backspace",
            "del": "delete",
            "delete": "delete",
            "win": "win",
            "windows": "win",
            "super": "win",
            "cmd": "win",
            "up": "up",
            "down": "down",
            "left": "left",
            "right": "right",
            "pageup": "pageup",
            "pagedown": "pagedown",
            "home": "home",
            "end": "end",
            "shift": "shift",
            "ctrl": "ctrl",
            "alt": "alt",
        }
        normalized = key.lower().strip()
        actual_key = key_map.get(normalized, normalized)
        pyautogui.press(actual_key)

    def hold_key(self, key: str, duration: float = 1.0):
        """Holds a keyboard key down for a specified duration in seconds before releasing it.
        Essential for game movement (holding 'w' to walk forward, 'shift' to sneak / avoid falling into lava,
        'space' to jump, 'a'/'d' to strafe).
        """
        DesktopAttacher.ensure_desktop_access()
        key_map = {
            "enter": "enter",
            "return": "enter",
            "esc": "esc",
            "escape": "esc",
            "tab": "tab",
            "space": "space",
            "backspace": "backspace",
            "del": "delete",
            "delete": "delete",
            "win": "win",
            "windows": "win",
            "shift": "shift",
            "ctrl": "ctrl",
            "alt": "alt",
            "up": "up",
            "down": "down",
            "left": "left",
            "right": "right",
        }
        normalized = key.lower().strip()
        actual_key = key_map.get(normalized, normalized)
        dur = min(max(duration, 0.05), 10.0)
        pyautogui.keyDown(actual_key)
        try:
            time.sleep(dur)
        finally:
            pyautogui.keyUp(actual_key)

    def mouse_move_relative(self, dx: int, dy: int):
        """Moves the mouse cursor by a relative delta (dx, dy).
        Uses low-level hardware mouse events (MOUSEEVENTF_MOVE), essential for 3D games
        (e.g., Minecraft, FPS games) and camera rotation where absolute cursor movement does not work.
        """
        DesktopAttacher.ensure_desktop_access()
        if sys.platform == "win32":
            ctypes.windll.user32.mouse_event(0x0001, int(dx), int(dy), 0, 0)
        else:
            pyautogui.moveRel(int(dx), int(dy))

    def game_look(self, direction: str = "right", degrees: int = 45):
        """Turns the 3D camera in games (like Minecraft) by the specified angle in degrees.
        Supports 'left', 'right', 'up', 'down'.
        Translates degrees to hardware mouse deltas (~6 pixels per degree).
        """
        dir_lower = direction.lower().strip()
        pixels = int(round(abs(degrees) * 6.0))
        dx, dy = 0, 0
        if "left" in dir_lower:
            dx = -pixels
        elif "right" in dir_lower:
            dx = pixels
        elif "up" in dir_lower:
            dy = -pixels
        elif "down" in dir_lower:
            dy = pixels
        self.mouse_move_relative(dx, dy)

    def hotkey(self, *keys):
        DesktopAttacher.ensure_desktop_access()
        # Expand combinations if passed as 'ctrl+c'
        actual_keys = []
        for k in keys:
            if "+" in k:
                actual_keys.extend([part.strip().lower() for part in k.split("+")])
            else:
                actual_keys.append(k.strip().lower())

        pyautogui.hotkey(*actual_keys)

    def open_application(self, target: str) -> str:
        """Launches an application, executable, file, or URL."""
        DesktopAttacher.ensure_desktop_access()
        target = target.strip()
        common_apps = {
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "calc": "calc.exe",
            "explorer": "explorer.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "chrome": "chrome",
            "edge": "msedge",
            "code": "code",
            "terminal": "wt.exe",
            "taskmgr": "taskmgr.exe",
            "paint": "mspaint.exe",
            "settings": "ms-settings:",
        }

        exec_cmd = common_apps.get(target.lower(), target)
        try:
            # Check if it's a URL or uri scheme
            if "://" in exec_cmd or exec_cmd.endswith(":"):
                os.startfile(exec_cmd)
                return f"Successfully opened URI '{exec_cmd}'"

            # Use subprocess to launch detached
            subprocess.Popen(exec_cmd, shell=True)
            return f"Successfully started '{exec_cmd}'"
        except Exception as e:
            # Fallback to Start-Process via PowerShell
            try:
                subprocess.Popen(["powershell", "-NoProfile", "-Command", f"Start-Process '{exec_cmd}'"], shell=True)
                return f"Started '{exec_cmd}' via PowerShell"
            except Exception as e2:
                return f"Failed to launch '{target}': {str(e2)}"

    def run_command(self, command: str, timeout: int = 15) -> Dict[str, Any]:
        """Runs a command via PowerShell safely, returning stdout, stderr, and return code."""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            # Truncate if excessively long
            if len(stdout) > 4000:
                stdout = stdout[:4000] + "\n... [Output truncated]"
            if len(stderr) > 2000:
                stderr = stderr[:2000] + "\n... [Error truncated]"

            return {
                "success": result.returncode == 0,
                "return_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "return_code": -1, "stdout": "", "stderr": f"Command timed out after {timeout} seconds"}
        except Exception as e:
            return {"success": False, "return_code": -1, "stdout": "", "stderr": str(e)}

    def list_windows(self) -> List[Dict[str, Any]]:
        """Lists currently visible top-level desktop windows."""
        windows = []
        if sys.platform != "win32":
            return windows

        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def enum_callback(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buffer, length + 1)
                    title = buffer.value.strip()
                    # Filter out empty or system shell trays
                    if title and title not in ("Program Manager", "Settings", "Default IME", "MSCTFIME UI"):
                        rect = wintypes.RECT()
                        user32.GetWindowRect(hwnd, ctypes.byref(rect))
                        w = rect.right - rect.left
                        h = rect.bottom - rect.top
                        if w > 50 and h > 50:
                            windows.append({
                                "hwnd": hwnd,
                                "title": title,
                                "bounds": {"x": rect.left, "y": rect.top, "width": w, "height": h}
                            })
            return True

        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        return windows

    def focus_window(self, title_query: str) -> bool:
        """Finds and brings a window to the foreground."""
        DesktopAttacher.ensure_desktop_access()
        if sys.platform != "win32":
            return False

        user32 = ctypes.windll.user32
        windows = self.list_windows()
        target_hwnd = None

        query_lower = title_query.lower()
        for win in windows:
            if query_lower in win["title"].lower():
                target_hwnd = win["hwnd"]
                break

        if not target_hwnd:
            return False

        # Windows foreground activation bypass: tap Alt key
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)

        # SW_RESTORE = 9
        user32.ShowWindow(target_hwnd, 9)
        time.sleep(0.05)
        user32.BringWindowToTop(target_hwnd)
        user32.SetForegroundWindow(target_hwnd)

        # If window was outside primary monitor, reposition to primary monitor
        sw, sh = self.get_screen_size()
        rect = wintypes.RECT()
        user32.GetWindowRect(target_hwnd, ctypes.byref(rect))
        bw = rect.right - rect.left
        bh = rect.bottom - rect.top
        if rect.left >= sw or rect.right <= 0 or rect.top >= sh:
            user32.MoveWindow(target_hwnd, 60, 60, min(bw, sw - 120), min(bh, sh - 120), True)

        # Click center of window to ensure keyboard focus and 3D game mouse lock
        time.sleep(0.15)
        cx = max(rect.left + 50, min(rect.left + bw // 2, sw - 50))
        cy = max(rect.top + 50, min(rect.top + bh // 2, sh - 50))
        pyautogui.click(cx, cy)

        return True

    def read_clipboard(self) -> str:
        try:
            return pyperclip.paste() or ""
        except Exception:
            return ""

    def write_clipboard(self, text: str) -> bool:
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            return False

    def get_system_info(self) -> Dict[str, Any]:
        """Returns current system resource utilization and active foreground window."""
        DesktopAttacher.ensure_desktop_access()
        sw, sh = self.get_screen_size()
        mx, my = self.get_mouse_position()

        active_title = "Unknown"
        if sys.platform == "win32":
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    active_title = buf.value

        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()

        return {
            "screen_resolution": f"{sw}x{sh}",
            "mouse_position": {"x": mx, "y": my},
            "active_window": active_title,
            "cpu_usage_pct": cpu,
            "ram_used_gb": round((mem.total - mem.available) / (1024 ** 3), 2),
            "ram_total_gb": round(mem.total / (1024 ** 3), 2),
            "ram_percent": mem.percent,
        }

# Global singleton
controller = PCController()
