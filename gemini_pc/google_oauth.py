import os
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow

from gemini_pc.config import BASE_DIR, ENV_FILE

TOKENS_FILE = BASE_DIR / "google_tokens.json"
CLIENT_SECRETS_FILE = BASE_DIR / "client_secrets.json"

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/generative-language",
    "https://www.googleapis.com/auth/cloud-platform",
]

class GoogleOAuthManager:
    """Handles Google OAuth 2.0 authentication for Google One AI Pro users."""

    def __init__(self):
        self._tokens: Optional[Dict[str, Any]] = None
        self.last_redirect_uri: str = ""
        self._load_tokens()

    def _load_tokens(self):
        if TOKENS_FILE.exists():
            try:
                with open(TOKENS_FILE, "r", encoding="utf-8") as f:
                    self._tokens = json.load(f)
            except Exception:
                self._tokens = None

    def _save_tokens(self, tokens: Dict[str, Any]):
        self._tokens = tokens
        with open(TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2)

    def get_client_credentials(self) -> Tuple[str, str]:
        # Check environment variables
        client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

        # Check client_secrets.json if env vars not set
        if (not client_id or not client_secret) and CLIENT_SECRETS_FILE.exists():
            try:
                with open(CLIENT_SECRETS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    conf = data.get("installed") or data.get("web") or {}
                    client_id = conf.get("client_id", "")
                    client_secret = conf.get("client_secret", "")
            except Exception:
                pass

        return client_id, client_secret

    def set_client_credentials(self, client_id: str, client_secret: str):
        # Update .env
        env_dict = {}
        if ENV_FILE.exists():
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_dict[k.strip()] = v.strip()

        env_dict["GOOGLE_CLIENT_ID"] = client_id.strip()
        env_dict["GOOGLE_CLIENT_SECRET"] = client_secret.strip()

        with open(ENV_FILE, "w", encoding="utf-8") as f:
            for k, v in env_dict.items():
                f.write(f"{k}={v}\n")

        os.environ["GOOGLE_CLIENT_ID"] = client_id.strip()
        os.environ["GOOGLE_CLIENT_SECRET"] = client_secret.strip()

    def has_client_credentials(self) -> bool:
        cid, csecret = self.get_client_credentials()
        return bool(cid and csecret)

    def is_authenticated(self) -> bool:
        return self._tokens is not None and bool(self._tokens.get("access_token") or self._tokens.get("refresh_token"))

    def get_user_profile(self) -> Dict[str, Any]:
        if not self._tokens:
            return {"authenticated": False}
        return {
            "authenticated": True,
            "email": self._tokens.get("email", ""),
            "name": self._tokens.get("name", ""),
            "picture": self._tokens.get("picture", ""),
            "expiry": self._tokens.get("expiry"),
        }

    def get_authorization_url(self, redirect_uri: str) -> str:
        client_id, client_secret = self.get_client_credentials()
        if not client_id or not client_secret:
            raise ValueError("Google OAuth Client ID or Client Secret is missing. Please configure them in Settings.")

        self.last_redirect_uri = redirect_uri

        client_config = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )

        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent"
        )
        return auth_url

    def handle_oauth_callback(self, code: str, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
        client_id, client_secret = self.get_client_credentials()
        eff_redirect_uri = redirect_uri or self.last_redirect_uri

        client_config = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=eff_redirect_uri
        )
        flow.fetch_token(code=code)
        creds = flow.credentials

        # Fetch user info
        user_info = {}
        try:
            resp = requests.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"},
                timeout=10
            )
            if resp.status_code == 200:
                user_info = resp.json()
        except Exception:
            pass

        token_data = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or []),
            "email": user_info.get("email", ""),
            "name": user_info.get("name", ""),
            "picture": user_info.get("picture", ""),
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }

        self._save_tokens(token_data)
        return user_info

    def get_valid_access_token(self) -> Optional[str]:
        """Returns a valid access token, automatically refreshing it if expired."""
        if not self._tokens:
            return None

        access_token = self._tokens.get("access_token")
        refresh_token = self._tokens.get("refresh_token")
        client_id, client_secret = self.get_client_credentials()

        if not refresh_token and not access_token:
            return None

        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id or self._tokens.get("client_id"),
            client_secret=client_secret or self._tokens.get("client_secret"),
            scopes=self._tokens.get("scopes", SCOPES),
        )

        # Check if expired or needs refresh
        if not creds.valid or creds.expired:
            if creds.refresh_token:
                try:
                    creds.refresh(Request())
                    self._tokens["access_token"] = creds.token
                    if creds.expiry:
                        self._tokens["expiry"] = creds.expiry.isoformat()
                    self._save_tokens(self._tokens)
                except Exception as e:
                    print(f"[GoogleOAuth] Failed to refresh token: {e}")
                    return None

        return creds.token

    def logout(self):
        self._tokens = None
        if TOKENS_FILE.exists():
            try:
                os.remove(TOKENS_FILE)
            except Exception:
                pass

# Global singleton
oauth_manager = GoogleOAuthManager()
