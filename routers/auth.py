import os
import tempfile

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow

from config import SCOPES

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def auth_login():
    # Write client_secret to a temp file (Flow requires a file)
    client_secret = os.getenv("client_secret.json")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(client_secret)
        temp_path = f.name

    flow = Flow.from_client_secrets_file(
        temp_path,
        scopes=SCOPES,
        redirect_uri=os.getenv("REDIRECT_URI", "http://localhost:8000/auth/callback")
    )
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

    with open("code_verifier.txt", "w") as f:
        f.write(flow.code_verifier or "")

    os.unlink(temp_path)
    return RedirectResponse(auth_url)


@router.get("/callback")
def auth_callback(code: str, state: str = None):
    client_secret = os.getenv("client_secret.json")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(client_secret)
        temp_path = f.name

    flow = Flow.from_client_secrets_file(
        temp_path,
        scopes=SCOPES,
        redirect_uri=os.getenv("REDIRECT_URI", "http://localhost:8000/auth/callback")
    )

    with open("code_verifier.txt", "r") as f:
        flow.code_verifier = f.read().strip() or None

    flow.fetch_token(code=code)

    new_token_json = flow.credentials.to_json()

    with open("token.json", "w", encoding="utf-8") as token_file:
        token_file.write(new_token_json)

    os.unlink(temp_path)

    if os.path.exists("code_verifier.txt"):
        os.remove("code_verifier.txt")

    return {"mesaj": "Successfully authenticated!"}
