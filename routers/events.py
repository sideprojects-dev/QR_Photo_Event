import os
import io as io_module
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
import qrcode

from deps import get_supabase, require_admin
from google_drive import get_drive_service

router = APIRouter(tags=["events"])


@router.get("/event/{slug}")
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

    # Aceeași problemă poate apărea și la CSS: unele browsere încorporate
    # (deschise prin scanarea QR-ului) țin în cache agresiv fișierele
    # statice, inclusiv style.css.
    style_version = int(os.path.getmtime("static/style.css"))
    html = html.replace(
        '<link rel="stylesheet" href="/static/style.css">',
        f'<link rel="stylesheet" href="/static/style.css?v={style_version}">'
    )

    # Inject slug into page so JavaScript knows where to upload
    html = html.replace("</body>", f'<script>window.EVENT_SLUG = "{slug}";</script></body>')
    return HTMLResponse(html)


@router.post("/api/create-event", dependencies=[Depends(require_admin)])
async def api_create_event(event_name: str, location_slug: str):
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


@router.post("/api/events/{slug}/activate", dependencies=[Depends(require_admin)])
def activate_event(slug: str):
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


@router.get("/api/events", dependencies=[Depends(require_admin)])
def get_events():
    supabase = get_supabase()
    result = supabase.table("events").select("*").execute()
    return {"events": result.data}


@router.get("/api/qr/{slug}")
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
