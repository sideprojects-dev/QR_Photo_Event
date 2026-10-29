import io as io_module
import os
import uuid
import warnings
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from PIL import Image, ImageOps

from deps import get_supabase
from perf_monitor import PerfTrace
from guest_access import has_event_access
from google_drive import (
    get_drive_service,
    get_drive_file_size,
    download_file_range,
    get_or_create_child_folder,
    upload_bytes_to_drive,
    upload_file_to_drive
)
from upload_limits import MAX_IMAGE_BYTES, MAX_VIDEO_BYTES

router = APIRouter(tags=["media"])
STREAM_CHUNK_BYTES = 1024 * 1024

THUMBNAIL_FOLDER_NAME = "_thumbnails"
PREVIEW_FOLDER_NAME = "_previews"

THUMBNAIL_MAX_SIZE = (600, 600)
PREVIEW_MAX_SIZE = (1600, 1600)

THUMBNAIL_JPEG_QUALITY = 82
PREVIEW_JPEG_QUALITY = 90
VIDEO_HEADER_BYTES = 4096
IMAGE_FORMAT_BY_MIME = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
VIDEO_MIME_TYPES = ("video/mp4", "video/webm")
EXTENSION_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}


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

    record = result.data[0] if result.data else None
    return record if valid_saved_media(record, event_id, drive_file_id) else None


def valid_saved_media(record, event_id, drive_file_id: str) -> bool:
    return (
        isinstance(record, dict)
        and bool(record.get("id"))
        and str(record.get("event_id")) == str(event_id)
        and record.get("drive_file_id") == drive_file_id
    )


def find_saved_media(supabase, event_id, drive_file_id: str):
    result = (
        supabase.table("media")
        .select("id, event_id, drive_file_id, content_type, created_at")
        .eq("drive_file_id", drive_file_id).limit(2).execute()
    )
    records = result.data or []
    if not records:
        return None
    if len(records) != 1 or not valid_saved_media(records[0], event_id, drive_file_id):
        raise RuntimeError("Media insert result could not be verified")
    return records[0]


def cleanup_created_drive_files(drive, file_ids) -> bool:
    cleaned = True
    for file_id in dict.fromkeys(file_id for file_id in file_ids if file_id):
        try:
            drive.files().delete(fileId=file_id).execute()
        except Exception:
            cleaned = False
    return cleaned


