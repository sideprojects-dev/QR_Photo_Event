from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse

from config import FOLDER_ID
from deps import get_supabase, require_admin
from google_drive import get_drive_service

router = APIRouter(tags=["locations"])


@router.get("/event/master")
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


@router.get("/event/master/{location_slug}")
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


@router.get("/api/locations/{location_slug}/events", dependencies=[Depends(require_admin)])
def get_location_events(location_slug: str):
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
