import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body, Request
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
    model: str = "gemini-3.1-flash-lite"
    require_approval: bool = False

class ApiKeyRequest(BaseModel):
    api_key: str
    email: str = ""

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

from fastapi.responses import FileResponse, Response, RedirectResponse, HTMLResponse, StreamingResponse
from gemini_pc.google_oauth import oauth_manager

class GoogleOAuthCredsRequest(BaseModel):
    client_id: str
    client_secret: str

@app.get("/api/status")
async def get_status():
    sys_info = controller.get_system_info()
    oauth_profile = oauth_manager.get_user_profile()
    is_authed = oauth_manager.is_authenticated()
    user_email = oauth_profile.get("email") or settings.GOOGLE_ACCOUNT_EMAIL

    return {
        "status": agent.status.value,
        "current_goal": agent.current_goal,
        "current_step": agent.current_step,
        "max_steps": agent.max_steps,
        "authenticated": is_authed,
        "has_api_key": is_authed,
        "auth_type": "oauth" if is_authed else "none",
        "default_model": settings.DEFAULT_MODEL,
        "google_account": user_email,
        "google_oauth": oauth_profile,
        "has_oauth_creds": oauth_manager.has_client_credentials(),
        "is_google_one": settings.IS_GOOGLE_ONE,
        "system_info": sys_info,
    }

