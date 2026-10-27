import io

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, Response
from httpx import ConnectError
import qrcode

from config import FOLDER_ID
from deps import get_supabase, require_admin
from guest_access import absolute_guest_url, event_path, has_location_access, master_path
from google_drive import get_drive_service

router = APIRouter(tags=["locations"])


@router.get("/event/master")
def master_redirect():
    return HTMLResponse("<h1>Codul QR nu este disponibil</h1>", status_code=404)


@router.get("/event/master/{location_slug}")
def master_redirect_location(location_slug: str, access: str | None = None):
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
    if not has_location_access(location_id, access):
        return HTMLResponse("<h1>Locația nu a fost găsită</h1>", status_code=404)

    event_result = (
        supabase
        .table("events")
        .select("id, slug")
        .eq("location_id", location_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )

    if not event_result.data:
        return HTMLResponse("<h1>Niciun eveniment activ momentan la această locație</h1>", status_code=404)

    event = event_result.data[0]
    return RedirectResponse(
        event_path(event["slug"], event["id"]),
        headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"}
    )


@router.post("/api/locations", dependencies=[Depends(require_admin)])
async def create_location(location_name: str):
    location_name = location_name.strip()

    if not location_name:
        raise HTTPException(
            status_code=400,
            detail="Location name is required."
        )

    slug = location_name.lower()
    slug = slug.replace(" & ", "-").replace(" ", "-")
    slug = ''.join(c for c in slug if c.isalnum() or c == '-')

    if not slug.strip('-'):
        raise HTTPException(
            status_code=400,
            detail="Location name cannot form a usable URL."
        )

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


@router.get("/api/locations", dependencies=[Depends(require_admin)])
def get_locations():
    supabase = get_supabase()

    try:
        result = (
            supabase
            .table("locations")
            .select("*")
            .order("created_at", desc=False)
            .execute()
        )
    except ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Nu se poate conecta la Supabase. Verifică dacă proiectul "
                "este activ și dacă SUPABASE_URL din .env este corect."
            ),
        ) from exc

    return {
        "locations": result.data
    }


@router.get("/api/locations/{location_slug}/events", dependencies=[Depends(require_admin)])
def get_location_events(location_slug: str, response: Response):
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

    response.headers["Cache-Control"] = "private, no-store"
    return {
        "location": location,
        "events": [
            {**event, "guest_url": event_path(event["slug"], event["id"])}
            for event in events_result.data
        ]
    }


@router.get("/api/locations/{location_slug}/master-qr", dependencies=[Depends(require_admin)])
def get_location_master_qr(location_slug: str, request: Request):
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
        raise HTTPException(status_code=404, detail="Locația nu a fost găsită.")

    # QR-ul conține URL-ul permanent /event/master/{location_slug} — nu
    # depinde de niciun eveniment anume, deci nu se schimbă niciodată.
    url = absolute_guest_url(request, master_path(location_slug, location_result.data[0]["id"]))
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={location_slug}_master_qr.png"}
    )
