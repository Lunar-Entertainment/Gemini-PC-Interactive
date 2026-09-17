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


SYSTEM_INSTRUCTION = """You are Gemini PC Interactive, an autonomous AI desktop agent capable of seeing the user's computer screen and controlling the PC with high precision and speed.

COORDINATE SYSTEM (0 - 1000 NORMALIZED SCALE):
- All screen coordinates (x, y) MUST use a 0 to 1000 normalized scale:
  - x: 0 = leftmost edge, 1000 = rightmost edge. Center x is 500.
  - y: 0 = topmost edge, 1000 = bottommost edge. Center y is 500.
  - (0, 0) is top-left, (1000, 1000) is bottom-right.
- The screenshot displays reference ruler tick badges labeled from 0 to 1000 along the top and left borders, with subtle guide lines every 100 units.
- ALL coordinates you pass to tools (mouse_click, mouse_double_click, move_mouse, mouse_right_click, drag_and_drop, scroll_screen) MUST use this 0-1000 scale.
- The system automatically translates your 0-1000 coordinates to physical screen pixels with sub-pixel precision.

ACCURACY & TARGETING RULES:
1. Dead-Center Targeting:
   - Carefully locate the visual boundaries of your target element (button, icon, input field, tab, menu).
   - Estimate the exact center point (x, y) on the 0-1000 scale using the nearest 100-unit rulers and grid lines.
2. Form Input & Focus:
   - Before typing into any text input or search bar, you MUST click inside it first to ensure it has focus.
   - Set press_enter=True when submitting a search query or command.
3. Closed-Loop Visual Feedback:
   - If a red bullseye marker is visible labeled "LAST CLICK: [x=..., y=...]", it shows your previous click's exact location.
   - Use this feedback to see if the element was clicked or if your click was slightly off, and immediately calibrate your next action.
4. Step-by-Step Reasoning:
   In your reasoning, state:
   - Target: [Element name]
   - Estimated position: [x, y] (0-1000 scale)
   - Action: [Tool to execute]
   Then immediately call the tool.
5. Completion:
   - When the objective is achieved, call `finish_task(summary, success=True)` immediately.
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

        oauth_profile = oauth_manager.get_user_profile() if oauth_manager.is_authenticated() else {}
        user_display = oauth_profile.get("name") or oauth_profile.get("email") or "User"

        client = None
        auth_type = f"Google One ({user_display})"

        if not oauth_manager.is_authenticated():
            user_email = oauth_profile.get("email") or settings.GOOGLE_ACCOUNT_EMAIL
            email_info = f" ({user_email})" if user_email else ""
            self.status = AgentStatus.ERROR
            self.emit("error", {
                "message": (
                    f"Please sign in with your Google One account{email_info} in Settings to connect Gemini PC Interactive."
                ),
                "open_settings": True
            })
            self.emit("status_change", {"status": self.status.value})
            return

        # Initialize the GenAI Client transparently for Google One account
        try:
            transport_key = settings.INTERNAL_TRANSPORT_KEY
            client = genai.Client(api_key=transport_key)
        except Exception as e:
            logger.error(f"Failed to initialize Gemini Client: {e}")
            self.status = AgentStatus.ERROR
            self.emit("error", {"message": f"Google One authentication failed: {e}"})
            self.emit("status_change", {"status": self.status.value})
            return

        last_action_coord = None
        last_fn_name: Optional[str] = None
        last_tool_output: Optional[str] = None
        sw, sh = controller.get_screen_size()

        active_model = model_name or settings.DEFAULT_MODEL
        RELIABLE_FALLBACK_MODELS = [
            "gemini-3.8-flash",
            "gemini-3.6-flash",
            "gemini-flash-latest",
            "gemini-flash-lite-latest"
        ]

        self.emit("log", {
            "level": "info",
            "message": f"Starting autonomous task with model '{active_model}' (Auth: {auth_type}). Display resolution: {sw}x{sh}"
        })

        gen_config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=ALL_DESKTOP_FUNCTIONS,
            temperature=0.1,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        chat = None
        try:
            chat = client.chats.create(
                model=active_model,
                config=gen_config,
            )
        except Exception as e:
            logger.warning(f"Initial chat creation with '{active_model}' failed: {e}. Will try fallback.")

        def prune_chat_history(history: List[types.Content], keep_recent_images: int = 1) -> List[types.Content]:
            images_seen = 0
            pruned = []
            for content in reversed(history or []):
                new_parts = []
                for part in reversed(content.parts or []):
                    if getattr(part, "inline_data", None):
                        images_seen += 1
                        if images_seen > keep_recent_images:
                            new_parts.append(types.Part.from_text(text="[Prior screenshot state]"))
                        else:
                            new_parts.append(part)
                    else:
                        new_parts.append(part)
                new_parts.reverse()
                pruned.append(types.Content(role=content.role, parts=new_parts))
            pruned.reverse()
            return pruned

        def send_with_fallback(current_chat, current_model, msg_payload):
            models_to_try = [current_model] + [m for m in RELIABLE_FALLBACK_MODELS if m != current_model]
            last_err = None
            import re

            for round_idx in range(2):
                for candidate in models_to_try:
                    try:
                        if not current_chat or getattr(current_chat, "_model", None) != candidate:
                            hist = current_chat.get_history() if current_chat else None
                            if hist:
                                hist = prune_chat_history(hist)
                            current_chat = client.chats.create(
                                model=candidate,
                                config=gen_config,
                                history=hist,
                            )
                        # Periodic history pruning on active chat to protect token quota
                        if current_chat:
                            current_chat._curated_history = prune_chat_history(current_chat.get_history(), keep_recent_images=1)
                        resp = current_chat.send_message(msg_payload)
                        return current_chat, resp, candidate
                    except Exception as ex:
                        last_err = ex
                        err_msg = str(ex).lower()

                        delay_to_wait = 2.0
                        m_delay = re.search(r"retry\s*(?:delay|in)[\'\":\s]+([0-9\.]+)", err_msg)
                        if m_delay:
                            try:
                                delay_to_wait = min(max(float(m_delay.group(1)), 1.5), 8.0)
                            except Exception:
                                pass

                        if (
                            "503" in err_msg
                            or "unavailable" in err_msg
                            or "capacity" in err_msg
                            or "404" in err_msg
                            or "not found" in err_msg
                            or "429" in err_msg
                            or "resource_exhausted" in err_msg
                        ):
                            is_zero_quota = "limit: 0" in err_msg
                            sleep_duration = 0 if is_zero_quota else delay_to_wait
                            self.emit("log", {
                                "level": "warning",
                                "message": f"Model '{candidate}' hit capacity/quota limit ({str(ex)[:60]}...). Switching to fallback model..."
                            })
                            if sleep_duration > 0:
                                time.sleep(sleep_duration)
                            continue
                        raise ex
            raise last_err

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
                    grid_step=100,
                    last_action_coord=last_action_coord
                )
            else:
                processed_img = raw_screenshot

            opt_img = VisualGrounding.optimize_image(
                processed_img,
                max_width=settings.SCREENSHOT_MAX_WIDTH,
                quality=80
            )
            jpeg_bytes = opt_img.bytes
            orig_w, orig_h = opt_img.orig_size
            sent_w, sent_h = opt_img.sent_size

            preview_b64 = VisualGrounding.to_base64_data_url(jpeg_bytes)
            self.emit("screen_update", {
                "step": self.current_step,
                "data_url": preview_b64,
                "resolution": f"{orig_w}x{orig_h}"
            })

            # 3. Construct prompt content
            image_part = types.Part.from_bytes(
                data=jpeg_bytes,
                mime_type="image/jpeg"
            )

            step_prompt = (
                f"CURRENT GOAL: {goal}\n"
                f"STEP: {self.current_step} / {self.max_steps}\n"
                f"DISPLAY RESOLUTION: {orig_w}x{orig_h}\n"
                f"Observe the desktop screenshot. Coordinates use a 0-1000 normalized scale (rulers along top and left borders).\n"
                f"Identify the target element, state its center coordinates [x, y] (0-1000 scale) in your reasoning, and execute the tool."
            )

            turn_payload = []
            if last_fn_name is not None:
                fn_resp_part = types.Part.from_function_response(
                    name=last_fn_name,
                    response={"output": last_tool_output or "Executed"}
                )
                turn_payload.append(fn_resp_part)

            turn_payload.append(image_part)
            turn_payload.append(step_prompt)

            self.emit("log", {"level": "info", "message": f"Consulting Gemini {active_model} via Chat.send_message (Step {self.current_step})..."})

            try:
                chat, response, used_model = send_with_fallback(chat, active_model, turn_payload)
                if used_model != active_model:
                    active_model = used_model
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "resource_exhausted" in err_str.lower():
                    friendly_msg = (
                        f"Quota Exceeded (429 RESOURCE_EXHAUSTED): Google AI Studio Free Tier limits were reached. "
                        f"Note: Google One AI Pro consumer subscriptions cover web Gemini (gemini.google.com) but do not grant "
                        f"developer API quota. To unlock higher limits (or use Gemini Pro), generate a free API key at "
                        f"https://aistudio.google.com/apikey and add it to your .env or Settings."
                    )
                    self.emit("error", {"message": friendly_msg})
                else:
                    self.emit("error", {"message": f"Gemini API error on step {self.current_step}: {err_str}"})
                self.status = AgentStatus.ERROR
                break

            # Extract reasoning text and function calls
            thought_text = ""
            function_calls = []

            if getattr(response, "function_calls", None):
                function_calls = list(response.function_calls)

            for candidate in getattr(response, "candidates", []) or []:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if part.text:
                            thought_text += part.text + "\n"
                        if part.function_call and not function_calls:
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
                    time.sleep(1.0)
                    last_fn_name = None
                    last_tool_output = None
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
                    last_fn_name = fn_name
                    last_tool_output = "Action skipped by user request."
                    continue

                self.status = AgentStatus.RUNNING
                self.emit("status_change", {"status": self.status.value})

            # Automatic coordinate translation & scaling between sent image, 0-1000 scale, and physical screen
            scale_x = orig_w / float(sent_w) if sent_w > 0 else 1.0
            scale_y = orig_h / float(sent_h) if sent_h > 0 else 1.0

            def adjust_coords(raw_x, raw_y):
                try:
                    rx = float(raw_x)
                    ry = float(raw_y)
                    # 1. Normalized float [0.0, 1.0]
                    if 0.0 <= rx <= 1.0 and 0.0 <= ry <= 1.0 and orig_w > 1 and orig_h > 1:
                        px = int(round(rx * orig_w))
                        py = int(round(ry * orig_h))
                        return max(0, min(px, orig_w - 1)), max(0, min(py, orig_h - 1))

                    # 2. Standard 0-1000 normalized scale (native Gemini vision & visual grounding grid)
                    if 0.0 <= rx <= 1000.0 and 0.0 <= ry <= 1000.0:
                        px = int(round((rx / 1000.0) * orig_w))
                        py = int(round((ry / 1000.0) * orig_h))
                        return max(0, min(px, orig_w - 1)), max(0, min(py, orig_h - 1))

                    # 3. Raw physical screen pixels (>1000)
                    if abs(scale_x - 1.0) > 0.001 or abs(scale_y - 1.0) > 0.001:
                        px = int(round(rx * scale_x))
                        py = int(round(ry * scale_y))
                        return max(0, min(px, orig_w - 1)), max(0, min(py, orig_h - 1))

                    px = int(round(rx))
                    py = int(round(ry))
                    return max(0, min(px, orig_w - 1)), max(0, min(py, orig_h - 1))
                except Exception:
                    return raw_x, raw_y

            if fn_name in ("mouse_click", "mouse_double_click", "move_mouse", "mouse_right_click"):
                if "x" in fn_args and "y" in fn_args:
                    fn_args["x"], fn_args["y"] = adjust_coords(fn_args["x"], fn_args["y"])
                    last_action_coord = (int(fn_args["x"]), int(fn_args["y"]))
            elif fn_name == "drag_and_drop":
                if "from_x" in fn_args and "from_y" in fn_args:
                    fn_args["from_x"], fn_args["from_y"] = adjust_coords(fn_args["from_x"], fn_args["from_y"])
                if "to_x" in fn_args and "to_y" in fn_args:
                    fn_args["to_x"], fn_args["to_y"] = adjust_coords(fn_args["to_x"], fn_args["to_y"])
                    last_action_coord = (int(fn_args["to_x"]), int(fn_args["to_y"]))
            elif fn_name == "scroll_screen":
                if fn_args.get("x", 0) > 0 or fn_args.get("y", 0) > 0:
                    fn_args["x"], fn_args["y"] = adjust_coords(fn_args.get("x", 0), fn_args.get("y", 0))

            # Execute tool call
            tool_fn = TOOL_DISPATCHER.get(fn_name)
            tool_output = ""
            if not tool_fn:
                tool_output = f"Error: Tool '{fn_name}' not found."
            else:
                try:
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

            last_fn_name = fn_name
            last_tool_output = tool_output

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
