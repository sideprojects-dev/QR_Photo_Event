import os
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()  # load environment variables from .env file

CLIENT_SECRET_FILE = "client_secret.json"
FOLDER_ID = os.getenv("FOLDER_ID")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_FILE = "token.json"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

REQUIRED_SETTINGS = (
    "ADMIN_PASSWORD",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "FOLDER_ID",
    "GOOGLE_DRIVE_TOKEN_JSON",
)


def validate_config(environ=None):
    """Fail at startup with setting names, never credential values."""
    values = os.environ if environ is None else environ
    missing = [
        name for name in REQUIRED_SETTINGS
        if not values.get(name, "").strip()
    ]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    password = values["ADMIN_PASSWORD"]
    if len(password) < 12 or password.lower() == "admin123":
        raise RuntimeError(
            "ADMIN_PASSWORD must have at least 12 characters and cannot be the default password"
        )

    try:
        url = urlsplit(values["SUPABASE_URL"])
        valid_url = url.scheme in ("http", "https") and bool(url.hostname)
    except ValueError:
        valid_url = False
    if not valid_url:
        raise RuntimeError("SUPABASE_URL must be a valid HTTP(S) URL")
