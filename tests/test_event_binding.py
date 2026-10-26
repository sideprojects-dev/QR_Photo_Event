import io
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from PIL import Image

from main import app
from routers import events, locations, media


TEST_ENV = {
    "ADMIN_PASSWORD": "example-password-123",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "FOLDER_ID": "test-drive-folder",
    "GOOGLE_DRIVE_TOKEN_JSON": '{"token":"test-token"}',
}


class EventBindingTests(unittest.TestCase):
    def test_open_page_keeps_original_event_after_qr_changes(self):
        qr_db = Mock()
        qr_query = (
            qr_db.table.return_value.select.return_value
            .eq.return_value.order.return_value.limit.return_value
        )
        qr_query.execute.side_effect = [
            SimpleNamespace(data=[{"slug": "event-A"}]),
            SimpleNamespace(data=[{"slug": "event-B"}]),
        ]

        with patch.object(locations, "get_supabase", return_value=qr_db):
            first_scan = locations.master_redirect()
            second_scan = locations.master_redirect()

        self.assertEqual(first_scan.headers["location"], "/event/event-A")
        self.assertEqual(second_scan.headers["location"], "/event/event-B")

        event_db = Mock()
        event_query = event_db.table.return_value.select.return_value.eq.return_value
        event_query.execute.return_value = SimpleNamespace(data=[{"id": 1}])

        with patch.object(events, "get_supabase", return_value=event_db):
            page = events.event_page("event-A")

        self.assertIn('window.EVENT_SLUG = "event-A";', page.body.decode())

        image = io.BytesIO()
        Image.new("RGB", (2, 2)).save(image, format="JPEG")
        supabase = object()
        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(media, "get_supabase", return_value=supabase),
            patch.object(
                media,
                "get_event_by_slug",
                return_value={"id": 1, "folder_id": "event-A-folder"},
            ) as get_event,
            patch.object(media, "get_drive_service", return_value=object()),
            patch.object(media, "upload_file_to_drive", return_value="original"),
            patch.object(media, "get_or_create_child_folder", return_value="variants"),
            patch.object(media, "upload_bytes_to_drive", return_value="variant"),
            patch.object(media, "save_media_record", return_value={"id": 1}) as save_record,
            TestClient(app) as client,
        ):
            response = client.post(
                "/upload/event-A",
                files={"file": ("photo.jpg", image.getvalue(), "image/jpeg")},
            )

        self.assertEqual(response.status_code, 200)
        get_event.assert_called_once_with(supabase, "event-A")
        self.assertEqual(save_record.call_args.kwargs["event_id"], 1)

    def test_event_slug_cannot_break_out_of_inline_script(self):
        slug = '</script><script>alert(1)</script>'
        event_db = Mock()
        event_query = event_db.table.return_value.select.return_value.eq.return_value
        event_query.execute.return_value = SimpleNamespace(data=[{"id": 1}])

        with patch.object(events, "get_supabase", return_value=event_db):
            page = events.event_page(slug)

        html = page.body.decode()
        escaped_slug = json.dumps(slug).replace("<", "\\u003c").replace(">", "\\u003e")
        self.assertIn(f"window.EVENT_SLUG = {escaped_slug};", html)
        self.assertNotIn(slug, html)


if __name__ == "__main__":
    unittest.main()