def get_event_media(
    supabase,
    event_id: int,
    limit: int,
    offset: int
):
    result = (
        supabase
        .table("media")
        .select("id, content_type, created_at")
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


def public_media_record(record):
    return {
        key: record[key]
        for key in ("id", "content_type", "created_at")
        if key in record
    }


@router.get("/api/events/{slug}/media")
def get_event_media_endpoint(
    slug: str,
    response: Response,
    limit: int = 30,
    offset: int = 0,
    access: str | None = None
):
    trace = PerfTrace("gallery_list")
    outcome = "error"
    try:
        result = _get_event_media_response(slug, response, limit, offset, access, trace)
        outcome = "ok"
        return result
    finally:
        trace.emit(outcome)


def _get_event_media_response(slug, response, limit, offset, access, trace):
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
    with trace.step("event_lookup"):
        event = get_event_by_slug(supabase, slug)
    with trace.step("access_check"):
        if not has_event_access(event["id"], access):
            raise HTTPException(status_code=404, detail="Eveniment negăsit.")

    with trace.step("media_list"):
        items, has_more = get_event_media(
            supabase=supabase,
            event_id=event["id"],
            limit=limit,
            offset=offset
        )

    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"

    return {
        "items": [public_media_record(item) for item in items],
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


def get_accessible_media(supabase, media_id: str, access: str | None, trace=None):
    if trace is None:
        record = get_media_by_id(supabase, media_id)
        allowed = has_event_access(record["event_id"], access)
    else:
        with trace.step("media_lookup"):
            record = get_media_by_id(supabase, media_id)
        with trace.step("access_check"):
            allowed = has_event_access(record["event_id"], access)
    if not allowed:
        raise HTTPException(status_code=404, detail="Media not found.")
    return record


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


def validate_image_content(file_bytes: bytes, content_type: str) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io_module.BytesIO(file_bytes)) as image:
            if image.format != IMAGE_FORMAT_BY_MIME[content_type]:
                raise ValueError("Image format does not match the declared MIME type")
            image.load()


def validate_video_header(header: bytes, content_type: str) -> None:
    if content_type == "video/mp4":
        valid = (
            len(header) >= 16
            and header[4:8] == b"ftyp"
            and int.from_bytes(header[:4], "big") >= 16
        )
    else:
        valid = (
            header.startswith(b"\x1a\x45\xdf\xa3")
            and b"\x42\x82\x84webm" in header
        )

    if not valid:
        raise HTTPException(
            status_code=400,
            detail="Invalid video container header."
        )


def iter_drive_range(
    drive_file_id: str, start: int, end: int,
    trace_id: str | None = None
):
    """Request only bounded ranges; no Drive response is kept between yields."""
    trace = PerfTrace("media_stream", trace_id=trace_id)
    outcome = "interrupted"
    try:
        for offset in range(start, end + 1, STREAM_CHUNK_BYTES):
            chunk_end = min(offset + STREAM_CHUNK_BYTES - 1, end)
            # StreamingResponse may advance the iterator on another worker thread.
            # Drive clients are thread-local, so acquire one on that thread.
            with trace.step("drive_fetch"):
                chunk = download_file_range(
                    get_drive_service(), drive_file_id, offset, chunk_end
                )
            if len(chunk) != chunk_end - offset + 1:
                raise RuntimeError("Google Drive returned an incomplete media range")
            yield chunk
        outcome = "ok"
    except Exception:
        outcome = "error"
        raise
    finally:
        trace.emit(outcome)


def stream_drive_file(
    drive,
    drive_file_id: str,
    media_type: str,
    content_disposition: str | None = None,
    range_header: str | None = None,
    file_size: int | None = None,
    trace: PerfTrace | None = None,
):
    if file_size is None:
        if trace is None:
            file_size = get_drive_file_size(drive, drive_file_id)
        else:
            with trace.step("drive_metadata"):
                file_size = get_drive_file_size(drive, drive_file_id)
    file_size = int(file_size)
    start, end = (parse_byte_range(range_header, file_size)
                  if range_header else (0, file_size - 1))
    headers = {
        "Cache-Control": "private, no-store",
        "X-Robots-Tag": "noindex, nofollow",
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1 if file_size else 0),
    }
    if content_disposition:
        headers["Content-Disposition"] = content_disposition
    if range_header:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    return StreamingResponse(
        iter_drive_range(
            drive_file_id, start, end, trace_id=trace.trace_id if trace else None
        ) if file_size else iter(()),
        status_code=206 if range_header else 200,
        media_type=media_type,
        headers=headers,
    )


@router.get("/media/{media_id}/thumbnail")
def stream_media_thumbnail(media_id: str, access: str | None = None):
    trace = PerfTrace("thumbnail_prepare")
    outcome = "error"
    try:
        result = _stream_media_thumbnail(media_id, access, trace)
        outcome = "ok"
        return result
    finally:
        trace.emit(outcome)


def _stream_media_thumbnail(media_id, access, trace):
    supabase = get_supabase()
    media_record = get_accessible_media(
        supabase=supabase,
        media_id=media_id,
        access=access,
        trace=trace
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
            trace=trace
        )

    return stream_drive_file(
        drive=drive,
        drive_file_id=media_record["drive_file_id"],
        media_type=media_record["content_type"],
        trace=trace
    )


@router.get("/media/{media_id}/preview")
def stream_media_preview(media_id: str, access: str | None = None):
    trace = PerfTrace("preview_prepare")
    outcome = "error"
    try:
        result = _stream_media_preview(media_id, access, trace)
        outcome = "ok"
        return result
    finally:
        trace.emit(outcome)


def _stream_media_preview(media_id, access, trace):
    supabase = get_supabase()
    media_record = get_accessible_media(
        supabase=supabase,
        media_id=media_id,
        access=access,
        trace=trace
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
            trace=trace
        )

    return stream_drive_file(
        drive=drive,
        drive_file_id=media_record["drive_file_id"],
        media_type=media_record["content_type"],
        trace=trace
    )


@router.get("/media/{media_id}/download")
def download_media(media_id: str, access: str | None = None):
    supabase = get_supabase()
    media_record = get_accessible_media(
        supabase=supabase,
        media_id=media_id,
        access=access
    )

    drive = get_drive_service()

    return stream_drive_file(
        drive=drive,
        drive_file_id=media_record["drive_file_id"],
        media_type=media_record["content_type"],
        content_disposition=(
            f'attachment; filename="{media_record["file_name"]}"'
        )
    )




