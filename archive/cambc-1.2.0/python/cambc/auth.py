"""Credential storage for cambc CLI authentication."""

import json
from pathlib import Path

CREDENTIALS_DIR = Path.home() / ".cambc"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"

# Default to production; overridable via CAMBC_API_URL env var
DEFAULT_API_URL = "https://game.battlecode.cam"


def get_api_url() -> str:
    import os
    return os.environ.get("CAMBC_API_URL", DEFAULT_API_URL)


def save_credentials(token: str, expires_at: str, user: dict, team: dict | None) -> None:
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "token": token,
        "expires_at": expires_at,
        "user": user,
        "team": team,
    }
    CREDENTIALS_FILE.write_text(json.dumps(data, indent=2))
    # Restrict permissions to owner only
    CREDENTIALS_FILE.chmod(0o600)


def load_credentials() -> dict | None:
    if not CREDENTIALS_FILE.exists():
        return None
    try:
        return json.loads(CREDENTIALS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def clear_credentials() -> None:
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()


def get_token() -> str | None:
    creds = load_credentials()
    if not creds:
        return None
    return creds.get("token")
