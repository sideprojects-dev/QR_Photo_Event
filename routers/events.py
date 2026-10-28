import os
import io as io_module
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse, Response
import qrcode

from deps import get_supabase, require_admin
from guest_access import absolute_guest_url, event_path, has_event_access
from google_drive import get_drive_service

router = APIRouter(tags=["events"])


@router.get("/event/{slug}")
def event_page(slug: str, access: str | None = None):
    supabase = get_supabase()

    result = (
        supabase
        .table("events")
        .select("id")
        .eq("slug", slug)
        .limit(1)
        .execute()
    )

    if not result.data:
        return HTMLResponse(
            "<h1>Eveniment negăsit</h1>",
            status_code=404
        )

    if not has_event_access(result.data[0]["id"], access):
        return HTMLResponse("<h1>Eveniment negăsit</h1>", status_code=404)

    with open(
        "static/index.html",
        "r",
        encoding="utf-8"
    ) as f:
        html = f.read()

    app_version = int(
        os.path.getmtime("static/js/app.js")
    )

    html = html.replace(
        '<script type="module" src="/static/js/app.js"></script>',
        f'<script type="module" src="/static/js/app.js?v={app_version}"></script>'
    )

    css_files = [
        "base.css",
        "camera.css",
        "gallery.css"
    ]

    for css_file in css_files:
        css_path = f"static/css/{css_file}"
        css_version = int(
            os.path.getmtime(css_path)
        )

        html = html.replace(
            f'href="/static/css/{css_file}"',
            f'href="/static/css/{css_file}?v={css_version}"'
        )

    event_slug_json = (
        json.dumps(slug)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    html = html.replace(
        "</body>",
        f'''
        <script>
            window.EVENT_SLUG = {event_slug_json};
            window.EVENT_ACCESS = {json.dumps(access)};
        </script>
        </body>
        '''
    )

    return HTMLResponse(html, headers={
        "Cache-Control": "private, no-store",
        "Referrer-Policy": "no-referrer",
        "X-Robots-Tag": "noindex, nofollow",
    })


@router.post("/api/create-event", dependencies=[Depends(require_admin)])
async def api_create_event(event_name: str, location_slug: str, request: Request, response: Response):
    event_name = event_name.strip()
    location_slug = location_slug.strip()

    if not event_name:
        raise HTTPException(
            status_code=400,
            detail="Event name is required."
        )

    slug = event_name.lower()
    slug = slug.replace(" & ", "-").replace(" ", "-")
    slug = ''.join(c for c in slug if c.isalnum() or c == '-')

    if not slug.strip('-') or slug == "master":
        raise HTTPException(
            status_code=400,
            detail="Event name cannot form a usable URL."
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

        # Keep the current Master QR destination until the new event exists.
        # Its activation below is one database transaction.
        result = (
            supabase
            .table("events")
            .insert({
                "slug": slug,
                "name": event_name,
                "folder_id": folder_id,
                "created_at": datetime.now().isoformat(),
                "status": "archived",
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

    if not result.data or not result.data[0].get("id"):
        raise HTTPException(
            status_code=503,
            detail="Rezultatul creării este neclar. Verifică evenimentul înainte de a reîncerca.",
        )

    try:
        activate_event_in_db(supabase, slug, location_slug)
    except HTTPException as exc:
        # The new row and Drive folder may already exist. Keep both, so that
        # an administrator can inspect and activate it without duplicating data.
        raise HTTPException(
            status_code=503,
            detail="Evenimentul a fost creat, dar activarea nu a putut fi confirmată. Reîncarcă lista.",
        ) from exc

    response.headers["Cache-Control"] = "private, no-store"
    return {
        "success": True,
        "slug": slug,
        "url": absolute_guest_url(request, event_path(slug, result.data[0]["id"])),
        "folder_id": folder_id,
        "location_id": location_id
    }


@router.post("/api/events/{slug}/activate", dependencies=[Depends(require_admin)])
def activate_event(slug: str, location_slug: str | None = None):
    supabase = get_supabase()
    activate_event_in_db(supabase, slug, location_slug)
    return {"success": True, "slug": slug}


def activate_event_in_db(supabase, slug: str, location_slug: str | None):
    try:
        result = supabase.rpc(
            "activate_event_atomic",
            {"p_event_slug": slug, "p_location_slug": location_slug},
        ).execute()
    except Exception as exc:
        if getattr(exc, "code", None) == "23505":
            raise HTTPException(
                status_code=409,
                detail="Alt eveniment a fost activat simultan. Reîncarcă lista.",
            ) from exc
        raise HTTPException(
            status_code=503,
            detail="Rezultatul activării nu a putut fi confirmat. Reîncarcă lista evenimentelor.",
        ) from exc

    outcome = result.data.get("result") if isinstance(result.data, dict) else None
    if outcome in ("event_not_found", "location_not_found", "location_mismatch"):
        raise HTTPException(status_code=404, detail="Evenimentul nu a fost găsit în locația indicată.")
    if outcome == "event_unbound":
        raise HTTPException(status_code=400, detail="Evenimentul nu este asociat unei locații.")
    if outcome not in ("activated", "already_active"):
        raise HTTPException(status_code=503, detail="Rezultatul activării nu a putut fi verificat.")

    return outcome


@router.get("/api/events", dependencies=[Depends(require_admin)])
def get_events():
    supabase = get_supabase()
    result = supabase.table("events").select("*").execute()
    return {"events": result.data}


@router.get("/api/qr/{slug}", dependencies=[Depends(require_admin)])
def get_qr(slug: str, request: Request):
    # Generate QR and return as image
    supabase = get_supabase()
    result = (
        supabase.table("events").select("id")
        .eq("slug", slug).limit(1).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Eveniment negăsit.")
    url = absolute_guest_url(request, event_path(slug, result.data[0]["id"]))
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io_module.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png", headers={"Content-Disposition": f"attachment; filename={slug}_qr.png"})
