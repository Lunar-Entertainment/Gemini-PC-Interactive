import time
from typing import Dict, Any, List, Optional
from gemini_pc.pc_controller import controller

class DesktopTools:
    """Provides tools callable by the Gemini agent to interact with the PC."""

    @staticmethod
    def mouse_click(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
        """
        Clicks at the specified screen coordinate (x, y).
        
        Args:
            x: Horizontal coordinate on a 0 to 1000 normalized scale (0 = leftmost edge, 1000 = rightmost edge, 500 = center).
            y: Vertical coordinate on a 0 to 1000 normalized scale (0 = topmost edge, 1000 = bottommost edge, 500 = center).
            button: 'left' or 'right' or 'middle'. Default is 'left'.
            clicks: 1 for single click, 2 for double click.
        """
        controller.mouse_click(x=x, y=y, button=button, clicks=clicks)
        return f"Clicked {button} button at ({x}, {y}) (clicks: {clicks})"

    @staticmethod
    def mouse_double_click(x: int, y: int) -> str:
        """
        Double clicks at the specified screen coordinate (x, y).
        
        Args:
            x: Horizontal coordinate on a 0 to 1000 normalized scale (0 = leftmost edge, 1000 = rightmost edge, 500 = center).
            y: Vertical coordinate on a 0 to 1000 normalized scale (0 = topmost edge, 1000 = bottommost edge, 500 = center).
        """
        controller.mouse_double_click(x=x, y=y)
        return f"Double clicked at ({x}, {y})"

    @staticmethod
    def move_mouse(x: int, y: int) -> str:
        """
        Moves the mouse cursor to (x, y) without clicking.
        
        Args:
            x: Horizontal coordinate on a 0 to 1000 normalized scale (0 = leftmost edge, 1000 = rightmost edge, 500 = center).
            y: Vertical coordinate on a 0 to 1000 normalized scale (0 = topmost edge, 1000 = bottommost edge, 500 = center).
        """
        controller.mouse_move(x=x, y=y)
        return f"Moved cursor to ({x}, {y})"

    @staticmethod
    def drag_and_drop(from_x: int, from_y: int, to_x: int, to_y: int) -> str:
        """
        Drags an item from (from_x, from_y) and drops it at (to_x, to_y).
        
        Args:
            from_x: Starting horizontal coordinate (0-1000 normalized scale).
            from_y: Starting vertical coordinate (0-1000 normalized scale).
            to_x: Ending horizontal coordinate (0-1000 normalized scale).
            to_y: Ending vertical coordinate (0-1000 normalized scale).
        """
        controller.drag(from_x=from_x, from_y=from_y, to_x=to_x, to_y=to_y)
        return f"Dragged from ({from_x}, {from_y}) to ({to_x}, {to_y})"

    @staticmethod
    def type_text(text: str, press_enter: bool = False) -> str:
        """
        Types the given text into the currently active/focused input field or window.
        Supports Unicode, foreign characters, and emojis.
        
        Args:
            text: Text to type into the focused element.
            press_enter: If True, presses the Enter key immediately after typing.
        """
        controller.type_text(text=text, press_enter=press_enter)
        return f"Typed text '{text[:40]}{'...' if len(text) > 40 else ''}' (press_enter={press_enter})"

    @staticmethod
    def press_key(key: str) -> str:
        """
        Presses a single keyboard key.
        
        Args:
            key: Key name, such as 'enter', 'tab', 'esc', 'backspace', 'space', 'win', 'up', 'down', 'left', 'right'.
        """
        controller.press_key(key=key)
        return f"Pressed key '{key}'"

    @staticmethod
    def hold_key(key: str, duration: float = 1.0) -> str:
        """
        Holds a keyboard key down for a specified duration in seconds before releasing it.
        Essential for game movement (holding 'w' to walk forward, 'shift' to sneak / avoid falling into lava, 'space' to jump, 'a'/'d' to strafe).
        
        Args:
            key: Key name, such as 'w', 's', 'a', 'd', 'shift', 'space', 'ctrl', 'alt'.
            duration: Number of seconds to hold the key down (e.g. 0.5 to 3.0).
        """
        controller.hold_key(key=key, duration=duration)
        return f"Held key '{key}' down for {duration} seconds."

    @staticmethod
    def mouse_move_relative(dx: int, dy: int) -> str:
        """
        Moves the mouse cursor by a relative offset (dx, dy) using low-level hardware events.
        CRITICAL FOR 3D GAMES (like Minecraft or FPS games) and camera rotation where absolute cursor movement does not work.
        
        Args:
            dx: Horizontal pixel delta (negative = turn left, positive = turn right).
            dy: Vertical pixel delta (negative = turn up / look up, positive = turn down / look down).
        """
        controller.mouse_move_relative(dx=dx, dy=dy)
        return f"Moved mouse relatively by (dx={dx}, dy={dy})"

    @staticmethod
    def game_look(direction: str = "right", degrees: int = 45) -> str:
        """
        Turns the 3D camera in games (like Minecraft) smoothly in the specified direction.
        
        Args:
            direction: 'left', 'right', 'up', or 'down'.
            degrees: Approximate angle to turn in degrees (e.g. 45, 90, 180).
        """
        controller.game_look(direction=direction, degrees=degrees)
        return f"Turned 3D camera {direction} by ~{degrees} degrees."

    @staticmethod
    def key_combination(keys: str) -> str:
        """
        Presses multiple keys simultaneously as a hotkey combination.
        
        Args:
            keys: Combination separated by plus, e.g. 'ctrl+c', 'ctrl+v', 'win+r', 'alt+tab', 'ctrl+a', 'alt+f4', 'ctrl+shift+esc'.
        """
        controller.hotkey(keys)
        return f"Pressed key combination '{keys}'"

    @staticmethod
    def scroll_screen(amount: int, x: int = 0, y: int = 0) -> str:
        """
        Scrolls the mouse wheel up or down.
        
        Args:
            amount: Positive integer to scroll up (e.g. 300), negative integer to scroll down (e.g. -300).
            x: Optional horizontal coordinate on a 0-1000 normalized scale to place cursor before scrolling.
            y: Optional vertical coordinate on a 0-1000 normalized scale to place cursor before scrolling.
        """
        pos_x = x if (x > 0 or y > 0) else None
        pos_y = y if (x > 0 or y > 0) else None
        controller.scroll(amount=amount, x=pos_x, y=pos_y)
        return f"Scrolled {'up' if amount > 0 else 'down'} by {abs(amount)}"

    @staticmethod
    def open_application(app_or_path: str) -> str:
        """
        Opens an application, URL, or file path.
        
        Args:
            app_or_path: Name of app (e.g. 'notepad', 'calc', 'chrome', 'msedge', 'explorer', 'code', 'cmd') or full path or URL.
        """
        res = controller.open_application(app_or_path)
        # Give the app a moment to launch
        time.sleep(0.3)
        return res

    @staticmethod
    def focus_window(window_title: str) -> str:
        """
        Brings a window matching the title query to the foreground and focuses it.
        
        Args:
            window_title: Substring or full title of the window to focus.
        """
        success = controller.focus_window(window_title)
        if success:
            time.sleep(0.1)
            return f"Successfully focused window matching '{window_title}'"
        return f"Could not find any open window matching '{window_title}'"

    @staticmethod
    def list_open_windows() -> str:
        """
        Lists all visible top-level application windows currently open on the desktop.
        """
        windows = controller.list_windows()
        if not windows:
            return "No visible application windows found."
        titles = [f"- {w['title']} (bounds: {w['bounds']['width']}x{w['bounds']['height']} at {w['bounds']['x']},{w['bounds']['y']})" for w in windows]
        return "Open visible windows:\n" + "\n".join(titles)

    @staticmethod
    def run_system_command(command: str) -> str:
        """
        Executes a command via PowerShell on the PC and returns the terminal output.
        Useful for querying files, inspecting system status, checking network, or executing batch operations.
        
        Args:
            command: The PowerShell command line to execute.
        """
        res = controller.run_command(command)
        out = f"Return Code: {res['return_code']}\n"
        if res["stdout"]:
            out += f"STDOUT:\n{res['stdout']}\n"
        if res["stderr"]:
            out += f"STDERR:\n{res['stderr']}\n"
        return out.strip()

    @staticmethod
    def read_clipboard() -> str:
        """
        Reads the text currently copied to the system clipboard.
        """
        clip = controller.read_clipboard()
        return f"Clipboard text:\n{clip}"

    @staticmethod
    def write_clipboard(text: str) -> str:
        """
        Sets the system clipboard to the specified text.
        """
        controller.write_clipboard(text)
        return "Successfully copied text to clipboard."

    @staticmethod
    def wait_seconds(seconds: float) -> str:
        """
        Waits for a specified duration in seconds (e.g. 1.0 to 3.0) for UI transitions or page loads.
        
        Args:
            seconds: Number of seconds to wait (maximum 10.0).
        """
        dur = min(max(seconds, 0.1), 10.0)
        time.sleep(dur)
        return f"Waited {dur} seconds."

    @staticmethod
    def finish_task(summary: str, success: bool = True) -> str:
        """
        Signals that the task has been finished or cannot proceed further.
        
        Args:
            summary: Detailed explanation of what was achieved or the final answer to the user.
            success: Whether the task was completed successfully.
        """
        return f"TASK_COMPLETED: success={success}, summary={summary}"


# Function list for Gemini Tool registration
ALL_DESKTOP_FUNCTIONS = [
    DesktopTools.mouse_click,
    DesktopTools.mouse_double_click,
    DesktopTools.move_mouse,
    DesktopTools.mouse_move_relative,
    DesktopTools.game_look,
    DesktopTools.drag_and_drop,
    DesktopTools.type_text,
    DesktopTools.press_key,
    DesktopTools.hold_key,
    DesktopTools.key_combination,
    DesktopTools.scroll_screen,
    DesktopTools.open_application,
    DesktopTools.focus_window,
    DesktopTools.list_open_windows,
    DesktopTools.run_system_command,
    DesktopTools.read_clipboard,
    DesktopTools.write_clipboard,
    DesktopTools.wait_seconds,
    DesktopTools.finish_task,
]

# Dispatcher mapping name -> callable
TOOL_DISPATCHER = {fn.__name__: fn for fn in ALL_DESKTOP_FUNCTIONS}