@app.get("/api/auth/google/login")
async def google_login(request: Request, host: Optional[str] = None):
    if not oauth_manager.has_client_credentials():
        raise HTTPException(
            status_code=400,
            detail="Google OAuth Client ID & Secret are not configured yet. Please configure them in Settings."
        )

    # Determine redirect host (defaulting to localhost or user specified host)
    chosen_host = host or "localhost"
    redirect_uri = f"http://{chosen_host}:{settings.PORT}/api/auth/google/callback"

    try:
        auth_url = oauth_manager.get_authorization_url(redirect_uri=redirect_uri)
        return RedirectResponse(auth_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/auth/google/callback")
async def google_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    if error:
        return HTMLResponse(f"""
        <div style="background:#090d16;color:#f8fafc;font-family:sans-serif;padding:40px;text-align:center;">
          <h2 style="color:#fb7185;">Google OAuth Error</h2>
          <p>{error}</p>
          <a href="/" style="color:#38bdf8;">Return to Dashboard</a>
        </div>
        """)
    if not code:
        return HTMLResponse("<h3>Error: Missing authorization code</h3>")

    # Use the exact redirect_uri recorded when login was initiated
    redirect_uri = oauth_manager.last_redirect_uri or f"{request.base_url}api/auth/google/callback"
    try:
        user_info = oauth_manager.handle_oauth_callback(code=code, redirect_uri=redirect_uri, state=state)
        email = user_info.get("email", "Google One User")

        # Broadcast update to web UI
        broadcast_sync({
            "type": "oauth_success",
            "data": {
                "email": email,
                "name": user_info.get("name", ""),
                "picture": user_info.get("picture", ""),
            }
        })

        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
          <title>Google One Connected</title>
          <style>
            body {{
              background: #090d16;
              color: #f8fafc;
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
              display: flex;
              align-items: center;
              justify-content: center;
              height: 100vh;
              margin: 0;
            }}
            .card {{
              background: #1e293b;
              padding: 32px 40px;
              border-radius: 16px;
              border: 1px solid rgba(99, 102, 241, 0.4);
              box-shadow: 0 10px 40px rgba(0,0,0,0.6);
              text-align: center;
              max-width: 420px;
            }}
            h2 {{ color: #38bdf8; margin-bottom: 12px; }}
            p {{ color: #94a3b8; font-size: 14px; line-height: 1.5; }}
            .btn {{
              display: inline-block;
              margin-top: 20px;
              padding: 10px 20px;
              background: linear-gradient(135deg, #38bdf8, #818cf8);
              color: #fff;
              text-decoration: none;
              border-radius: 8px;
              font-weight: 600;
              font-size: 14px;
            }}
          </style>
        </head>
        <body>
          <div class="card">
            <h2>Google One Connected!</h2>
            <p>Signed in as <strong>{email}</strong>.</p>
            <p>Your Google One AI Pro plan is now authenticated with Gemini PC Interactive.</p>
            <a href="/" class="btn">Return to Dashboard</a>
          </div>
          <script>
            setTimeout(() => {{ window.location.href = "/"; }}, 1800);
          </script>
        </body>
        </html>
        """)
    except Exception as e:
        return HTMLResponse(f"<h3>OAuth Error</h3><p>{str(e)}</p>")

@app.post("/api/auth/google/credentials")
async def save_oauth_credentials(req: GoogleOAuthCredsRequest):
    if not req.client_id.strip() or not req.client_secret.strip():
        raise HTTPException(status_code=400, detail="Client ID and Secret cannot be empty.")
    oauth_manager.set_client_credentials(req.client_id, req.client_secret)
    return {"success": True, "has_oauth_creds": oauth_manager.has_client_credentials()}

@app.post("/api/auth/google/logout")
async def google_logout():
    oauth_manager.logout()
    return {"success": True}

@app.post("/api/api-key")
async def set_api_key():
    return {
        "success": True,
        "authenticated": oauth_manager.is_authenticated(),
        "has_api_key": oauth_manager.is_authenticated(),
        "google_account": settings.GOOGLE_ACCOUNT_EMAIL,
    }

@app.get("/api/screenshot")
async def get_screenshot(grid: bool = False):
    img = controller.take_screenshot()
    if grid or settings.GRID_OVERLAY:
        img = VisualGrounding.draw_coordinate_grid(img, grid_step=100)
    opt = VisualGrounding.optimize_image(img, max_width=1920, quality=85)
    return Response(content=opt.bytes, media_type="image/jpeg")

async def mjpeg_generator(fps: int = 1):
    # Lock stream strictly to 1 FPS to minimize CPU overhead and maximize agent responsiveness
    interval = 1.0
    while True:
        try:
            img = controller.take_screenshot()
            opt = VisualGrounding.optimize_image(img, max_width=1280, quality=60)
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + opt.bytes + b"\r\n"
            )
            await asyncio.sleep(interval)
        except Exception:
            await asyncio.sleep(1.0)

@app.get("/api/stream")
async def stream_desktop(fps: int = 1):
    return StreamingResponse(
        mjpeg_generator(fps=1),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

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

    # Send complete initial state
    try:
        sys_info = controller.get_system_info()
        oauth_profile = oauth_manager.get_user_profile()
        is_authed = oauth_manager.is_authenticated()
        user_email = oauth_profile.get("email") or settings.GOOGLE_ACCOUNT_EMAIL

        await websocket.send_text(json.dumps({
            "type": "init",
            "timestamp": 0,
            "data": {
                "status": agent.status.value,
                "goal": agent.current_goal,
                "step": agent.current_step,
                "max_steps": agent.max_steps,
                "authenticated": is_authed,
                "has_api_key": is_authed,
                "auth_type": "oauth" if is_authed else "none",
                "default_model": settings.DEFAULT_MODEL,
                "google_account": user_email,
                "google_oauth": oauth_profile,
                "has_oauth_creds": oauth_manager.has_client_credentials(),
                "is_google_one": settings.IS_GOOGLE_ONE,
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
                        img = VisualGrounding.draw_coordinate_grid(img, grid_step=100)
                    opt = VisualGrounding.optimize_image(img, max_width=settings.SCREENSHOT_MAX_WIDTH, quality=80)
                    b64 = VisualGrounding.to_base64_data_url(opt.bytes)
                    orig_w, orig_h = opt.orig_size
                    await websocket.send_text(json.dumps({
                        "type": "screen_update",
                        "data": {"data_url": b64, "resolution": f"{orig_w}x{orig_h}"}
                    }))
                elif action == "request_system_info":
                    sys_info = controller.get_system_info()
                    await websocket.send_text(json.dumps({
                        "type": "system_info",
                        "data": sys_info
                    }))
                elif action == "update_key":
                    await websocket.send_text(json.dumps({
                        "type": "key_updated",
                        "data": {"authenticated": oauth_manager.is_authenticated(), "has_api_key": oauth_manager.is_authenticated()}
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
