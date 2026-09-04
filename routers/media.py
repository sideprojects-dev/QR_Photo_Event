import io as io_module
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from googleapiclient.http import MediaIoBaseDownload
from PIL import Image, ImageOps

from deps import get_supabase
from google_drive import (
    get_drive_service,
    get_or_create_child_folder,
    upload_bytes_to_drive,
    upload_file_to_drive
)

router = APIRouter(tags=["media"])

THUMBNAIL_FOLDER_NAME = "_thumbnails"
PREVIEW_FOLDER_NAME = "_previews"

THUMBNAIL_MAX_SIZE = (600, 600)
PREVIEW_MAX_SIZE = (1600, 1600)

THUMBNAIL_JPEG_QUALITY = 82
PREVIEW_JPEG_QUALITY = 90


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
    thumbnail_drive_file_id: str | None,
    preview_drive_file_id: str | None,
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
            "thumbnail_drive_file_id": thumbnail_drive_file_id,
            "preview_drive_file_id": preview_drive_file_id,
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
            "id, event_id, drive_file_id, thumbnail_drive_file_id, "
            "preview_drive_file_id, file_name, content_type, "
            "size_bytes, created_at"
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
    event = get_event_by_slug(supabase, slug)

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
            "id, event_id, drive_file_id, thumbnail_drive_file_id, "
            "preview_drive_file_id, file_name, content_type, "
            "size_bytes, created_at"
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


def create_image_variant(
    file_bytes: bytes,
    max_size: tuple[int, int],
    quality: int
) -> bytes:
    input_buffer = io_module.BytesIO(file_bytes)

    with Image.open(input_buffer) as image:
        image = ImageOps.exif_transpose(image)

        image.thumbnail(
            max_size,
            Image.Resampling.LANCZOS
        )

        if image.mode != "RGB":
            image = image.convert("RGB")

        output_buffer = io_module.BytesIO()

        image.save(
            output_buffer,
            format="JPEG",
            quality=quality,
            optimize=True
        )

        return output_buffer.getvalue()


def create_image_thumbnail(file_bytes: bytes) -> bytes:
    return create_image_variant(
        file_bytes=file_bytes,
        max_size=THUMBNAIL_MAX_SIZE,
        quality=THUMBNAIL_JPEG_QUALITY
    )


def create_image_preview(file_bytes: bytes) -> bytes:
    return create_image_variant(
        file_bytes=file_bytes,
        max_size=PREVIEW_MAX_SIZE,
        quality=PREVIEW_JPEG_QUALITY
    )


def download_drive_file_to_buffer(
    drive,
    drive_file_id: str
):
    request = drive.files().get_media(
        fileId=drive_file_id
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
    return buffer


def stream_drive_file(
    drive,
    drive_file_id: str,
    media_type: str,
    cache_seconds: int,
    content_disposition: str | None = None
):
    buffer = download_drive_file_to_buffer(
        drive=drive,
        drive_file_id=drive_file_id
    )

    headers = {
        "Cache-Control":
            f"public, max-age={cache_seconds}"
    }

    if content_disposition:
        headers["Content-Disposition"] = content_disposition

    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers=headers
    )


@router.get("/media/{media_id}/thumbnail")
def stream_media_thumbnail(media_id: str):
    supabase = get_supabase()
    media_record = get_media_by_id(
        supabase=supabase,
        media_id=media_id
    )

    if not media_record["content_type"].startswith("image/"):
        raise HTTPException(
            status_code=404,
            detail="Thumbnail not available for this media."
        )

    thumbnail_drive_file_id = media_record.get(
        "thumbnail_drive_file_id"
    )

    drive = get_drive_service()

    if thumbnail_drive_file_id:
        return stream_drive_file(
            drive=drive,
            drive_file_id=thumbnail_drive_file_id,
            media_type="image/jpeg",
            cache_seconds=86400
        )

    return stream_drive_file(
        drive=drive,
        drive_file_id=media_record["drive_file_id"],
        media_type=media_record["content_type"],
        cache_seconds=3600
    )


@router.get("/media/{media_id}/preview")
def stream_media_preview(media_id: str):
    supabase = get_supabase()
    media_record = get_media_by_id(
        supabase=supabase,
        media_id=media_id
    )

    if not media_record["content_type"].startswith("image/"):
        raise HTTPException(
            status_code=404,
            detail="Preview not available for this media."
        )

    preview_drive_file_id = media_record.get(
        "preview_drive_file_id"
    )

    drive = get_drive_service()

    if preview_drive_file_id:
        return stream_drive_file(
            drive=drive,
            drive_file_id=preview_drive_file_id,
            media_type="image/jpeg",
            cache_seconds=86400
        )

    return stream_drive_file(
        drive=drive,
        drive_file_id=media_record["drive_file_id"],
        media_type=media_record["content_type"],
        cache_seconds=3600
    )


