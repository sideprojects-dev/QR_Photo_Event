from fastapi import FastAPI, UploadFile, File, HTTPException
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

    new_token_json = flow.credentials.to_json()

    with open("token.json", "w", encoding="utf-8") as token_file:   
        token_file.write(new_token_json)

    os.unlink(temp_path)

    if os.path.exists("code_verifier.txt"):
        os.remove("code_verifier.txt")

    return {"mesaj": "Successfully authenticated!"}

@app.post("/upload/{slug}")
async def upload(slug: str, file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith(("image/", "video/")):
        raise HTTPException(
            status_code=400,
            detail="Only image and video files are allowed."
        )

    # Get folder_id for this event from Supabase
    supabase = get_supabase()
    result = supabase.table("events").select("folder_id").eq("slug", slug).execute()
    
    if not result.data:
        return {"mesaj": "Eveniment negăsit"}
    
    event_folder_id = result.data[0]["folder_id"]

    # Generate unique filename
    extension = os.path.splitext(file.filename)[1]
    unique_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}{extension}"

    # Upload to the event's specific folder
    drive = get_drive_service()
    file_metadata = {
        "name": unique_name,
        "parents": [event_folder_id]  # event folder, not main folder
    }

    # upload pe bucati
    await file.seek(0)
    media = MediaIoBaseUpload(file.file, mimetype=file.content_type, chunksize=8 * 1024 * 1024, resumable=True)
    request = drive.files().create(body=file_metadata, media_body=media, fields="id")
    response = None

    while response is None:
        _, response = request.next_chunk()

    return {"mesaj": "Saved!"}

def get_supabase():
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    public_key = os.getenv("SUPABASE_KEY")

    if not service_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is missing from environment")

    return create_client(
        os.getenv("SUPABASE_URL"),
        service_key
    )

