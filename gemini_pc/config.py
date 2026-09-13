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
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gemini-3.8-flash")
    MAX_AGENT_STEPS: int = int(os.getenv("MAX_AGENT_STEPS", "30"))
    SCREENSHOT_MAX_WIDTH: int = int(os.getenv("SCREENSHOT_MAX_WIDTH", "1600"))
    GRID_OVERLAY: bool = os.getenv("GRID_OVERLAY", "true").lower() in ("true", "1", "yes")
    ACTION_DELAY_SEC: float = float(os.getenv("ACTION_DELAY_SEC", "0.6"))
    REQUIRE_CONFIRMATION: bool = os.getenv("REQUIRE_CONFIRMATION", "false").lower() in ("true", "1", "yes")

    # Google One / AI Pro Account settings
    GOOGLE_ACCOUNT_EMAIL: str = os.getenv("GOOGLE_ACCOUNT_EMAIL", "")
    IS_GOOGLE_ONE: bool = os.getenv("IS_GOOGLE_ONE", "true").lower() in ("true", "1", "yes")

    @classmethod
    def update_api_key(cls, new_key: str, email: str = ""):
        cls.GEMINI_API_KEY = new_key.strip()
        if email:
            cls.GOOGLE_ACCOUNT_EMAIL = email.strip()

        env_dict = {}
        if ENV_FILE.exists():
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_dict[k.strip()] = v.strip()

        env_dict["GEMINI_API_KEY"] = cls.GEMINI_API_KEY
        if email:
            env_dict["GOOGLE_ACCOUNT_EMAIL"] = cls.GOOGLE_ACCOUNT_EMAIL
        env_dict["DEFAULT_MODEL"] = cls.DEFAULT_MODEL

        with open(ENV_FILE, "w", encoding="utf-8") as f:
            for k, v in env_dict.items():
                f.write(f"{k}={v}\n")

settings = Settings()
