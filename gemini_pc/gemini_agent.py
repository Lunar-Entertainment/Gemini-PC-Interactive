import os
import re
import json
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
- All screen coordinates (x, y) use a 0 to 1000 normalized scale:
  - x: 0 = leftmost edge, 1000 = rightmost edge. Center x is 500.
  - y: 0 = topmost edge, 1000 = bottommost edge. Center y is 500.
  - (0, 0) is top-left, (1000, 1000) is bottom-right.
- Reference ruler tick badges labeled from 0 to 1000 run along ALL 4 BORDERS (Top, Bottom, Left, and Right), with tick marks every 25 units.
- Golden yellow lines mark the center axes at x=500 and y=500.
- Small landmark pills show local coordinates across quadrants (e.g. [250,250], [750,250], [500,500], [250,750], [750,750], [500,940]).

SYNTHETIC MOUSE CURSOR & VISUAL GROUNDING:
- The actual current mouse cursor is drawn directly onto the screenshot as a vibrant cyan crosshair badge labeled `CURSOR: [x, y]`.
- You can move or click relative to this position using `move_by(dx, dy)` or `click_by(dx, dy)`.
- If a red bullseye marker labeled "LAST CLICK: [x=..., y=...]" is visible, it shows your previous action's exact location for closed-loop visual feedback.

TWO-STAGE "CROP & ZOOM" FOR SUB-PIXEL ACCURACY:
- For small desktop elements (calculator buttons, toolbar icons, checkboxes, close buttons, browser tabs, menus, table cells):
  Call `precision_click(x, y, target_description)`.
  - Stage 1: Provide the approximate area [x, y] on the 0-1000 scale and a concise description of the target (e.g. `precision_click(x=380, y=620, target_description="multiply key")`).
  - Stage 2: The system automatically crops a 300x300px box around that area, overlays a fine 0-100 micro-grid, and calculates sub-pixel accuracy before executing the click.

ACCURACY & TARGETING RULES:
1. Dead-Center Targeting & Border Rulers:
   - Locate the visual boundaries of your target element.
   - Use the nearest border ruler (e.g. bottom border for taskbar icons at y=960-990) and tick marks to find the center [x, y].
   - For small or dense targets, ALWAYS prefer `precision_click(x, y, target_description)`.
2. Form Input & Focus:
   - Before typing into any text input or search bar, you MUST click inside it first to ensure it has focus.
   - Set press_enter=True when submitting a search query or command.
3. Window Management & Switching:
   - When asked to switch to, open, or click an application window that is already open, ALWAYS prefer calling `focus_window(window_title)` (e.g. `focus_window("Minecraft")` or `focus_window("Calculator")`).