def parse_byte_range(
    range_header: str,
    file_size: int
) -> tuple[int, int]:
    unsatisfiable = HTTPException(
        status_code=416, detail="Requested range is not satisfiable.",
        headers={"Content-Range": f"bytes */{file_size}",
                 "Accept-Ranges": "bytes"},
    )
    if not range_header.startswith("bytes=") or file_size <= 0:
        raise unsatisfiable

    range_value = range_header.removeprefix("bytes=").strip()

    if "," in range_value:
        raise unsatisfiable

    start_text, separator, end_text = range_value.partition("-")

    if not separator:
        raise unsatisfiable

    try:
        if start_text:
            if not start_text.isdecimal():
                raise ValueError
            start = int(start_text)

            if start < 0 or start >= file_size:
                raise ValueError

            if end_text:
                if not end_text.isdecimal():
                    raise ValueError
                end = int(end_text)
            else:
                end = file_size - 1
        else:
            # Suffix range, e.g. bytes=-500
            if not end_text.isdecimal():
                raise ValueError
            suffix_length = int(end_text)

            if suffix_length <= 0:
                raise ValueError

            suffix_length = min(
                suffix_length,
                file_size
            )

            start = file_size - suffix_length
            end = file_size - 1

        end = min(
            end,
            file_size - 1
        )

        if end < start:
            raise ValueError

    except (TypeError, ValueError):
        raise unsatisfiable

    return start, end


def stream_video_with_range(
    request: Request,
    drive,
    media_record
):
    file_size = media_record.get(
        "size_bytes"
    )

    if not file_size:
        file_size = get_drive_file_size(
            drive=drive,
            drive_file_id=media_record["drive_file_id"]
        )

    file_size = int(file_size)
    range_header = request.headers.get("range")

    return stream_drive_file(
        drive=drive,
        drive_file_id=media_record["drive_file_id"],
        media_type=media_record["content_type"],
        content_disposition=f'inline; filename="{media_record["file_name"]}"',
        range_header=range_header,
        file_size=file_size,
    )


@router.get("/media/{media_id}")
def stream_media(
    media_id: str,
    request: Request,
    access: str | None = None
):
    supabase = get_supabase()
    media_record = get_accessible_media(
        supabase=supabase,
        media_id=media_id,
        access=access
    )

    drive = get_drive_service()

    if media_record["content_type"].startswith("video/"):
        return stream_video_with_range(
            request=request,
            drive=drive,
            media_record=media_record
        )

    return stream_drive_file(
        drive=drive,
        drive_file_id=media_record["drive_file_id"],
        media_type=media_record["content_type"],
        content_disposition=(
            f'inline; filename="{media_record["file_name"]}"'
        )
    )


@router.post("/upload/{slug}")
def upload(
    slug: str,
    request: Request,
    file: UploadFile = File(...),
    access: str | None = None
):
    trace = PerfTrace(
        "photo_upload" if file.content_type and file.content_type.startswith("image/") else "video_upload",
        trace_id=request.scope.get("state", {}).get("perf_trace_id")
    )
    outcome = "error"
    try:
        result = _process_upload(slug, file, access, trace)
        outcome = "ok"
        return result
    finally:
        trace.emit(outcome)


