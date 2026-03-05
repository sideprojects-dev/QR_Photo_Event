from fastapi import FastAPI, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from dotenv import load_dotenv
import io
import os
import uuid
from datetime import datetime

app = FastAPI()

load_dotenv()  # Load environment variables from .env file

CLIENT_SECRET_FILE = "client_secret.json"
FOLDER_ID = os.getenv("FOLDER_ID")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_FILE = "token.json"

def get_drive_service():
    creds = None

    # Load existing token if available
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # If no valid token, raise error (user needs to visit /auth/login)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        else:
            raise Exception("Not authenticated. Visit /auth/login")

    return build("drive", "v3", credentials=creds)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/auth/login")
def auth_login():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri="http://localhost:8000/auth/callback"
    )
    auth_url, _ = flow.authorization_url(
        prompt="consent",
        access_type="offline"
    )

    # Save only the code_verifier string, not the whole flow object
    with open("code_verifier.txt", "w") as f:
        f.write(flow.code_verifier or "")

    return RedirectResponse(auth_url)


@app.get("/auth/callback")
def auth_callback(code: str, state: str = None):
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri="http://localhost:8000/auth/callback"
    )

    # Load the saved code_verifier
    with open("code_verifier.txt", "r") as f:
        flow.code_verifier = f.read().strip() or None

    flow.fetch_token(code=code)

    # Save token for future use
    creds = flow.credentials
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    # Clean up temporary file
    os.remove("code_verifier.txt")

    return {"mesaj": "Successfully authenticated!"}

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    content = await file.read()

    # Generate unique filename
    extension = os.path.splitext(file.filename)[1]
    unique_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}{extension}"

    # Upload to Google Drive
    drive = get_drive_service()

    file_metadata = {
        "name": unique_name,
        "parents": [FOLDER_ID]
    }

    media = MediaIoBaseUpload(
        io.BytesIO(content),
        mimetype=file.content_type,
        resumable=True
    )

    drive.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name"
    ).execute()

    return {"mesaj": "Saved!"}