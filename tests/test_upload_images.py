import io
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from main import app
from routers import media


TEST_ENV = {
    "ADMIN_PASSWORD": "example-password-123",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "FOLDER_ID": "test-drive-folder",
    "GOOGLE_DRIVE_TOKEN_JSON": '{"token":"test-token"}',
}


class ImageUploadTests(unittest.TestCase):
    def upload(self, data: bytes, content_type: str):
        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(media, "get_supabase", return_value=object()),
            patch.object(
                media,
                "get_event_by_slug",
                return_value={"id": 1, "folder_id": "event-folder"},
            ),
            patch.object(media, "get_drive_service") as drive_service,
            TestClient(app) as client,
        ):
            response = client.post(
                "/upload/test-event",
                files={"file": ("photo.jpg", data, content_type)},
            )
            self.assertEqual(drive_service.call_count, 0)
            return response

    def test_invalid_jpeg_is_rejected_before_drive(self):
        response = self.upload(b"not an image", "image/jpeg")
        self.assertEqual(response.status_code, 400)

    def test_svg_is_rejected_before_drive(self):
        response = self.upload(b"<svg></svg>", "image/svg+xml")
        self.assertEqual(response.status_code, 400)

    def test_declared_mime_must_match_decoded_format(self):
        buffer = io.BytesIO()
        Image.new("RGB", (2, 2)).save(buffer, format="PNG")
        response = self.upload(buffer.getvalue(), "image/jpeg")
        self.assertEqual(response.status_code, 400)

    def test_oversized_image_is_rejected_before_drive(self):
        with patch.object(media, "MAX_IMAGE_BYTES", 8):
            response = self.upload(b"123456789", "image/jpeg")
        self.assertEqual(response.status_code, 413)

    def test_valid_jpeg_reaches_storage(self):
        buffer = io.BytesIO()
        Image.new("RGB", (2, 2)).save(buffer, format="JPEG")

        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(media, "get_supabase", return_value=object()),
            patch.object(
                media,
                "get_event_by_slug",
                return_value={"id": 1, "folder_id": "event-folder"},
            ),
            patch.object(media, "get_drive_service", return_value=object()),
            patch.object(media, "upload_file_to_drive", return_value="original") as upload_original,
            patch.object(media, "get_or_create_child_folder", return_value="variants-folder"),
            patch.object(media, "upload_bytes_to_drive", return_value="variant"),
            patch.object(media, "save_media_record", return_value={"id": 1}),
            TestClient(app) as client,
        ):
            response = client.post(
                "/upload/test-event",
                files={"file": ("photo.jpg", buffer.getvalue(), "image/jpeg")},
            )

        self.assertEqual(response.status_code, 200)
        upload_original.assert_called_once()


if __name__ == "__main__":
    unittest.main()