def _process_upload(slug, file, access, trace):
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

    if (
        file.content_type.startswith("image/")
        and file.content_type not in IMAGE_FORMAT_BY_MIME
    ):
        raise HTTPException(
            status_code=400,
            detail="Only JPEG, PNG and WebP images are supported."
        )

    if (
        file.content_type.startswith("video/")
        and file.content_type not in VIDEO_MIME_TYPES
    ):
        raise HTTPException(
            status_code=400,
            detail="Only MP4 and WebM videos are supported."
        )

    supabase = get_supabase()
    with trace.step("event_lookup"):
        event = get_event_by_slug(supabase, slug)
    with trace.step("access_check"):
        if not has_event_access(event["id"], access):
            raise HTTPException(status_code=404, detail="Eveniment negăsit.")

    extension = EXTENSION_BY_MIME[file.content_type]

    unique_name = (
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
        f"{uuid.uuid4().hex[:6]}{extension}"
    )

    file.file.seek(0)

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
            file.file.seek(0)
            with trace.step("image_read"):
                image_bytes = file.file.read(MAX_IMAGE_BYTES + 1)

            if len(image_bytes) > MAX_IMAGE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Image exceeds the 25 MB limit."
                )

            with trace.step("image_decode_validate"):
                validate_image_content(image_bytes, file.content_type)

            with trace.step("thumbnail_generate"):
                thumbnail_bytes = create_image_thumbnail(image_bytes)

            with trace.step("preview_generate"):
                preview_bytes = create_image_preview(image_bytes)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid image file."
            ) from exc
        finally:
            file.file.seek(0)

    if file.content_type.startswith("video/"):
        if file_size is None:
            raise HTTPException(
                status_code=400,
                detail="Could not determine video size."
            )
        if file_size > MAX_VIDEO_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Video exceeds the 250 MB limit."
            )

        file.file.seek(0)
        try:
            header = file.file.read(VIDEO_HEADER_BYTES)
        finally:
            file.file.seek(0)
        validate_video_header(header, file.content_type)

    drive = get_drive_service()

    drive_file_id = None
    thumbnail_drive_file_id = None
    preview_drive_file_id = None

    try:
        with trace.step("drive_original_upload"):
            drive_file_id = upload_file_to_drive(
                drive=drive,
                file=file,
                file_name=unique_name,
                folder_id=event["folder_id"]
            )
        if not drive_file_id:
            raise RuntimeError("Drive did not return a file ID")

        if thumbnail_bytes:
            try:
                with trace.step("drive_thumbnail_folder"):
                    thumbnail_folder_id = get_or_create_child_folder(
                        drive=drive,
                        parent_folder_id=event["folder_id"],
                        folder_name=THUMBNAIL_FOLDER_NAME
                    )

                with trace.step("drive_thumbnail_upload"):
                    thumbnail_drive_file_id = upload_bytes_to_drive(
                        drive=drive,
                        data=thumbnail_bytes,
                        file_name=(
                            "thumb_"
                            f"{os.path.splitext(unique_name)[0]}.jpg"
                        ),
                        folder_id=thumbnail_folder_id,
                        mimetype="image/jpeg"
                    )
            except Exception as exc:
                print(
                    "Thumbnail upload failed:",
                    repr(exc),
                    flush=True
                )

        if preview_bytes:
            try:
                with trace.step("drive_preview_folder"):
                    preview_folder_id = get_or_create_child_folder(
                        drive=drive,
                        parent_folder_id=event["folder_id"],
                        folder_name=PREVIEW_FOLDER_NAME
                    )

                with trace.step("drive_preview_upload"):
                    preview_drive_file_id = upload_bytes_to_drive(
                        drive=drive,
                        data=preview_bytes,
                        file_name=(
                            "preview_"
                            f"{os.path.splitext(unique_name)[0]}.jpg"
                        ),
                        folder_id=preview_folder_id,
                        mimetype="image/jpeg"
                    )
            except Exception as exc:
                print(
                    "Preview upload failed:",
                    repr(exc),
                    flush=True
                )

    except Exception as exc:
        cleaned = cleanup_created_drive_files(
            drive, (preview_drive_file_id, thumbnail_drive_file_id, drive_file_id)
        )
        detail = (
            "Încărcarea a eșuat; curățarea fișierelor din Drive necesită verificare manuală."
            if not cleaned else "Încărcarea fișierului a eșuat."
        )
        raise HTTPException(status_code=503, detail=detail) from exc

    try:
        with trace.step("supabase_media_insert"):
            media_record = save_media_record(
                supabase=supabase,
                event_id=event["id"],
                drive_file_id=drive_file_id,
                thumbnail_drive_file_id=thumbnail_drive_file_id,
                preview_drive_file_id=preview_drive_file_id,
                file_name=unique_name,
                content_type=file.content_type,
                size_bytes=file_size,
            )
    except Exception:
        media_record = None

    if media_record is None:
        try:
            with trace.step("supabase_media_verify"):
                media_record = find_saved_media(supabase, event["id"], drive_file_id)
        except Exception as exc:
            # The insert may have committed despite a failed response. Never
            # delete a Drive file while its database state is unknown.
            raise HTTPException(
                status_code=503,
                detail="Rezultatul salvării este neclar. Verifică manual Drive și baza de date."
            ) from exc
        if media_record is None:
            cleaned = cleanup_created_drive_files(
                drive, (preview_drive_file_id, thumbnail_drive_file_id, drive_file_id)
            )
            detail = (
                "Salvarea a eșuat; curățarea din Drive necesită verificare manuală."
                if not cleaned else "Salvarea materialului a eșuat."
            )
            raise HTTPException(status_code=503, detail=detail)

    return {
        "success": True,
        "media": public_media_record(media_record)
    }
