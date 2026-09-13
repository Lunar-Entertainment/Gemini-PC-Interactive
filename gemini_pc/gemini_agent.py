import os
import time
import threading
import logging
from enum import Enum
from typing import Callable, Optional, Dict, Any, List
from PIL import Image

from google import genai
from google.genai import types

from gemini_pc.config import settings
from gemini_pc.pc_controller import controller
from gemini_pc.visual_grounding import VisualGrounding
from gemini_pc.tools import ALL_DESKTOP_FUNCTIONS, TOOL_DISPATCHER

logger = logging.getLogger("GeminiAgent")

class AgentStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    STOPPED = "STOPPED"
    FINISHED = "FINISHED"
    ERROR = "ERROR"


SYSTEM_INSTRUCTION = """You are Gemini PC Interactive, an autonomous AI desktop agent capable of seeing the user's computer screen and controlling the PC to accomplish user goals.

You have access to tools to:
1. Click mouse coordinates (x, y), double-click, move, drag, and scroll.
2. Type text, press keys (enter, tab, esc, win, etc.), and use keyboard shortcuts (ctrl+c, ctrl+v, win+r, alt+tab, etc.).
3. Open applications (e.g. 'notepad', 'calc', 'chrome', 'msedge', 'code', 'explorer'), focus windows, or list open windows.
4. Run system commands in PowerShell for file manipulation or status queries.
5. Read/write system clipboard.
6. Call `finish_task(summary, success)` when your objective is achieved or cannot proceed.

OPERATIONAL GUIDELINES:
- Examine the provided screenshot carefully to locate UI elements, text, buttons, and input fields.
- Coordinates (x, y) represent actual screen pixels. Use the coordinate markers/grid or element visual position to estimate exact button centers.
- Before interacting with an application, ensure it is in the foreground. If an app isn't open, use `open_application` to launch it.
- After typing into a search bar or run prompt, press 'enter' if needed.
- If you need to open an app via Start Menu or Run dialog, you can use `key_combination("win+r")`, wait a moment, then type the command and press enter.
- Always provide your concise reasoning before taking an action: Explain what you see and why you are taking the tool call.
- When the user's goal is fully achieved, call `finish_task` with a clear summary of what was done.
- If you run into an error or unexpected screen state, re-orient yourself by looking at the new screenshot and adapt.
"""

