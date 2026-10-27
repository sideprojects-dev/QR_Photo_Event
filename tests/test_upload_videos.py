import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

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


class VideoUploadTests(unittest.TestCase):
    def upload(self, data: bytes, content_type: str, filename="clip.exe"):
        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(media, "get_supabase", return_value=object()),
            patch.object(
                media,
                "get_event_by_slug",
                return_value={"id": 1, "folder_id": "event-folder"},
            ),
            patch.object(media, "get_drive_service", return_value=object()) as drive_service,
            patch.object(media, "upload_file_to_drive", return_value="original") as upload_original,
            patch.object(media, "save_media_record", return_value={"id": 1}),
            TestClient(app) as client,
        ):
            response = client.post(
                f"/upload/test-event?access={event_token(1)}",
                files={"file": (filename, data, content_type)},
            )
            return response, drive_service.call_count, upload_original

    def test_executable_declared_as_mp4_is_rejected(self):
        response, drive_calls, upload_original = self.upload(
            b"MZ" + b"fake executable", "video/mp4"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(drive_calls, 0)
        upload_original.assert_not_called()

    def test_invalid_webm_header_is_rejected(self):
        response, drive_calls, _ = self.upload(b"not webm", "video/webm")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(drive_calls, 0)

    def test_unsupported_video_type_is_rejected(self):
        response, drive_calls, _ = self.upload(b"anything", "video/x-msvideo")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(drive_calls, 0)

    def test_oversized_video_is_rejected(self):
        with patch.object(media, "MAX_VIDEO_BYTES", 8):
            response, drive_calls, _ = self.upload(b"123456789", "video/mp4")
        self.assertEqual(response.status_code, 413)
        self.assertEqual(drive_calls, 0)

    def test_mp4_header_reaches_storage_with_canonical_extension(self):
        header = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isom"
        response, drive_calls, upload_original = self.upload(header, "video/mp4")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(drive_calls, 1)
        self.assertTrue(upload_original.call_args.kwargs["file_name"].endswith(".mp4"))

    def test_webm_header_reaches_storage_with_canonical_extension(self):
        header = b"\x1a\x45\xdf\xa3\x9f\x42\x82\x84webm"
        response, drive_calls, upload_original = self.upload(header, "video/webm")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(drive_calls, 1)
        self.assertTrue(upload_original.call_args.kwargs["file_name"].endswith(".webm"))


if __name__ == "__main__":
    unittest.main()
