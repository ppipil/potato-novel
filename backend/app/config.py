import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH, override=True)


@dataclass
class Settings:
    client_id: str = os.getenv("SECONDME_CLIENT_ID", "")
    client_secret: str = os.getenv("SECONDME_CLIENT_SECRET", "")
    redirect_uri: str = os.getenv("SECONDME_REDIRECT_URI", "http://localhost:3000/api/auth/callback")
    scope: str = os.getenv("SECONDME_SCOPE", "openid profile")
    auth_url: str = os.getenv("SECONDME_AUTH_URL", "")
    token_url: str = os.getenv("SECONDME_TOKEN_URL", "")
    userinfo_url: str = os.getenv("SECONDME_USERINFO_URL", "")
    session_secret: str = os.getenv("SESSION_SECRET", "")
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    secondme_app_id: str = os.getenv("SECONDME_APP_ID", "")


settings = Settings()