class GeminiAgent:
    """Manages autonomous agent interaction with Gemini and the desktop."""

    def __init__(self):
        self.status: AgentStatus = AgentStatus.IDLE
        self.current_goal: str = ""
        self.current_step: int = 0
        self.max_steps: int = settings.MAX_AGENT_STEPS
        self.stop_requested: bool = False
        self.paused: bool = False
        self.pending_approval_tool: Optional[Dict[str, Any]] = None
        self.approval_event = threading.Event()
        self.approval_result: bool = False
        self.event_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._thread: Optional[threading.Thread] = None
        self._setup_killswitch()

    def register_callback(self, callback: Callable[[Dict[str, Any]], None]):
        self.event_callbacks.append(callback)

    def emit(self, event_type: str, data: Dict[str, Any]):
        payload = {"type": event_type, "timestamp": time.time(), "data": data}
        for cb in self.event_callbacks:
            try:
                cb(payload)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")

    def _setup_killswitch(self):
        """Sets up a global emergency stop hotkey (Esc key or Pause)."""
        try:
            from pynput import keyboard

            def on_press(key):
                if key == keyboard.Key.esc and self.status == AgentStatus.RUNNING:
                    logger.warning("Emergency Stop hotkey (ESC) detected!")
                    self.stop()
                    self.emit("alert", {"message": "Emergency Stop activated via ESC key!"})

            listener = keyboard.Listener(on_press=on_press)
            listener.daemon = True
            listener.start()
        except Exception as e:
            logger.warning(f"Could not initialize pynput keyboard listener: {e}")

    def start_goal(self, goal: str, model_name: Optional[str] = None, require_approval: bool = False):
        if self.status == AgentStatus.RUNNING:
            return False

        self.current_goal = goal.strip()
        self.current_step = 0
        self.stop_requested = False
        self.paused = False
        self.pending_approval_tool = None
        self.status = AgentStatus.RUNNING

        model = model_name or settings.DEFAULT_MODEL
        self.emit("status_change", {"status": self.status.value, "goal": self.current_goal})

        self._thread = threading.Thread(
            target=self._run_loop,
            args=(self.current_goal, model, require_approval),
            daemon=True
        )
        self._thread.start()
        return True

    def stop(self):
        self.stop_requested = True
        self.paused = False
        self.status = AgentStatus.STOPPED
        self.approval_event.set()
        self.emit("status_change", {"status": self.status.value})

    def pause(self):
        if self.status == AgentStatus.RUNNING:
            self.paused = True
            self.status = AgentStatus.PAUSED
            self.emit("status_change", {"status": self.status.value})

    def resume(self):
        if self.status == AgentStatus.PAUSED:
            self.paused = False
            self.status = AgentStatus.RUNNING
            self.emit("status_change", {"status": self.status.value})

    def approve_step(self, approved: bool = True):
        """Approves or rejects a pending step when running in confirmation mode."""
        self.approval_result = approved
        self.approval_event.set()

    def _run_loop(self, goal: str, model_name: str, require_approval: bool):
        from gemini_pc.google_oauth import oauth_manager

        oauth_token = oauth_manager.get_valid_access_token() if oauth_manager.is_authenticated() else None
        api_key = settings.GEMINI_API_KEY

        if not api_key and not oauth_token:
            self.status = AgentStatus.ERROR
            self.emit("error", {"message": "No authentication configured. Please sign in with your Google One account via OAuth or set an API key in Settings."})
            self.emit("status_change", {"status": self.status.value})
            return

        try:
            if oauth_token:
                client = genai.Client(
                    api_key="oauth_bearer",
                    http_options=types.HttpOptions(headers={"Authorization": f"Bearer {oauth_token}"})
                )
            else:
                client = genai.Client(api_key=api_key)
        except Exception as e:
            self.status = AgentStatus.ERROR
            self.emit("error", {"message": f"Failed to initialize Gemini Client: {str(e)}"})
            self.emit("status_change", {"status": self.status.value})
            return

        chat_history = []
        last_action_coord = None
        sw, sh = controller.get_screen_size()

        self.emit("log", {"level": "info", "message": f"Starting autonomous task with model '{model_name}'. Display resolution: {sw}x{sh}"})

        while self.current_step < self.max_steps and not self.stop_requested:
            # Handle pause state
            while self.paused and not self.stop_requested:
                time.sleep(0.5)

            if self.stop_requested:
                break

            self.current_step += 1
            step_start_time = time.time()

            self.emit("step_start", {"step": self.current_step, "max_steps": self.max_steps})

            # 1. Capture screen
            try:
                raw_screenshot = controller.take_screenshot()
            except Exception as e:
                self.emit("error", {"message": f"Failed to capture screenshot: {e}"})
                break

            # 2. Add visual grounding grid overlay if enabled
            if settings.GRID_OVERLAY:
                processed_img = VisualGrounding.draw_coordinate_grid(
                    raw_screenshot,
                    grid_step=150,
                    last_action_coord=last_action_coord
                )
            else:
                processed_img = raw_screenshot

            jpeg_bytes, (orig_w, orig_h) = VisualGrounding.optimize_image(
                processed_img,
                max_width=settings.SCREENSHOT_MAX_WIDTH,
                quality=80
            )

            preview_b64 = VisualGrounding.to_base64_data_url(jpeg_bytes)
            self.emit("screen_update", {
                "step": self.current_step,
                "data_url": preview_b64,
                "resolution": f"{orig_w}x{orig_h}"
            })

            # 3. Construct prompt content
            # Convert JPEG bytes to Part for Gemini
            image_part = types.Part.from_bytes(
                data=jpeg_bytes,
                mime_type="image/jpeg"
            )

            step_prompt = (
                f"CURRENT GOAL: {goal}\n"
                f"STEP: {self.current_step} / {self.max_steps}\n"
                f"SCREEN RESOLUTION: {orig_w}x{orig_h}\n"
                f"Observe the desktop screenshot. Decide what to do next to make progress toward the goal.\n"
                f"Explain your reasoning and call the appropriate tool."
            )

            # Build request contents
            # We pass previous interaction context + current screenshot + prompt
            current_turn = [image_part, step_prompt]
            full_contents = chat_history + current_turn

            gen_config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=ALL_DESKTOP_FUNCTIONS,
                temperature=0.2,
            )

            self.emit("log", {"level": "info", "message": f"Consulting Gemini {model_name} (Step {self.current_step})..."})

            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=full_contents,
                    config=gen_config,
                )
            except Exception as e:
                err_msg = str(e)
                # Handle model name fallback if specific experimental preview name differs
                if "404" in err_msg or "not found" in err_msg.lower():
                    fallback_model = "gemini-2.5-flash"
                    self.emit("log", {"level": "warning", "message": f"Model '{model_name}' not available on current endpoint, trying fallback '{fallback_model}'..."})
                    try:
                        response = client.models.generate_content(
                            model=fallback_model,
                            contents=full_contents,
                            config=gen_config,
                        )
                        model_name = fallback_model
                    except Exception as e2:
                        self.emit("error", {"message": f"Gemini API error on step {self.current_step}: {str(e2)}"})
                        self.status = AgentStatus.ERROR
                        break
                else:
                    self.emit("error", {"message": f"Gemini API error on step {self.current_step}: {err_msg}"})
                    self.status = AgentStatus.ERROR
                    break

            # Extract reasoning text and function calls
            thought_text = ""
            function_calls = []

            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if part.text:
                            thought_text += part.text + "\n"
                        if part.function_call:
                            function_calls.append(part.function_call)

            thought_text = thought_text.strip()
            self.emit("reasoning", {
                "step": self.current_step,
                "thought": thought_text or "(No written reasoning, proceeding with tool execution)",
            })

            # If Gemini didn't make any function calls, check if task is completed
            if not function_calls:
                self.emit("log", {"level": "info", "message": "No action proposed by model."})
                if "completed" in thought_text.lower() or "finished" in thought_text.lower():
                    self.status = AgentStatus.FINISHED
                    self.emit("task_completed", {"summary": thought_text, "success": True})
                    break
                else:
                    # Give it another chance or small wait
                    time.sleep(1.0)
                    continue

            # Process first function call
            fn_call = function_calls[0]
            fn_name = fn_call.name
            fn_args = dict(fn_call.args) if fn_call.args else {}

            self.emit("action_proposed", {
                "step": self.current_step,
                "tool": fn_name,
                "arguments": fn_args,
            })

            # Check if this is finish_task
            if fn_name == "finish_task":
                summary = fn_args.get("summary", "Task concluded.")
                success = fn_args.get("success", True)
                self.status = AgentStatus.FINISHED
                self.emit("task_completed", {"summary": summary, "success": success})
                break

            # If step-by-step confirmation is enabled
            if require_approval:
                self.status = AgentStatus.AWAITING_APPROVAL
                self.pending_approval_tool = {"tool": fn_name, "args": fn_args}
                self.approval_event.clear()
                self.emit("status_change", {"status": self.status.value, "pending": self.pending_approval_tool})

                # Wait for user approval
                self.approval_event.wait()
                if self.stop_requested:
                    break

                if not self.approval_result:
                    self.emit("log", {"level": "warning", "message": f"Action '{fn_name}' was skipped/rejected by user."})
                    self.status = AgentStatus.RUNNING
                    self.emit("status_change", {"status": self.status.value})
                    time.sleep(0.5)
                    continue

                self.status = AgentStatus.RUNNING
                self.emit("status_change", {"status": self.status.value})

            # Execute tool call
            tool_fn = TOOL_DISPATCHER.get(fn_name)
            tool_output = ""
            if not tool_fn:
                tool_output = f"Error: Tool '{fn_name}' not found."
            else:
                try:
                    # Update coordinate tracking for visual indicator
                    if "x" in fn_args and "y" in fn_args:
                        last_action_coord = (int(fn_args["x"]), int(fn_args["y"]))

                    self.emit("action_executing", {"tool": fn_name, "args": fn_args})
                    tool_output = str(tool_fn(**fn_args))
                except Exception as ex:
                    tool_output = f"Execution error in {fn_name}: {str(ex)}"
                    logger.error(f"Tool execution failed: {ex}")

            self.emit("action_result", {
                "step": self.current_step,
                "tool": fn_name,
                "output": tool_output,
                "duration": round(time.time() - step_start_time, 2),
            })

            # Append to history summary for context persistence
            chat_history.append(
                f"[Step {self.current_step}] Action: {fn_name}({fn_args}) -> Result: {tool_output}"
            )
            # Keep history manageable
            if len(chat_history) > 6:
                chat_history = chat_history[-6:]

            # Action delay
            time.sleep(settings.ACTION_DELAY_SEC)

        if self.current_step >= self.max_steps and self.status == AgentStatus.RUNNING:
            self.status = AgentStatus.FINISHED
            self.emit("task_completed", {
                "summary": f"Reached maximum configured steps ({self.max_steps}).",
                "success": False
            })

        if self.status != AgentStatus.ERROR and self.status != AgentStatus.FINISHED:
            self.status = AgentStatus.IDLE

        self.emit("status_change", {"status": self.status.value})

# Global Agent Instance
agent = GeminiAgent()
