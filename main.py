from fastapi import FastAPI, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import Header
from fastapi.responses import StreamingResponse
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from dotenv import load_dotenv
from datetime import datetime
from supabase import create_client
import io
import io as io_module
import os
import uuid
import json
import tempfile
import qrcode


app = FastAPI()

load_dotenv()  # load environment variables from .env file

CLIENT_SECRET_FILE = "client_secret.json"
FOLDER_ID = os.getenv("FOLDER_ID")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_FILE = "token.json"

def get_drive_service():
    creds = None

    token_json = os.getenv("token.json")
    print(f"token_json exists: {bool(token_json)}")

    if token_json:
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
        print(f"creds valid: {creds.valid}, expired: {creds.expired}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing token...")
            creds.refresh(Request())
        else:
            raise Exception("No valid credentials available. Please authenticate at /auth/login")
        
    service = build("drive", "v3", credentials=creds)
    print(f"Drive service type: {type(service)}")
    return service

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/auth/login")
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

@app.get("/auth/callback")
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
    os.unlink(temp_path)

    if os.path.exists("code_verifier.txt"):
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

def get_supabase():
    return create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY")
    )
    
@app.get("/event/{slug}")
def event_page(slug: str):
    # look up event in Supabase
    supabase = get_supabase()
    result = supabase.table("events").select("*").eq("slug", slug).execute()

    if not result.data:
        return HTMLResponse("<h1>Eveniment negăsit</h1>", status_code=404)
    
    with open("static/index.html", "r", encoding="utf-8") as f:  
        return HTMLResponse(f.read())
    
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD","admin123")

@app.post("/api/create-event")
async def create_event(
    event_name: str,
    x_admin_password: str = Header(None)
):
    # check admin password
    if x_admin_password != ADMIN_PASSWORD:
        return {"error": "Unauthorized"}, 401
    
    # generate slug
    slug = event_name.lower()
    slug = slug.replace(" & ", " - ").replace(" ", " ")
    slug = ''.join(c for c in slug if c.isalnum() or c == '-')

    # create folder in Google Drive
    drive = get_drive_service
    folder = drive.files().create(
        body={
            "name": slug,
            "mimeType": "application/vnd.google-apps.folder"},
        fields="id"
    ).execute()
    folder_id = folder["id"]

    # save event to Supabase
    supabase = get_supabase()
    supabase.table("events").insert({
        "slug": slug,
        "name": event_name,
        "folder_id": folder_id,
        "created_at": datetime.now().isoformat()
    }).execute()

    return {
        "success": True,
        "slug": slug,
        "url": f"https://qr-photo-event.onrender.com/event/{slug}",
        "folder_id": folder_id
    }

@app.get("/admin")
def admin_panel():
    with open("static/admin.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())
    
@app.get("/api/events")
def get_events(x_admin_password: str = Header(None)):
    if x_admin_password != ADMIN_PASSWORD:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    supabase = get_supabase()
    result = supabase.table("events").select("*").execute()
    return {"events": result.data}

@app.get("/api/qr/{slug}")
def get_qr(slug: str):
    # Generate QR and return as image
    url = f"https://qr-photo-event.onrender.com/event/{slug}"
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io_module.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png", headers={"Content-Disposition": f"attachment; filename={slug}_qr.png"})