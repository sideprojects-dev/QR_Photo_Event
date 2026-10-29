import io
import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from guest_access import event_token
from main import app
from perf_monitor import PerfTrace
from routers import media


TEST_ENV = {
    "ADMIN_PASSWORD": "example-password-123",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "FOLDER_ID": "test-drive-folder",
    "GOOGLE_DRIVE_TOKEN_JSON": '{"token":"test-token"}',
    "QR_ACCESS_SECRET": "test-secret-with-at-least-32-characters",
}


def events(log_mock):
    return [json.loads(call.args[0]) for call in log_mock.call_args_list
            if call.args and '"event":"performance"' in call.args[0]]


class PerformanceMonitoringTests(unittest.TestCase):
    def test_disabled_monitoring_emits_nothing(self):
        with (patch.dict(os.environ, {"QR_PERF_MONITORING": "0"}),
              patch("perf_monitor._logger.info") as log):
            trace = PerfTrace("example")
            with trace.step("work"):
                pass
            trace.emit()
        log.assert_not_called()

    def test_logging_failure_does_not_interrupt_the_operation(self):
        with (patch.dict(os.environ, {"QR_PERF_MONITORING": "1"}),
              patch("perf_monitor._logger.info", side_effect=RuntimeError("log unavailable"))):
            trace = PerfTrace("example")
            with trace.step("work"):
                pass
            trace.emit()

    def test_photo_upload_logs_phases_without_sensitive_values(self):
        photo = io.BytesIO()
        Image.new("RGB", (2, 2)).save(photo, format="JPEG")
        with (
            patch.dict(os.environ, {**TEST_ENV, "QR_PERF_MONITORING": "1"}),
            patch("perf_monitor._logger.info") as log,
            patch.object(media, "get_supabase", return_value=object()),
            patch.object(media, "get_event_by_slug", return_value={"id": 1, "folder_id": "folder"}),
            patch.object(media, "get_drive_service", return_value=object()),
            patch.object(media, "upload_file_to_drive", return_value="original"),
            patch.object(media, "get_or_create_child_folder", return_value="variants"),
            patch.object(media, "upload_bytes_to_drive", return_value="variant"),
            patch.object(media, "save_media_record", return_value={
                "id": 1, "content_type": "image/jpeg"
            }),
            TestClient(app) as client,
        ):
            access = event_token(1)
            response = client.post(
                f"/upload/test-event?access={access}",
                files={"file": ("private-photo.jpg", photo.getvalue(), "image/jpeg")},
            )
        self.assertEqual(response.status_code, 200)
        records = events(log)
        upload = next(item for item in records if item["operation"] == "photo_upload")
        request = next(item for item in records if item["operation"] == "upload_request")
        self.assertEqual(upload["trace_id"], request["trace_id"])
        self.assertTrue({"image_read", "image_decode_validate", "thumbnail_generate",
                         "preview_generate", "drive_original_upload", "drive_thumbnail_folder",
                         "drive_thumbnail_upload", "drive_preview_folder",
                         "drive_preview_upload", "supabase_media_insert"}
                        <= upload["phases_ms"].keys())
        serialized = json.dumps(records)
        self.assertNotIn(access, serialized)
        self.assertNotIn("private-photo.jpg", serialized)
        self.assertNotIn("test-event", serialized)

    def test_gallery_and_thumbnail_separate_preparation_from_streaming(self):
        record = {
            "id": "media-1", "event_id": 1, "content_type": "image/jpeg",
            "thumbnail_drive_file_id": "thumbnail", "drive_file_id": "original",
        }
        with (
            patch.dict(os.environ, {**TEST_ENV, "QR_PERF_MONITORING": "1"}),
            patch("perf_monitor._logger.info") as log,
            patch.object(media, "get_supabase", return_value=object()),
            patch.object(media, "get_event_by_slug", return_value={"id": 1}),
            patch.object(media, "get_event_media", return_value=([record], False)),
            patch.object(media, "get_media_by_id", return_value=record),
            patch.object(media, "get_drive_service", return_value=object()),
            patch.object(media, "get_drive_file_size", return_value=3),
            patch.object(media, "download_file_range", return_value=b"img"),
            TestClient(app) as client,
        ):
            access = event_token(1)
            listing = client.get(f"/api/events/test-event/media?access={access}")
            thumbnail = client.get(f"/media/media-1/thumbnail?access={access}")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(thumbnail.content, b"img")
        records = events(log)
        gallery = next(item for item in records if item["operation"] == "gallery_list")
        prepare = next(item for item in records if item["operation"] == "thumbnail_prepare")
        stream = next(item for item in records if item["operation"] == "media_stream")
        self.assertTrue({"event_lookup", "access_check", "media_list"} <= gallery["phases_ms"].keys())
        self.assertTrue({"media_lookup", "access_check", "drive_metadata"} <= prepare["phases_ms"].keys())
        self.assertIn("drive_fetch", stream["phases_ms"])
        self.assertEqual(prepare["trace_id"], stream["trace_id"])
        self.assertNotIn(access, json.dumps(records))


if __name__ == "__main__":
    unittest.main()
