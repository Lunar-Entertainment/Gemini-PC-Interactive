import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from gemini_pc.config import settings, BASE_DIR
from gemini_pc.pc_controller import controller
from gemini_pc.gemini_agent import agent, AgentStatus
from gemini_pc.visual_grounding import VisualGrounding

app = FastAPI(title="Gemini PC Interactive", version="1.0.0")

WEB_DIR = BASE_DIR / "web"

# Connected WebSocket clients
active_connections: List[WebSocket] = []
main_loop: asyncio.AbstractEventLoop = None

class GoalRequest(BaseModel):
    goal: str
    model: str = "gemini-2.5-flash"
    require_approval: bool = False

class ApiKeyRequest(BaseModel):
    api_key: str

class ManualActionRequest(BaseModel):
    action: str
    params: Dict[str, Any] = {}

def broadcast_sync(payload: Dict[str, Any]):
    """Called from agent background threads to broadcast messages over WebSockets."""
    global main_loop
    if not active_connections or not main_loop:
        return
    msg = json.dumps(payload)
    for ws in list(active_connections):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(msg), main_loop)
        except Exception:
            pass

# Connect agent event emitter to WebSocket broadcast
agent.register_callback(broadcast_sync)

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()

@app.get("/api/status")
async def get_status():
    sys_info = controller.get_system_info()
    return {
        "status": agent.status.value,
        "current_goal": agent.current_goal,
        "current_step": agent.current_step,
        "max_steps": agent.max_steps,
        "has_api_key": bool(settings.GEMINI_API_KEY),
        "default_model": settings.DEFAULT_MODEL,
        "system_info": sys_info,
    }

@app.post("/api/api-key")
async def set_api_key(req: ApiKeyRequest):
    settings.update_api_key(req.api_key)
    return {"success": True, "has_api_key": bool(settings.GEMINI_API_KEY)}

@app.get("/api/screenshot")
async def get_screenshot(grid: bool = False):
    img = controller.take_screenshot()
    if grid or settings.GRID_OVERLAY:
        img = VisualGrounding.draw_coordinate_grid(img, grid_step=150)
    jpeg_bytes, _ = VisualGrounding.optimize_image(img, max_width=1600, quality=85)
    return Response(content=jpeg_bytes, media_type="image/jpeg")

@app.post("/api/start")
async def start_task(req: GoalRequest):
    if not req.goal.strip():
        raise HTTPException(status_code=400, detail="Goal cannot be empty.")
    success = agent.start_goal(
        goal=req.goal,
        model_name=req.model,
        require_approval=req.require_approval
    )
    if not success:
        raise HTTPException(status_code=409, detail="An agent task is already running.")
    return {"success": True, "goal": req.goal}

@app.post("/api/stop")
async def stop_task():
    agent.stop()
    return {"success": True, "status": agent.status.value}

@app.post("/api/pause")
async def pause_task():
    agent.pause()
    return {"success": True, "status": agent.status.value}

@app.post("/api/resume")
async def resume_task():
    agent.resume()
    return {"success": True, "status": agent.status.value}

@app.post("/api/approve")
async def approve_step(approved: bool = Body(..., embed=True)):
    agent.approve_step(approved=approved)
    return {"success": True}

@app.post("/api/manual-action")
async def manual_action(req: ManualActionRequest):
    action = req.action
    params = req.params
    output = ""

    if action == "click":
        controller.mouse_click(x=params.get("x"), y=params.get("y"), button=params.get("button", "left"))
        output = f"Clicked at ({params.get('x')}, {params.get('y')})"
    elif action == "type":
        controller.type_text(params.get("text", ""), press_enter=params.get("enter", False))
        output = f"Typed '{params.get('text')}'"
    elif action == "press":
        controller.press_key(params.get("key", "enter"))
        output = f"Pressed '{params.get('key')}'"
    elif action == "hotkey":
        controller.hotkey(params.get("keys", "ctrl+c"))
        output = f"Hotkey '{params.get('keys')}'"
    elif action == "open":
        output = controller.open_application(params.get("target", "notepad"))
    elif action == "command":
        res = controller.run_command(params.get("command", "dir"))
        output = res.get("stdout") or res.get("stderr") or "Done"
    else:
        output = f"Unknown action '{action}'"

    return {"success": True, "output": output}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)

    # Send initial state and screenshot
    try:
        sys_info = controller.get_system_info()
        await websocket.send_text(json.dumps({
            "type": "init",
            "timestamp": 0,
            "data": {
                "status": agent.status.value,
                "goal": agent.current_goal,
                "step": agent.current_step,
                "max_steps": agent.max_steps,
                "has_api_key": bool(settings.GEMINI_API_KEY),
                "system_info": sys_info,
            }
        }))
    except Exception:
        pass

    try:
        while True:
            data_str = await websocket.receive_text()
            try:
                msg = json.loads(data_str)
                action = msg.get("action")

                if action == "start":
                    agent.start_goal(
                        goal=msg.get("goal", ""),
                        model_name=msg.get("model", settings.DEFAULT_MODEL),
                        require_approval=msg.get("require_approval", False)
                    )
                elif action == "stop":
                    agent.stop()
                elif action == "pause":
                    agent.pause()
                elif action == "resume":
                    agent.resume()
                elif action == "approve":
                    agent.approve_step(msg.get("approved", True))
                elif action == "request_screenshot":
                    img = controller.take_screenshot()
                    if settings.GRID_OVERLAY:
                        img = VisualGrounding.draw_coordinate_grid(img, grid_step=150)
                    jpeg_bytes, (w, h) = VisualGrounding.optimize_image(img, max_width=1600, quality=80)
                    b64 = VisualGrounding.to_base64_data_url(jpeg_bytes)
                    await websocket.send_text(json.dumps({
                        "type": "screen_update",
                        "data": {"data_url": b64, "resolution": f"{w}x{h}"}
                    }))
                elif action == "request_system_info":
                    sys_info = controller.get_system_info()
                    await websocket.send_text(json.dumps({
                        "type": "system_info",
                        "data": sys_info
                    }))
                elif action == "update_key":
                    new_key = msg.get("api_key", "")
                    settings.update_api_key(new_key)
                    await websocket.send_text(json.dumps({
                        "type": "key_updated",
                        "data": {"has_api_key": bool(settings.GEMINI_API_KEY)}
                    }))
                elif action == "toggle_grid":
                    settings.GRID_OVERLAY = not settings.GRID_OVERLAY
                    await websocket.send_text(json.dumps({
                        "type": "grid_toggled",
                        "data": {"grid_overlay": settings.GRID_OVERLAY}
                    }))
            except Exception as e:
                logger.error(f"WebSocket message handling error: {e}")
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)
    except Exception:
        if websocket in active_connections:
            active_connections.remove(websocket)

# Mount web directory
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

@app.get("/")
async def get_index():
    index_path = WEB_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Gemini PC Interactive server is running. Web UI directory not found."}
