import sys
import argparse
import time
from gemini_pc.config import settings
from gemini_pc.pc_controller import controller
from gemini_pc.gemini_agent import agent, AgentStatus

def main():
    parser = argparse.ArgumentParser(description="Gemini PC Interactive CLI - Control your PC with Google Gemini")
    parser.add_argument("--goal", "-g", type=str, help="Goal or task description for Gemini to execute")
    parser.add_argument("--model", "-m", type=str, default="gemini-2.5-flash", help="Gemini model name")
    parser.add_argument("--approval", "-a", action="store_true", help="Require manual confirmation before each action")
    parser.add_argument("--info", "-i", action="store_true", help="Display PC system info and exit")
    parser.add_argument("--screenshot", "-s", type=str, help="Take screenshot and save to specified file path")
    args = parser.parse_args()

    if args.info:
        info = controller.get_system_info()
        print("\n=== PC System & Desktop Info ===")
        for k, v in info.items():
            print(f"  {k}: {v}")
        print("\n=== Visible Windows ===")
        for w in controller.list_windows():
            print(f"  [{w['hwnd']}] {w['title']}")
        return

    if args.screenshot:
        img = controller.take_screenshot()
        img.save(args.screenshot)
        print(f"Screenshot saved to: {args.screenshot}")
        return

    if not args.goal:
        print("Error: Please provide a goal using --goal 'your task here' or run the web UI via python app.py")
        sys.exit(1)

    if not settings.GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY environment variable is not set.")
        print("Set it in your terminal or .env file before running.")
        sys.exit(1)

    print(f"\n[Gemini PC Interactive] Initiating task: '{args.goal}'")
    print(f"Model: {args.model} | Confirmation Mode: {args.approval}")
    print("Press ESC or Ctrl+C at any time to halt.\n")

    def event_handler(payload):
        evt = payload["type"]
        data = payload.get("data", {})
        if evt == "step_start":
            print(f"\n--- [Step {data.get('step')} / {data.get('max_steps')}] ---")
        elif evt == "reasoning":
            print(f"Gemini Thought:\n{data.get('thought')}\n")
        elif evt == "action_executing":
            print(f"Executing: {data.get('tool')}({data.get('args')})")
        elif evt == "action_result":
            print(f"Result: {data.get('output')}")
        elif evt == "task_completed":
            print(f"\n>>> Task Concluded! Success: {data.get('success')}")
            print(f"Summary: {data.get('summary')}\n")
        elif evt == "error":
            print(f"\n[Error] {data.get('message')}")

    agent.register_callback(event_handler)
    agent.start_goal(goal=args.goal, model_name=args.model, require_approval=args.approval)

    try:
        while agent.status in (AgentStatus.RUNNING, AgentStatus.AWAITING_APPROVAL, AgentStatus.PAUSED):
            if agent.status == AgentStatus.AWAITING_APPROVAL and agent.pending_approval_tool:
                pending = agent.pending_approval_tool
                ans = input(f"Approve action '{pending['tool']}' with args {pending['args']}? [y/N]: ").strip().lower()
                agent.approve_step(ans in ("y", "yes"))
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nStopping task on user interrupt...")
        agent.stop()

if __name__ == "__main__":
    main()
