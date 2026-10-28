import os
import tracemalloc
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from guest_access import event_token
from main import app
from routers import media


TEST_ENV = {
    "ADMIN_PASSWORD": "example-password-123",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "FOLDER_ID": "test-drive-folder",
    "GOOGLE_DRIVE_TOKEN_JSON": '{"token":"test-token"}',
    "QR_ACCESS_SECRET": "test-secret-with-at-least-32-characters",
}


class MediaStreamingTests(unittest.TestCase):
    def setUp(self):
        self.content = b"v" * (media.STREAM_CHUNK_BYTES * 2 + 17)
        self.calls = []

    def read_range(self, drive, file_id, start, end):
        self.calls.append((file_id, start, end))
        return self.content[start:end + 1]

    def request(self, suffix="", headers=None, access_event=7, media_event=7,
                content_type="video/mp4"):
        record = {
            "id": "media-1", "event_id": media_event,
            "drive_file_id": "drive-1", "file_name": "clip.mp4",
            "content_type": content_type, "size_bytes": len(self.content),
        }
        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(media, "get_supabase", return_value=object()),
            patch.object(media, "get_media_by_id", return_value=record),
            patch.object(media, "get_drive_service", return_value=object()),
            patch.object(media, "get_drive_file_size", return_value=len(self.content)),
            patch.object(media, "download_file_range", side_effect=self.read_range),
            TestClient(app) as client,
        ):
            return client.get(
                f"/media/media-1{suffix}?access={event_token(access_event)}",
                headers=headers or {},
            )

    def test_full_video_download_is_chunked_with_200_headers(self):
        response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.content)
        self.assertEqual(response.headers["content-length"], str(len(self.content)))
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertEqual(len(self.calls), 3)
        self.assertLessEqual(max(end - start + 1 for _, start, end in self.calls),
                             media.STREAM_CHUNK_BYTES)

    def test_small_video_range_never_downloads_full_file(self):
        response = self.request(headers={"Range": "bytes=12-35"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, self.content[12:36])
        self.assertEqual(response.headers["content-range"],
                         f"bytes 12-35/{len(self.content)}")
        self.assertEqual(response.headers["content-length"], "24")
        self.assertEqual(self.calls, [("drive-1", 12, 35)])

    def test_invalid_and_unsatisfiable_ranges_return_416(self):
        for value in ("bytes=abc-def", "bytes=999999999-", "bytes=0-1,3-4"):
            with self.subTest(value=value):
                response = self.request(headers={"Range": value})
                self.assertEqual(response.status_code, 416)
                self.assertEqual(response.headers["content-range"],
                                 f"bytes */{len(self.content)}")
        self.assertEqual(self.calls, [])

    def test_preview_and_download_are_streamed(self):
        for suffix in ("/preview", "/download"):
            with self.subTest(suffix=suffix):
                response = self.request(suffix=suffix, content_type="image/jpeg")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, self.content)
                self.assertEqual(response.headers["content-length"],
                                 str(len(self.content)))

    def test_invalid_or_other_event_access_never_reads_drive(self):
        for event in (8,):
            response = self.request(access_event=event)
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.calls, [])

    def test_iterator_close_stops_future_requests(self):
        with (patch.object(media, "get_drive_service", return_value=object()),
              patch.object(media, "download_file_range", side_effect=self.read_range)):
            iterator = media.iter_drive_range("drive-1", 0, len(self.content) - 1)
            next(iterator)
            iterator.close()
            self.assertEqual(len(self.calls), 1)

    def test_streaming_peak_memory_does_not_scale_with_file_size(self):
        # The source represents a file already held by a fake Drive service.
        self.content = b"v" * (media.STREAM_CHUNK_BYTES * 20)
        with (patch.object(media, "get_drive_service", return_value=object()),
              patch.object(media, "download_file_range", side_effect=self.read_range)):
            tracemalloc.start()
            try:
                for chunk in media.iter_drive_range("drive-1", 0, len(self.content) - 1):
                    self.assertLessEqual(len(chunk), media.STREAM_CHUNK_BYTES)
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
        self.assertLess(peak, media.STREAM_CHUNK_BYTES * 3)


if __name__ == "__main__":
    unittest.main()
