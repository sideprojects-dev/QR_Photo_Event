import io as io_module
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from googleapiclient.http import MediaIoBaseDownload

from deps import get_supabase
from google_drive import get_drive_service, upload_file_to_drive

router = APIRouter(tags=["media"])


def get_event_by_slug(supabase, slug: str):
    result = (
        supabase
        .table("events")
        .select("id, folder_id")
        .eq("slug", slug)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="Eveniment negăsit."
        )

    return result.data[0]


def save_media_record(
    supabase,
    event_id: int,
    drive_file_id: str,
    file_name: str,
    content_type: str,
    size_bytes: int | None
):
    result = (
        supabase
        .table("media")
        .insert({
            "event_id": event_id,
            "drive_file_id": drive_file_id,
            "file_name": file_name,
            "content_type": content_type,
            "size_bytes": size_bytes
        })
        .execute()
    )

    return result.data[0] if result.data else None


def get_event_media(
    supabase,
    event_id: int,
    limit: int,
    offset: int
):
    result = (
        supabase
        .table("media")
        .select(
            "id, event_id, drive_file_id, file_name, "
            "content_type, size_bytes, created_at"
        )
        .eq("event_id", event_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit)
        .execute()
    )

    items = result.data or []

    has_more = len(items) > limit

    if has_more:
        items = items[:limit]

    return items, has_more


@router.get("/api/events/{slug}/media")
def get_event_media_endpoint(
    slug: str,
    limit: int = 30,
    offset: int = 0
):
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 100."
        )

    if offset < 0:
        raise HTTPException(
            status_code=400,
            detail="Offset cannot be negative."
        )

    supabase = get_supabase()

    event = get_event_by_slug(
        supabase=supabase,
        slug=slug
    )

    items, has_more = get_event_media(
        supabase=supabase,
        event_id=event["id"],
        limit=limit,
        offset=offset
    )

    return {
        "items": items,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None
        }
    }


def get_media_by_id(supabase, media_id: str):
    result = (
        supabase
        .table("media")
        .select(
            "id, event_id, drive_file_id, file_name, "
            "content_type, size_bytes, created_at"
        )
        .eq("id", media_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="Media not found."
        )

    return result.data[0]


@router.get("/media/{media_id}")
def stream_media(media_id: str):
    supabase = get_supabase()
    media_record = get_media_by_id(
        supabase=supabase,
        media_id=media_id
    )

    drive = get_drive_service()

    request = drive.files().get_media(
        fileId=media_record["drive_file_id"]
    )

    buffer = io_module.BytesIO()

    downloader = MediaIoBaseDownload(
        buffer,
        request
    )

    done = False

    while not done:
        _, done = downloader.next_chunk()

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type=media_record["content_type"],
        headers={
            "Content-Disposition":
                f'inline; filename="{media_record["file_name"]}"'
        }
    )


@router.post("/upload/{slug}")
async def upload(
    slug: str,
    file: UploadFile = File(...)
):
    if not file.content_type or not file.content_type.startswith(("image/", "video/")):
        raise HTTPException(
            status_code=400,
            detail="Only image and video files are allowed."
        )

    supabase = get_supabase()
    event = get_event_by_slug(supabase, slug)

    extension = os.path.splitext(file.filename or "")[1]

    unique_name = (
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
        f"{uuid.uuid4().hex[:6]}{extension}"
    )

    await file.seek(0)

    file_size = None

    try:
        current_position = file.file.tell()
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        file.file.seek(current_position)
    except Exception:
        file_size = None

    drive = get_drive_service()
    drive_file_id = None

    try:
        drive_file_id = upload_file_to_drive(
            drive=drive,
            file=file,
            file_name=unique_name,
            folder_id=event["folder_id"]
        )

        save_media_record(
            supabase=supabase,
            event_id=event["id"],
            drive_file_id=drive_file_id,
            file_name=unique_name,
            content_type=file.content_type,
            size_bytes=file_size
        )

    except Exception:
        if drive_file_id:
            try:
                drive.files().delete(
                    fileId=drive_file_id
                ).execute()
            except Exception:
                pass

        raise

    return {
        "success": True,
        "media": {
            "drive_file_id": drive_file_id,
            "file_name": unique_name,
            "content_type": file.content_type,
            "size_bytes": file_size
        }
    }
