from deps import get_supabase
from google_drive import (
    get_drive_service,
    get_or_create_child_folder,
    upload_bytes_to_drive
)
from routers.media import (
    PREVIEW_FOLDER_NAME,
    create_image_preview,
    download_drive_file_to_buffer
)


def main():
    supabase = get_supabase()
    drive = get_drive_service()

    result = (
        supabase
        .table("media")
        .select(
            "id, event_id, drive_file_id, "
            "preview_drive_file_id, content_type"
        )
        .order("created_at")
        .execute()
    )

    rows = result.data or []
    image_rows = [
        row
        for row in rows
        if (
            row.get("content_type", "").startswith("image/")
            and not row.get("preview_drive_file_id")
        )
    ]

    if not image_rows:
        print("Nu există imagini care au nevoie de preview.")
        return

    event_folder_cache = {}
    preview_folder_cache = {}

    for index, row in enumerate(image_rows, start=1):
        media_id = row["id"]
        event_id = row["event_id"]

        try:
            if event_id not in event_folder_cache:
                event_result = (
                    supabase
                    .table("events")
                    .select("folder_id")
                    .eq("id", event_id)
                    .limit(1)
                    .execute()
                )

                if not event_result.data:
                    print(
                        f"[{index}/{len(image_rows)}] "
                        f"Media {media_id}: event lipsă."
                    )
                    continue

                event_folder_cache[event_id] = (
                    event_result.data[0]["folder_id"]
                )

            event_folder_id = event_folder_cache[event_id]

            if event_id not in preview_folder_cache:
                preview_folder_cache[event_id] = (
                    get_or_create_child_folder(
                        drive=drive,
                        parent_folder_id=event_folder_id,
                        folder_name=PREVIEW_FOLDER_NAME
                    )
                )

            original_buffer = download_drive_file_to_buffer(
                drive=drive,
                drive_file_id=row["drive_file_id"]
            )

            preview_bytes = create_image_preview(
                original_buffer.getvalue()
            )

            preview_drive_file_id = upload_bytes_to_drive(
                drive=drive,
                data=preview_bytes,
                file_name=f"preview_{media_id}.jpg",
                folder_id=preview_folder_cache[event_id],
                mimetype="image/jpeg"
            )

            (
                supabase
                .table("media")
                .update({
                    "preview_drive_file_id":
                        preview_drive_file_id
                })
                .eq("id", media_id)
                .execute()
            )

            print(
                f"[{index}/{len(image_rows)}] "
                f"Media {media_id}: preview creat."
            )

        except Exception as exc:
            print(
                f"[{index}/{len(image_rows)}] "
                f"Media {media_id}: EROARE {repr(exc)}"
            )


if __name__ == "__main__":
    main()
