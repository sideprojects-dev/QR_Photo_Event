"""Read-only, event-scoped Drive/Supabase consistency report.

Run explicitly with ``python storage_consistency.py EVENT_SLUG``. No repair is
performed; unreferenced Drive files need human review before any deletion.
"""

import argparse

from deps import get_supabase
from google_drive import get_drive_service


def _drive_children(drive, folder_id):
    page_token = None
    escaped_folder_id = folder_id.replace("'", r"\'")
    while True:
        result = drive.files().list(
            q=f"'{escaped_folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=1000,
            **({"pageToken": page_token} if page_token else {}),
        ).execute()
        yield from result.get("files", [])
        page_token = result.get("nextPageToken")
        if not page_token:
            break


def check_event_storage(supabase, drive, slug):
    event_result = (
        supabase.table("events").select("id, folder_id")
        .eq("slug", slug).limit(1).execute()
    )
    if not event_result.data:
        raise ValueError("Evenimentul nu a fost găsit")
    event = event_result.data[0]
    referenced = set()
    offset = 0
    while True:
        rows = (
            supabase.table("media")
            .select("drive_file_id, thumbnail_drive_file_id, preview_drive_file_id")
            .eq("event_id", event["id"]).range(offset, offset + 499).execute()
        ).data or []
        for row in rows:
            referenced.update(row[key] for key in (
                "drive_file_id", "thumbnail_drive_file_id", "preview_drive_file_id"
            ) if row.get(key))
        if len(rows) < 500:
            break
        offset += 500

    actual = set()
    for child in _drive_children(drive, event["folder_id"]):
        if child.get("mimeType") == "application/vnd.google-apps.folder":
            if child.get("name") in ("_thumbnails", "_previews"):
                actual.update(item["id"] for item in _drive_children(drive, child["id"])
                    if item.get("mimeType") != "application/vnd.google-apps.folder")
        else:
            actual.add(child["id"])
    return {
        "referenced_count": len(referenced),
        "drive_file_count": len(actual),
        "missing_from_event_folders": sorted(referenced - actual),
        "unreferenced_in_event_folders": sorted(actual - referenced),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event_slug")
    args = parser.parse_args()
    report = check_event_storage(get_supabase(), get_drive_service(), args.event_slug)
    for key, value in report.items():
        print(f"{key}: {value}")
