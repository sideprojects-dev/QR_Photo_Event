import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi.responses import Response

from main import app
from routers import media
from guest_access import event_token


TEST_ENV = {
    "ADMIN_PASSWORD": "example-password-123",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "FOLDER_ID": "test-drive-folder",
    "GOOGLE_DRIVE_TOKEN_JSON": '{"token":"test-token"}',
    "QR_ACCESS_SECRET": "test-secret-with-at-least-32-characters",
}


class PublicMediaResponseTests(unittest.TestCase):
    def test_gallery_returns_only_fields_needed_by_browser(self):
        private_record = {
            "id": "media-1",
            "event_id": 7,
            "drive_file_id": "private-original-id",
            "thumbnail_drive_file_id": "private-thumbnail-id",
            "preview_drive_file_id": "private-preview-id",
            "file_name": "private-name.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 123,
            "created_at": "2026-10-26T12:00:00",
        }

        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(media, "get_supabase", return_value=object()),
            patch.object(media, "get_event_by_slug", return_value={"id": 7}),
            patch.object(media, "get_event_media", return_value=([private_record], False)),
            TestClient(app) as client,
        ):
            response = client.get(f"/api/events/event-one/media?access={event_token(7)}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.json()["items"], [{
            "id": "media-1",
            "content_type": "image/jpeg",
            "created_at": "2026-10-26T12:00:00",
        }])

    def test_gallery_does_not_accept_another_events_link(self):
        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(media, "get_supabase", return_value=object()),
            patch.object(media, "get_event_by_slug", return_value={"id": 7}),
            patch.object(media, "get_event_media") as get_items,
            TestClient(app) as client,
        ):
            for url in (
                "/api/events/event-one/media",
                f"/api/events/event-one/media?access={event_token(8)}",
            ):
                self.assertEqual(client.get(url).status_code, 404)
            get_items.assert_not_called()

    def test_each_media_route_requires_the_matching_event_link(self):
        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(media, "get_supabase", return_value=object()),
            patch.object(media, "get_media_by_id", return_value={
                "id": "media-1", "event_id": 7, "content_type": "image/jpeg"
            }),
            patch.object(media, "get_drive_service") as drive_service,
            TestClient(app) as client,
        ):
            for suffix in ("", "/thumbnail", "/preview", "/download"):
                for query in ("", f"?access={event_token(8)}"):
                    self.assertEqual(
                        client.get(f"/media/media-1{suffix}{query}").status_code,
                        404,
                    )
            drive_service.assert_not_called()

    def test_upload_rejects_another_events_link_before_storage(self):
        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(media, "get_supabase", return_value=object()),
            patch.object(media, "get_event_by_slug", return_value={"id": 7}),
            patch.object(media, "get_drive_service") as drive_service,
            TestClient(app) as client,
        ):
            response = client.post(
                f"/upload/event-one?access={event_token(8)}",
                files={"file": ("photo.jpg", b"test", "image/jpeg")},
            )
            self.assertEqual(response.status_code, 404)
            drive_service.assert_not_called()

    def test_matching_event_link_opens_its_media(self):
        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(media, "get_supabase", return_value=object()),
            patch.object(media, "get_media_by_id", return_value={
                "id": "media-1", "event_id": 7, "content_type": "image/jpeg",
                "drive_file_id": "private-original-id", "file_name": "photo.jpg",
            }),
            patch.object(media, "get_drive_service", return_value=object()),
            patch.object(media, "stream_drive_file", return_value=Response(b"image")) as stream,
            TestClient(app) as client,
        ):
            response = client.get(f"/media/media-1?access={event_token(7)}")
            self.assertEqual(response.status_code, 200)
            stream.assert_called_once()


if __name__ == "__main__":
    unittest.main()