@router.get("/media/{media_id}/download")
def download_media(media_id: str):
    supabase = get_supabase()
    media_record = get_media_by_id(
        supabase=supabase,
        media_id=media_id
    )

    drive = get_drive_service()

    return stream_drive_file(
        drive=drive,
        drive_file_id=media_record["drive_file_id"],
        media_type=media_record["content_type"],
        cache_seconds=3600,
        content_disposition=(
            f'attachment; filename="{media_record["file_name"]}"'
        )
    )


@router.get("/media/{media_id}")
def stream_media(media_id: str):
    supabase = get_supabase()
    media_record = get_media_by_id(
        supabase=supabase,
        media_id=media_id
    )

    drive = get_drive_service()

    return stream_drive_file(
        drive=drive,
        drive_file_id=media_record["drive_file_id"],
        media_type=media_record["content_type"],
        cache_seconds=3600,
        content_disposition=(
            f'inline; filename="{media_record["file_name"]}"'
        )
    )


@router.post("/upload/{slug}")
async def upload(
    slug: str,
    file: UploadFile = File(...)
):
    if (
        not file.content_type
        or not file.content_type.startswith(
            ("image/", "video/")
        )
    ):
        raise HTTPException(
            status_code=400,
            detail="Only image and video files are allowed."
        )

    supabase = get_supabase()
    event = get_event_by_slug(
        supabase,
        slug
    )

    extension = os.path.splitext(
        file.filename or ""
    )[1]

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

    thumbnail_bytes = None
    preview_bytes = None

    if file.content_type.startswith("image/"):
        try:
            await file.seek(0)
            image_bytes = await file.read()

            thumbnail_bytes = create_image_thumbnail(
                image_bytes
            )

            preview_bytes = create_image_preview(
                image_bytes
            )
        except Exception as exc:
            print(
                "Image derivative generation failed:",
                repr(exc),
                "content_type:",
                file.content_type,
                "filename:",
                file.filename,
                flush=True
            )
        finally:
            await file.seek(0)

    drive = get_drive_service()

    drive_file_id = None
    thumbnail_drive_file_id = None
    preview_drive_file_id = None

    try:
        drive_file_id = upload_file_to_drive(
            drive=drive,
            file=file,
            file_name=unique_name,
            folder_id=event["folder_id"]
        )

        if thumbnail_bytes:
            try:
                thumbnail_folder_id = (
                    get_or_create_child_folder(
                        drive=drive,
                        parent_folder_id=event["folder_id"],
                        folder_name=THUMBNAIL_FOLDER_NAME
                    )
                )

                thumbnail_drive_file_id = (
                    upload_bytes_to_drive(
                        drive=drive,
                        data=thumbnail_bytes,
                        file_name=(
                            "thumb_"
                            f"{os.path.splitext(unique_name)[0]}.jpg"
                        ),
                        folder_id=thumbnail_folder_id,
                        mimetype="image/jpeg"
                    )
                )
            except Exception as exc:
                print(
                    "Thumbnail upload failed:",
                    repr(exc),
                    flush=True
                )

        if preview_bytes:
            try:
                preview_folder_id = (
                    get_or_create_child_folder(
                        drive=drive,
                        parent_folder_id=event["folder_id"],
                        folder_name=PREVIEW_FOLDER_NAME
                    )
                )

                preview_drive_file_id = (
                    upload_bytes_to_drive(
                        drive=drive,
                        data=preview_bytes,
                        file_name=(
                            "preview_"
                            f"{os.path.splitext(unique_name)[0]}.jpg"
                        ),
                        folder_id=preview_folder_id,
                        mimetype="image/jpeg"
                    )
                )
            except Exception as exc:
                print(
                    "Preview upload failed:",
                    repr(exc),
                    flush=True
                )

        media_record = save_media_record(
            supabase=supabase,
            event_id=event["id"],
            drive_file_id=drive_file_id,
            thumbnail_drive_file_id=(
                thumbnail_drive_file_id
            ),
            preview_drive_file_id=(
                preview_drive_file_id
            ),
            file_name=unique_name,
            content_type=file.content_type,
            size_bytes=file_size
        )

    except Exception:
        for created_file_id in (
            preview_drive_file_id,
            thumbnail_drive_file_id,
            drive_file_id
        ):
            if not created_file_id:
                continue

            try:
                drive.files().delete(
                    fileId=created_file_id
                ).execute()
            except Exception:
                pass

        raise

    return {
        "success": True,
        "media": media_record or {
            "drive_file_id": drive_file_id,
            "thumbnail_drive_file_id":
                thumbnail_drive_file_id,
            "preview_drive_file_id":
                preview_drive_file_id,
            "file_name": unique_name,
            "content_type": file.content_type,
            "size_bytes": file_size
        }
    }
