import io as io_module
import json
import os
import threading

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from config import SCOPES


_credentials_lock = threading.Lock()
_cached_credentials = None
_thread_local = threading.local()


def _load_credentials_from_environment():
    token_json = os.getenv("token.json")

    if not token_json:
        raise RuntimeError(
            "Google Drive credentials are missing. "
            "Please authenticate at /auth/login."
        )

    return Credentials.from_authorized_user_info(
        json.loads(token_json),
        SCOPES
    )


def _get_valid_credentials():
    global _cached_credentials

    with _credentials_lock:
        if _cached_credentials and _cached_credentials.valid:
            return _cached_credentials

        if _cached_credentials is None:
            _cached_credentials = _load_credentials_from_environment()

        if not _cached_credentials.valid:
            if (
                _cached_credentials.expired
                and _cached_credentials.refresh_token
            ):
                _cached_credentials.refresh(Request())
            else:
                raise RuntimeError(
                    "No valid Google Drive credentials available. "
                    "Please authenticate at /auth/login."
                )

        return _cached_credentials


def get_drive_service():
    """
    Returns one Drive client per worker thread while sharing the same
    refreshed Credentials object.

    This avoids refreshing the OAuth token on every media request and
    avoids sharing one httplib2 client across multiple FastAPI threads.
    """
    credentials = _get_valid_credentials()

    service = getattr(_thread_local, "drive_service", None)
    service_credentials = getattr(
        _thread_local,
        "drive_credentials",
        None
    )

    if service is None or service_credentials is not credentials:
        service = build(
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False
        )
        _thread_local.drive_service = service
        _thread_local.drive_credentials = credentials

    return service


def upload_file_to_drive(
    drive,
    file,
    file_name: str,
    folder_id: str
):
    file_metadata = {
        "name": file_name,
        "parents": [folder_id]
    }

    media = MediaIoBaseUpload(
        file.file,
        mimetype=file.content_type,
        chunksize=8 * 1024 * 1024,
        resumable=True
    )

    request = drive.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    )

    response = None

    while response is None:
        _, response = request.next_chunk()

    return response["id"]


def upload_bytes_to_drive(
    drive,
    data: bytes,
    file_name: str,
    folder_id: str,
    mimetype: str
):
    file_metadata = {
        "name": file_name,
        "parents": [folder_id]
    }

    buffer = io_module.BytesIO(data)

    media = MediaIoBaseUpload(
        buffer,
        mimetype=mimetype,
        resumable=False
    )

    response = (
        drive.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id"
        )
        .execute()
    )

    return response["id"]


def get_or_create_child_folder(
    drive,
    parent_folder_id: str,
    folder_name: str
):
    escaped_name = folder_name.replace("'", r"\'")

    result = (
        drive.files()
        .list(
            q=(
                f"'{parent_folder_id}' in parents and "
                f"name = '{escaped_name}' and "
                "mimeType = 'application/vnd.google-apps.folder' and "
                "trashed = false"
            ),
            fields="files(id, name)",
            pageSize=1
        )
        .execute()
    )

    folders = result.get("files", [])

    if folders:
        return folders[0]["id"]

    created_folder = (
        drive.files()
        .create(
            body={
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_folder_id]
            },
            fields="id"
        )
        .execute()
    )

    return created_folder["id"]
