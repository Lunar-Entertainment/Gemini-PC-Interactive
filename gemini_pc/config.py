import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

# Load environment variables
load_dotenv(dotenv_path=ENV_FILE)

class Settings:
    PORT: int = int(os.getenv("PORT", "8080"))
    HOST: str = os.getenv("HOST", "127.0.0.1")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash")
    MAX_AGENT_STEPS: int = int(os.getenv("MAX_AGENT_STEPS", "30"))
    SCREENSHOT_MAX_WIDTH: int = int(os.getenv("SCREENSHOT_MAX_WIDTH", "1600"))
    GRID_OVERLAY: bool = os.getenv("GRID_OVERLAY", "true").lower() in ("true", "1", "yes")
    ACTION_DELAY_SEC: float = float(os.getenv("ACTION_DELAY_SEC", "0.6"))
    REQUIRE_CONFIRMATION: bool = os.getenv("REQUIRE_CONFIRMATION", "false").lower() in ("true", "1", "yes")

    @classmethod
    def update_api_key(cls, new_key: str):
        cls.GEMINI_API_KEY = new_key.strip()
        # Save to .env
        env_lines = []
        if ENV_FILE.exists():
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                env_lines = f.readlines()

        key_found = False
        new_lines = []
        for line in env_lines:
            if line.startswith("GEMINI_API_KEY="):
                new_lines.append(f"GEMINI_API_KEY={new_key.strip()}\n")
                key_found = True
            else:
                new_lines.append(line)

        if not key_found:
            new_lines.append(f"GEMINI_API_KEY={new_key.strip()}\n")

        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

settings = Settings()