@app.get("/event/master")
def master_redirect():
    # QR-ul master este printat o singură dată și redirecționează
    # mereu către evenimentul curent marcat drept "active" în Supabase.
    supabase = get_supabase()
    result = (
        supabase
        .table("events")
        .select("slug")
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not result.data:
        return HTMLResponse("<h1>Niciun eveniment activ momentan</h1>", status_code=404)

    active_slug = result.data[0]["slug"]
    return RedirectResponse(f"/event/{active_slug}")

@app.get("/event/master/{location_slug}")
def master_redirect_location(location_slug: str):
    # QR permanent al unei locații: nu se schimbă niciodată, doar
    # redirecționează mereu către evenimentul activ curent al locației.
    supabase = get_supabase()

    location_result = (
        supabase
        .table("locations")
        .select("id")
        .eq("slug", location_slug)
        .limit(1)
        .execute()
    )

    if not location_result.data:
        return HTMLResponse("<h1>Locația nu a fost găsită</h1>", status_code=404)

    location_id = location_result.data[0]["id"]

    event_result = (
        supabase
        .table("events")
        .select("slug")
        .eq("location_id", location_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )

    if not event_result.data:
        return HTMLResponse("<h1>Niciun eveniment activ momentan la această locație</h1>", status_code=404)

    active_slug = event_result.data[0]["slug"]
    return RedirectResponse(f"/event/{active_slug}")

@app.get("/event/{slug}")
def event_page(slug: str):
    supabase = get_supabase()
    result = supabase.table("events").select("*").eq("slug", slug).execute()

    if not result.data:
        return HTMLResponse("<h1>Eveniment negăsit</h1>", status_code=404)
    
    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    
    # Fortarează browserul să ia mereu ultima versiune a scriptului prin adăugarea unui query param cu timestamp.
    script_version = int(os.path.getmtime("static/script.js"))
    html = html.replace(
        '<script src="/static/script.js"></script>',
        f'<script src="/static/script.js?v={script_version}"></script>'
    )

    # Inject slug into page so JavaScript knows where to upload
    html = html.replace("</body>", f'<script>window.EVENT_SLUG = "{slug}";</script></body>')
    return HTMLResponse(html)
    
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD","admin123")

@app.post("/api/locations")
async def create_location(
    location_name: str,
    x_admin_password: str = Header(None)
):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    location_name = location_name.strip()

    if not location_name:
        raise HTTPException(
            status_code=400,
            detail="Location name is required."
        )

    slug = location_name.lower()
    slug = slug.replace(" & ", "-").replace(" ", "-")
    slug = ''.join(c for c in slug if c.isalnum() or c == '-')

    supabase = get_supabase()

    existing_location = (
        supabase
        .table("locations")
        .select("id")
        .eq("slug", slug)
        .execute()
    )

    if existing_location.data:
        raise HTTPException(
            status_code=409,
            detail="Există deja o locație cu acest nume."
        )

    drive = get_drive_service()

    folder = drive.files().create(
        body={
            "name": location_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [FOLDER_ID]
        },
        fields="id"
    ).execute()

    folder_id = folder["id"]

    result = (
        supabase
        .table("locations")
        .insert({
            "name": location_name,
            "slug": slug,
            "folder_id": folder_id
        })
        .execute()
    )

    return {
        "success": True,
        "location": result.data[0] if result.data else {
            "name": location_name,
            "slug": slug,
            "folder_id": folder_id
        }
    }

@app.get("/api/locations")
def get_locations(x_admin_password: str = Header(None)):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    supabase = get_supabase()

    result = (
        supabase
        .table("locations")
        .select("*")
        .order("created_at", desc=False)
        .execute()
    )

    return {
        "locations": result.data
    }

@app.get("/api/locations/{location_slug}/events")
def get_location_events(
    location_slug: str,
    x_admin_password: str = Header(None)
):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    supabase = get_supabase()

    location_result = (
        supabase
        .table("locations")
        .select("id, name, slug")
        .eq("slug", location_slug)
        .limit(1)
        .execute()
    )

    if not location_result.data:
        raise HTTPException(
            status_code=404,
            detail="Locația nu a fost găsită."
        )

    location = location_result.data[0]

    events_result = (
        supabase
        .table("events")
        .select("*")
        .eq("location_id", location["id"])
        .order("created_at", desc=True)
        .execute()
    )

    return {
        "location": location,
        "events": events_result.data
    }

@app.post("/api/create-event")
async def api_create_event(
    event_name: str,
    location_slug: str,
    x_admin_password: str = Header(None)
):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    event_name = event_name.strip()
    location_slug = location_slug.strip()

    if not event_name:
        raise HTTPException(
            status_code=400,
            detail="Event name is required."
        )

    supabase = get_supabase()

    # Get the selected location
    location_result = (
        supabase
        .table("locations")
        .select("id, name, folder_id")
        .eq("slug", location_slug)
        .limit(1)
        .execute()
    )

    if not location_result.data:
        raise HTTPException(
            status_code=404,
            detail="Locația nu a fost găsită."
        )

    location = location_result.data[0]
    location_id = location["id"]
    location_folder_id = location["folder_id"]

    if not location_folder_id:
        raise HTTPException(
            status_code=500,
            detail="Locația nu are folder Google Drive asociat."
        )

    # Generate event slug
    slug = event_name.lower()
    slug = slug.replace(" & ", "-").replace(" ", "-")
    slug = ''.join(c for c in slug if c.isalnum() or c == '-')

    # Check duplicate event slug
    existing_event = (
        supabase
        .table("events")
        .select("id")
        .eq("slug", slug)
        .execute()
    )

    if existing_event.data:
        raise HTTPException(
            status_code=409,
            detail="Există deja un eveniment cu acest nume."
        )

    drive = get_drive_service()

    folder_id = None

    try:
        # Create event folder inside the location folder
        folder = drive.files().create(
            body={
                "name": event_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [location_folder_id]
            },
            fields="id"
        ).execute()

        folder_id = folder["id"]

        # Archive only the active event from this location
        (
            supabase
            .table("events")
            .update({"status": "archived"})
            .eq("location_id", location_id)
            .eq("status", "active")
            .execute()
        )

        # Save the new event
        result = (
            supabase
            .table("events")
            .insert({
                "slug": slug,
                "name": event_name,
                "folder_id": folder_id,
                "created_at": datetime.now().isoformat(),
                "status": "active",
                "location_id": location_id
            })
            .execute()
        )

    except Exception:
        # Avoid leaving an orphan folder if Supabase insert fails
        if folder_id:
            try:
                drive.files().delete(fileId=folder_id).execute()
            except Exception:
                pass

        raise

    return {
        "success": True,
        "slug": slug,
        "url": f"https://qr-photo-event.onrender.com/event/{slug}",
        "folder_id": folder_id,
        "location_id": location_id
    }

@app.post("/api/events/{slug}/activate")
def activate_event(
    slug: str,
    x_admin_password: str = Header(None)
):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    supabase = get_supabase()

    event_result = (
        supabase
        .table("events")
        .select("id, slug, location_id")
        .eq("slug", slug)
        .limit(1)
        .execute()
    )

    if not event_result.data:
        raise HTTPException(
            status_code=404,
            detail="Eveniment negăsit."
        )

    event = event_result.data[0]
    location_id = event["location_id"]

    if not location_id:
        raise HTTPException(
            status_code=400,
            detail="Evenimentul nu este asociat unei locații."
        )

    (
        supabase
        .table("events")
        .update({"status": "archived"})
        .eq("location_id", location_id)
        .eq("status", "active")
        .execute()
    )

    (
        supabase
        .table("events")
        .update({"status": "active"})
        .eq("id", event["id"])
        .execute()
    )

    return {
        "success": True,
        "slug": slug
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