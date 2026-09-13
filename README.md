# ⚡ Gemini PC Interactive

> **Control, Automate, and Interact with your Windows PC & Desktop using Google Gemini Multimodal Vision & Reasoning.**

**Gemini PC Interactive** is an autonomous and interactive desktop agent that empowers Google Gemini models (`gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash`) to see your computer screen, analyze user interfaces, and execute real-world mouse and keyboard actions to achieve tasks autonomously.

---

## ✨ Features

- 👁️ **Visual Desktop Grounding**:
  - High-resolution desktop screen capture with Windows Per-Monitor DPI awareness.
  - Coordinate reference grid overlay that helps Gemini accurately pinpoint small buttons, menus, and text fields.
  - Automatic image compression for low latency and efficient token usage.

- 🖱️ **Full PC & Mouse/Keyboard Control**:
  - **Mouse**: Single click, double click, right click, drag-and-drop, smooth movement, and vertical scrolling.
  - **Keyboard**: Typing with full Unicode/emoji support (automatic clipboard fallback), key presses (`Enter`, `Tab`, `Esc`, `Win`, etc.), and hotkeys (`Ctrl+C`, `Win+R`, `Alt+Tab`, `Alt+F4`, `Ctrl+Shift+Esc`).
  - **OS Operations**: Launch applications (`notepad`, `calc`, `chrome`, `msedge`, `explorer`, `powershell`, or any executable/URL), window enumeration, bring window to focus, read/write clipboard, and execute PowerShell commands.

- 🧠 **Autonomous Multimodal Agent Loop**:
  - Takes a high-level goal from the user (e.g., *"Open Calculator and compute 487 * 932"*, *"Open Notepad and write a system status report"*, *"Search YouTube for lofi music"*).
  - Continuously observes the desktop, reasons in natural language, calls tools, observes the effect, and iterates until the goal is finished.

- 🛡️ **Comprehensive Safety & Kill-Switches**:
  - **Emergency Stop Hotkey**: Press <kbd>ESC</kbd> at any time to immediately freeze the agent loop.
  - **Fail-Safe Corner**: Moving your mouse to the top-left corner `(0, 0)` triggers an instant safety abort.
  - **Step-by-Step Approval Mode**: Optional human-in-the-loop toggle where Gemini must request permission before executing every action.

- 🎨 **Ultra-Modern Glassmorphism Web Dashboard**:
  - Live desktop viewport with real-time hover coordinate tracker.
  - Live Gemini Cognitive Stream (Thoughts, Actions, Tool Outputs, Timings).
  - Quick App Launchers & Quick Presets.
  - System performance monitors (CPU %, RAM %, active foreground window, screen resolution).
  - API Key & settings modal with local `.env` persistence.

- 💻 **CLI & Scripting Interface**:
  - Can also be launched directly from the terminal for headless execution or automated scripts.

---

## 🚀 Quick Start

### 1. Launch with One Click
Double-click **`run.bat`** in the project folder. It will launch the server and automatically open your default browser to `http://localhost:8080`.

### 2. Manual Command Line Launch
```powershell
# Activate the virtual environment
.\venv\Scripts\activate

# Launch the interactive web dashboard
python app.py
```

### 3. CLI Mode (Headless / Terminal)
```powershell
# Run a task directly from the command line
python -m gemini_pc.cli --goal "Open Calculator and compute 125 * 38" --model gemini-2.5-flash

# Run with human approval for each step
python -m gemini_pc.cli --goal "Open Notepad and write a note" --approval

# Inspect system and open windows
python -m gemini_pc.cli --info
```

---

## 🔑 Configuration & API Key

1. When you first open the web interface, click the **Settings** gear icon (or open the prompt).
2. Enter your **Google Gemini API Key** (obtainable for free at [Google AI Studio](https://aistudio.google.com/app/apikey)).
3. Click **Save Settings**. The key will be securely saved into `.env` and loaded automatically.

---

## 🛠️ Project Structure

```
GeminiPCInteractive/
├── app.py                      # Main entrypoint: server launcher & browser opener
├── run.bat                     # Windows one-click batch launcher
├── requirements.txt            # Python dependencies
├── .env.example                # Example configuration
├── gemini_pc/
│   ├── __init__.py
│   ├── config.py               # Settings and .env management
│   ├── pc_controller.py        # Windows DPI, Desktop Attacher, Mouse, Keyboard & OS controls
│   ├── visual_grounding.py     # Screenshot capture, coordinate grid overlay & compression
│   ├── tools.py                # Gemini tool definitions and function dispatcher
│   ├── gemini_agent.py         # Autonomous agent loop, multimodal reasoning & safety
│   ├── server.py               # FastAPI server and WebSocket real-time broadcast
│   └── cli.py                  # Command-line interface
└── web/
    ├── index.html              # Sleek responsive dashboard HTML
    ├── style.css               # Glassmorphism dark mode styling
    └── app.js                  # WebSocket client & interactive canvas logic
```

---

## 🔒 Safety Guidelines
- Never run untrusted prompts that request system deletion or sensitive actions.
- Keep the <kbd>ESC</kbd> emergency stop in mind when running in autonomous mode.
- Use the **Step-by-Step Approval** mode when trying sensitive or novel workflows.
