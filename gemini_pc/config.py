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
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gemini-3.6-flash")
    MAX_AGENT_STEPS: int = int(os.getenv("MAX_AGENT_STEPS", "30"))
    SCREENSHOT_MAX_WIDTH: int = int(os.getenv("SCREENSHOT_MAX_WIDTH", "1920"))
    GRID_OVERLAY: bool = os.getenv("GRID_OVERLAY", "true").lower() in ("true", "1", "yes")
    ACTION_DELAY_SEC: float = float(os.getenv("ACTION_DELAY_SEC", "0.05"))
    REQUIRE_CONFIRMATION: bool = os.getenv("REQUIRE_CONFIRMATION", "false").lower() in ("true", "1", "yes")

    # Google One / AI Pro Account settings
    GOOGLE_ACCOUNT_EMAIL: str = os.getenv("GOOGLE_ACCOUNT_EMAIL", "")
    IS_GOOGLE_ONE: bool = os.getenv("IS_GOOGLE_ONE", "true").lower() in ("true", "1", "yes")

    # Google Gemini API Key (Google AI Studio)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()

settings = Settings()


