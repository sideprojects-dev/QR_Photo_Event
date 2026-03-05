import os
import sys
import json
import qrcode
import tempfile
from datetime import datetime
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from supabase import create_client

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
BASE_URL = os.getenv("BASE_URL", "https://qr-photo-event.onrender.com")

def get_drive_service():
    token_json = os.getenv("token.json")
    creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)

def create_event(event_name: str):
    # Generate slug from name (ex: "Nunta Ana & Mihai" -> "nunta-ana-mihai")
    slug = event_name.lower()
    slug = slug.replace(" & ", "-").replace(" ", "-")
    slug = ''.join(c for c in slug if c.isalnum() or c == '-')

    print(f"Creating event: {event_name} (slug: {slug})")

    # 1. Create folder in Google Drive
    print("Creating Google Drive folder...")
    drive = get_drive_service()
    folder_metadata = {
        "name": event_name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    folder = drive.files().create(
        body=folder_metadata,
        fields="id, name"
    ).execute()
    folder_id = folder["id"]
    print(f"Folder created: {folder_id}")

    # 2. Save event to Supabase
    print("Saving event to Supabase...")
    supabase = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY")
    )
    supabase.table("events").insert({
        "slug": slug,
        "name": event_name,
        "folder_id": folder_id,
        "created_at": datetime.now().isoformat()
    }).execute()
    print("Event saved to database!")

    # 3. Generate QR code
    print("Generating QR code...")
    url = f"{BASE_URL}/event/{slug}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    filename = f"qr_{slug}.png"
    img.save(filename)

    print(f"\n Gata!")
    print(f"   Eveniment: {event_name}")
    print(f"   URL: {url}")
    print(f"   QR salvat: {filename}")
    print(f"   Folder Drive ID: {folder_id}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Utilizare: python create_event.py \"Nunta Ana & Mihai\"")
        sys.exit(1)
    create_event(sys.argv[1])