4. 3D Games & Camera Rotation (Minecraft, etc.):
   - Once a 3D game window is focused and active:
     - To look around or turn the camera: Use `game_look(direction="left"|"right"|"up"|"down", degrees=45)` or `mouse_move_relative(dx, dy)`. Never use `move_mouse` for 3D games!
     - To walk or move: Use `hold_key(key="w", duration=1.5)` (or "a", "s", "d").
     - To sneak/avoid falling in Minecraft: Use `hold_key(key="shift", duration=...)`.
     - To jump: Use `hold_key(key="space", duration=0.3)`.
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
        from gemini_pc.rate_limiter import rate_limiter
        import re

        oauth_profile = oauth_manager.get_user_profile() if oauth_manager.is_authenticated() else {}
        user_display = oauth_profile.get("name") or oauth_profile.get("email") or ""

        client = None
        if settings.GEMINI_API_KEY:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            auth_type = "API Key (15 RPM Free Tier)"
        elif oauth_manager.is_authenticated():
            client = oauth_manager.get_client()
            auth_type = f"Google One ({user_display or 'Active'})"
        else:
            self.status = AgentStatus.ERROR
            self.emit("error", {
                "message": "No API key configured. Please enter your Google Gemini API key in Settings or .env to start.",
                "open_settings": True
            })
            self.emit("status_change", {"status": self.status.value})
            return

        last_action_coord = None
        last_fn_name: Optional[str] = None
        last_tool_output: Optional[str] = None
        sw, sh = controller.get_screen_size()

        active_model = model_name or settings.DEFAULT_MODEL
        RELIABLE_FALLBACK_MODELS = [
            "gemini-3.6-flash",
            "gemini-flash-latest",
            "gemini-2.0-flash",
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

        def send_turn(current_chat, current_model, fn_resp_part, base_payload):
            nonlocal client
            models_to_try = [current_model] + [m for m in RELIABLE_FALLBACK_MODELS if m != current_model]
            last_err = None

            # 1. Enforce 15 RPM safety with 0-latency instant burst activation
            waited = rate_limiter.wait_for_slot()
            if waited > 0.05:
                self.emit("log", {
                    "level": "info",
                    "message": f"Rate-pacing: waited {waited:.2f}s to respect 15 RPM free tier..."
                })

            for candidate in models_to_try:
                # Ensure chat session exists with candidate model
                if not current_chat or getattr(current_chat, "_model", None) != candidate:
                    saved_history = None
                    if current_chat:
                        try:
                            saved_history = prune_chat_history(current_chat.get_history(), keep_recent_images=1)
                        except Exception:
                            pass
                    current_chat = client.chats.create(
                        model=candidate,
                        config=gen_config,
                        history=saved_history,
                    )
                    current_chat._model = candidate

                # Build payload safely:
                # Check if preceding turn was a model function call
                expecting_fn_resp = False
                try:
                    hist = current_chat.get_history()
                    if hist and hist[-1].role == "model":
                        expecting_fn_resp = any(
                            getattr(p, "function_call", None) is not None
                            for p in (hist[-1].parts or [])
                        )
                except Exception:
                    pass

                if expecting_fn_resp and fn_resp_part is not None:
                    payload = [fn_resp_part] + base_payload
                else:
                    payload = base_payload

                # Prune older screenshots on active chat to keep tokens minimal and responses sub-2s
                try:
                    current_chat._curated_history = prune_chat_history(
                        current_chat.get_history(), keep_recent_images=1
                    )
                except Exception:
                    pass

                try:
                    resp = current_chat.send_message(payload)
                    return current_chat, resp, candidate
                except Exception as ex:
                    last_err = ex
                    err_msg = str(ex).lower()

                    # Case A: Function response turn mismatch (400 INVALID_ARGUMENT)
                    if "function response" in err_msg or "function call turn" in err_msg:
                        self.emit("log", {
                            "level": "warning",
                            "message": "Function turn mismatch detected. Resetting chat turn and retrying..."
                        })
                        current_chat = None
                        fn_resp_part = None
                        continue

                    # Case B: Rate Limit (429 RESOURCE_EXHAUSTED)
                    if "429" in err_msg or "resource_exhausted" in err_msg or "quota" in err_msg:
                        delay_to_wait = 20.0
                        m_delay = re.search(r"retry\s*(?:delay|in)[\'\":\s]+([0-9\.]+)", err_msg)
                        if m_delay:
                            try:
                                delay_to_wait = min(max(float(m_delay.group(1)), 5.0), 60.0)
                            except Exception:
                                pass

                        rate_limiter.record_429(delay_to_wait)
                        self.emit("log", {
                            "level": "warning",
                            "message": f"Quota limit reached (429). Waiting {delay_to_wait:.1f}s for 15 RPM reset..."
                        })
                        time.sleep(delay_to_wait)
                        current_chat = None
                        continue

                    # Case C: 503 High Demand / Unavailable
                    if "503" in err_msg or "unavailable" in err_msg:
                        self.emit("log", {
                            "level": "warning",
                            "message": f"Model '{candidate}' high demand (503). Retrying with fallback model in 1.5s..."
                        })
                        time.sleep(1.5)
                        current_chat = None
                        continue

                    # Case D: 404 Model Not Found
                    if "404" in err_msg or "not found" in err_msg:
                        self.emit("log", {
                            "level": "warning",
                            "message": f"Model '{candidate}' not found. Trying next fallback model..."
                        })
                        current_chat = None
                        continue

                    raise ex

            raise last_err or RuntimeError("Failed to communicate with Gemini API.")

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
            # 1. Capture screen & current mouse cursor position
            try:
                raw_screenshot = controller.take_screenshot()
                current_cursor = controller.get_mouse_position()
            except Exception as e:
                self.emit("error", {"message": f"Failed to capture screenshot: {e}"})
                break

            # 2. Add visual grounding grid overlay & synthetic cursor crosshair if enabled
            if settings.GRID_OVERLAY:
                processed_img = VisualGrounding.draw_coordinate_grid(
                    raw_screenshot,
                    grid_step=100,
                    last_action_coord=last_action_coord,
                    current_mouse_coord=current_cursor,
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

            # 3. Construct prompt content with open windows and cursor context
            image_part = types.Part.from_bytes(
                data=jpeg_bytes,
                mime_type="image/jpeg"
            )

            open_wins = []
            try:
                for w in controller.list_windows():
                    t = w.get("title", "").strip()
                    if t and len(t) > 2 and not t.startswith("NVIDIA") and not t.startswith("Windows indata"):
                        open_wins.append(t)
            except Exception:
                pass

            cur_nx = int(round(current_cursor[0] / float(orig_w) * 1000.0)) if orig_w > 0 else 0
            cur_ny = int(round(current_cursor[1] / float(orig_h) * 1000.0)) if orig_h > 0 else 0

            step_prompt = (
                f"CURRENT GOAL: {goal}\n"
                f"STEP: {self.current_step} / {self.max_steps}\n"
                f"DISPLAY RESOLUTION: {orig_w}x{orig_h}\n"
                f"CURRENT CURSOR POSITION: ({current_cursor[0]}, {current_cursor[1]}) [Normalized: x={cur_nx}, y={cur_ny}] (marked with cyan crosshairs 'CURSOR: [x,y]' on screen)\n"
            )
            if open_wins:
                step_prompt += f"OPEN APPLICATION WINDOWS: {', '.join(open_wins[:6])}\n"
            if last_fn_name is not None:
                step_prompt += f"PREVIOUS ACTION EXECUTED: {last_fn_name} -> Output: {last_tool_output or 'Done'}\n"

            step_prompt += (
                "Observe the desktop screenshot. Coordinates use a 0-1000 normalized scale with border rulers and ticks every 25 units.\n"
                "- SUB-PIXEL PRECISION: For small buttons, icons, checkboxes, or tabs, call precision_click(x, y, target_description) for automatic Two-Stage Crop & Zoom!\n"
                "- RELATIVE MOVEMENTS: Use move_by(dx, dy) or click_by(dx, dy) to nudge or click relative to the visible CURSOR.\n"
                "- To switch to/focus any open application, call focus_window(window_title).\n"
                "- FOR 3D GAMES (Minecraft, etc.): To look around, use game_look(direction, degrees) or mouse_move_relative(dx, dy). Never use move_mouse for 3D camera control."
            )

            base_payload = [image_part, step_prompt]

            fn_resp_part = None
            if last_fn_name is not None:
                fn_resp_part = types.Part.from_function_response(
                    name=last_fn_name,
                    response={"output": last_tool_output or "Executed"}
                )

            self.emit("log", {"level": "info", "message": f"Consulting Gemini {active_model} (Step {self.current_step})..."})

            try:
                chat, response, used_model = send_turn(chat, active_model, fn_resp_part, base_payload)
                if used_model != active_model:
                    active_model = used_model
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "resource_exhausted" in err_str.lower():
                    friendly_msg = (
                        "Quota Exceeded (429 RESOURCE_EXHAUSTED): Free-tier 15 RPM limit reached. "
                        "Please wait a moment for the quota window to reset."
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

            # Compute predicted coordinates for visual click echo
            pred_x, pred_y = None, None
            if "x" in fn_args and "y" in fn_args:
                try:
                    pred_x, pred_y = adjust_coords(fn_args["x"], fn_args["y"])
                except Exception:
                    pass
            elif "from_x" in fn_args and "from_y" in fn_args:
                try:
                    pred_x, pred_y = adjust_coords(fn_args["from_x"], fn_args["from_y"])
                except Exception:
                    pass
            elif fn_name in ("move_by", "click_by"):
                try:
                    cx, cy = controller.get_mouse_position()
                    pred_x = max(0, min(cx + int(round(float(fn_args.get("dx", 0)))), orig_w - 1))
                    pred_y = max(0, min(cy + int(round(float(fn_args.get("dy", 0)))), orig_h - 1))
                except Exception:
                    pass

            self.emit("action_proposed", {
                "step": self.current_step,
                "tool": fn_name,
                "arguments": fn_args,
                "predicted_x": pred_x,
                "predicted_y": pred_y,
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
                self.pending_approval_tool = {
                    "tool": fn_name,
                    "args": fn_args,
                    "predicted_x": pred_x,
                    "predicted_y": pred_y,
                }
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

            # Coordinate adjustments before dispatch & Stage 2 Execution
            if fn_name in ("mouse_click", "mouse_double_click", "move_mouse", "mouse_right_click"):
                if "x" in fn_args and "y" in fn_args:
                    fn_args["x"], fn_args["y"] = adjust_coords(fn_args["x"], fn_args["y"])
                    last_action_coord = (int(fn_args["x"]), int(fn_args["y"]))
            elif fn_name == "precision_click":
                # Two-Stage Crop & Zoom execution:
                approx_x, approx_y = adjust_coords(fn_args.get("x", 500), fn_args.get("y", 500))
                target_desc = str(fn_args.get("target_description", "target element"))
                btn = fn_args.get("button", "left")
                clicks = int(fn_args.get("clicks", 1))

                self.emit("log", {
                    "level": "info",
                    "message": f"Stage 2 (Crop & Zoom): Pinpointing '{target_desc}' with 0-100 microgrid near ({approx_x}, {approx_y})..."
                })

                try:
                    crop_base = controller.take_screenshot()
                    zoom_img, crop_bounds = VisualGrounding.create_zoom_crop(
                        crop_base, approx_x, approx_y, box_size=300
                    )
                    zoom_opt = VisualGrounding.optimize_image(zoom_img, max_width=300, quality=80)
                    zoom_b64 = VisualGrounding.to_base64_data_url(zoom_opt.bytes)

                    self.emit("zoom_crop_preview", {
                        "step": self.current_step,
                        "data_url": zoom_b64,
                        "target": target_desc,
                        "center": [approx_x, approx_y],
                        "bounds": crop_bounds,
                    })

                    stage2_prompt = (
                        f"You are performing Stage 2 Crop & Zoom sub-pixel targeting for: '{target_desc}'.\n"
                        f"This is a 300x300px zoomed crop around screen position ({approx_x}, {approx_y}) overlaid with a fine 0-100 micro-grid.\n"
                        f"- u: 0 = left border, 100 = right border. Amber vertical line is u=50.\n"
                        f"- v: 0 = top border, 100 = bottom border. Amber horizontal line is v=50.\n"
                        f"Locate the exact center of the target '{target_desc}'.\n"
                        f"Respond strictly in JSON format: {{\"u\": <0-100 integer>, \"v\": <0-100 integer>}}\n"
                        f"Example: {{\"u\": 48, \"v\": 52}}"
                    )

                    stage2_img_part = types.Part.from_bytes(data=zoom_opt.bytes, mime_type="image/jpeg")
                    rate_limiter.wait_for_slot()
                    stage2_resp = client.models.generate_content(
                        model=active_model,
                        contents=[stage2_img_part, stage2_prompt],
                        config=types.GenerateContentConfig(
                            temperature=0.0,
                            response_mime_type="application/json",
                        )
                    )
                    stage2_text = stage2_resp.text or "{}"
                    try:
                        coords = json.loads(stage2_text)
                        u = float(coords.get("u", 50))
                        v = float(coords.get("v", 50))
                    except Exception:
                        m_u = re.search(r'"u"\s*:\s*([0-9\.]+)', stage2_text)
                        m_v = re.search(r'"v"\s*:\s*([0-9\.]+)', stage2_text)
                        u = float(m_u.group(1)) if m_u else 50.0
                        v = float(m_v.group(1)) if m_v else 50.0

                    final_x, final_y = VisualGrounding.microgrid_to_screen_coords(u, v, crop_bounds)
                    fn_args["x"] = final_x
                    fn_args["y"] = final_y
                    last_action_coord = (final_x, final_y)
                    self.emit("log", {
                        "level": "info",
                        "message": f"Stage 2 resolved '{target_desc}' at micro-grid [u={u:.1f}, v={v:.1f}] -> Screen ({final_x}, {final_y})"
                    })
                except Exception as ex:
                    logger.warning(f"Stage 2 crop & zoom fallback: {ex}")
                    fn_args["x"] = approx_x
                    fn_args["y"] = approx_y
                    last_action_coord = (approx_x, approx_y)

            elif fn_name == "drag_and_drop":
                if "from_x" in fn_args and "from_y" in fn_args:
                    fn_args["from_x"], fn_args["from_y"] = adjust_coords(fn_args["from_x"], fn_args["from_y"])
                if "to_x" in fn_args and "to_y" in fn_args:
                    fn_args["to_x"], fn_args["to_y"] = adjust_coords(fn_args["to_x"], fn_args["to_y"])
                    last_action_coord = (int(fn_args["to_x"]), int(fn_args["to_y"]))
            elif fn_name in ("move_by", "click_by"):
                # Track mouse coordinate after relative action
                pass
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
