"""Administrative media listing and recoverable removal."""

from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Response
from googleapiclient.errors import HttpError

from deps import count_rows, get_supabase, require_admin
from google_drive import get_drive_service


router = APIRouter(prefix="/api/admin", tags=["admin-media"], dependencies=[Depends(require_admin)])
MEDIA_FIELDS = (
    "id, event_id, drive_file_id, thumbnail_drive_file_id, "
    "preview_drive_file_id, file_name, content_type, size_bytes, created_at"
)
LIST_FIELDS = "id, file_name, content_type, size_bytes, created_at"
_DELETE_LOCKS = tuple(Lock() for _ in range(64))


def event_for_admin(supabase, slug: str):
    result = (
        supabase.table("events").select("id, name, slug")
        .eq("slug", slug).limit(1).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Evenimentul nu a fost găsit.")
    return result.data[0]


@router.get("/stats")
def admin_stats(response: Response):
    try:
        supabase = get_supabase()
        stats = {
            "locations": count_rows(supabase, "locations"),
            "active_events": count_rows(supabase, "events", (("status", "active"),)),
            "archived_events": count_rows(supabase, "events", (("status", "archived"),)),
            "photos": count_rows(supabase, "media", media_kind="image"),
            "videos": count_rows(supabase, "media", media_kind="video"),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Statisticile nu au putut fi încărcate.") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return stats


@router.get("/events/{slug}/media")
def list_admin_media(
    slug: str,
    response: Response,
    kind: str = "all",
    sort: str = "newest",
    limit: int = 30,
    offset: int = 0,
):
    if kind not in ("all", "image", "video") or sort not in ("newest", "oldest"):
        raise HTTPException(status_code=400, detail="Filtru sau sortare invalidă.")
    if limit < 1 or limit > 100 or offset < 0:
        raise HTTPException(status_code=400, detail="Paginare invalidă.")
    try:
        supabase = get_supabase()
        event = event_for_admin(supabase, slug)
        query = (
            supabase.table("media").select(LIST_FIELDS)
            .eq("event_id", event["id"])
        )
        if kind != "all":
            query = query.like("content_type", f"{kind}/%")
        descending = sort == "newest"
        result = (
            query.order("created_at", desc=descending)
            .order("id", desc=descending)
            .range(offset, offset + limit)
            .execute()
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Materialele nu au putut fi încărcate.") from exc

    items = result.data or []
    has_more = len(items) > limit
    response.headers["Cache-Control"] = "private, no-store"
    return {
        "event": {"id": event["id"], "name": event["name"], "slug": event["slug"]},
        "items": items[:limit],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
        },
    }


def _is_missing_drive_file(exc: HttpError) -> bool:
    return getattr(getattr(exc, "resp", None), "status", None) == 404


def _restore_trashed(drive, file_ids: list[str]) -> bool:
    restored = True
    for file_id in reversed(file_ids):
        try:
            drive.files().update(
                fileId=file_id, body={"trashed": False}, fields="id"
            ).execute()
        except Exception:
            restored = False
    return restored


@router.delete("/events/{slug}/media/{media_id}")
def delete_admin_media(slug: str, media_id: str, response: Response):
    # Serialize repeat requests within a worker, including the ownership check.
    with _DELETE_LOCKS[hash(media_id) % len(_DELETE_LOCKS)]:
        return _delete_admin_media_locked(slug, media_id, response)


def _delete_admin_media_locked(slug: str, media_id: str, response: Response):
    try:
        supabase = get_supabase()
        event = event_for_admin(supabase, slug)
        record_result = (
            supabase.table("media").select(MEDIA_FIELDS)
            .eq("id", media_id).eq("event_id", event["id"])
            .limit(1).execute()
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Materialul nu a putut fi verificat.") from exc
    if not record_result.data:
        raise HTTPException(status_code=404, detail="Materialul nu există în acest eveniment.")

    record = record_result.data[0]
    file_ids = list(dict.fromkeys(
        file_id for file_id in (
            record.get("drive_file_id"),
            record.get("thumbnail_drive_file_id"),
            record.get("preview_drive_file_id"),
        ) if file_id
    ))
    newly_trashed = []
    try:
        drive = get_drive_service()
        for file_id in file_ids:
            try:
                metadata = drive.files().get(fileId=file_id, fields="trashed").execute()
            except HttpError as exc:
                if _is_missing_drive_file(exc):
                    continue
                raise
            if metadata.get("trashed"):
                continue
            drive.files().update(
                fileId=file_id, body={"trashed": True}, fields="id"
            ).execute()
            newly_trashed.append(file_id)
    except Exception as exc:
        restored = _restore_trashed(drive, newly_trashed) if newly_trashed else True
        detail = (
            "Ștergerea din Drive a eșuat; restaurarea necesită verificare manuală."
            if not restored else "Ștergerea din Drive a eșuat. Materialul a fost păstrat."
        )
        raise HTTPException(status_code=503, detail=detail) from exc

    try:
        deleted = (
            supabase.table("media").delete()
            .eq("id", media_id).eq("event_id", event["id"])
            .execute()
        )
    except Exception as exc:
        try:
            still_present = (
                supabase.table("media").select("id")
                .eq("id", media_id).eq("event_id", event["id"])
                .limit(1).execute()
            ).data
        except Exception as check_exc:
            raise HTTPException(
                status_code=503,
                detail="Rezultatul ștergerii din baza de date este neclar. Verifică manual materialul și Coșul Drive."
            ) from check_exc
        if not still_present:
            response.headers["Cache-Control"] = "private, no-store"
            return {"status": "deleted", "id": media_id}
        restored = _restore_trashed(drive, newly_trashed)
        detail = (
            "Baza de date nu a putut fi actualizată; restaurarea din Drive necesită verificare manuală."
            if not restored else "Baza de date nu a putut fi actualizată. Materialul a fost păstrat."
        )
        raise HTTPException(status_code=503, detail=detail) from exc

    response.headers["Cache-Control"] = "private, no-store"
    if not deleted.data:
        # Another request removed the row after our ownership check. Do not restore
        # files whose media record is already gone.
        return {"status": "already_deleted", "id": media_id}
    return {"status": "deleted", "id": media_id}
