import io as io_module
import json
import os

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from config import SCOPES


def get_drive_service():
    creds = None

    token_json = os.getenv("token.json")
    print(f"token_json exists: {bool(token_json)}")

    if token_json:
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
        print(f"creds valid: {creds.valid}, expired: {creds.expired}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing token...")
            creds.refresh(Request())
        else:
            raise Exception("No valid credentials available. Please authenticate at /auth/login")

    service = build("drive", "v3", credentials=creds)
    print(f"Drive service type: {type(service)}")
    return service


def upload_file_to_drive(drive, file, file_name: str, folder_id: str):
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

