import json
import os
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
    "QR_PERF_MONITORING": "1",
}


class ThumbnailPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.content = b"thumbnail-data"
        self.record = {
            "id": "media-1", "event_id": 7, "drive_file_id": "original-1",
            "thumbnail_drive_file_id": "thumbnail-1", "content_type": "image/jpeg",
            "size_bytes": len(self.content), "file_name": "photo.jpg",
        }

    def request(self, *, access_event=7, record=None, lookup_error=None,
                metadata_error=None, monitoring=True):
        selected = self.record if record is None else record

        def lookup(*_):
            if lookup_error:
                raise lookup_error
            return selected

        def metadata(*_):
            if metadata_error:
                raise metadata_error
            return len(self.content)

        def read_range(_, file_id, start, end):
            return self.content[start:end + 1]

        with (
            patch.dict(os.environ, dict(TEST_ENV, QR_PERF_MONITORING="1" if monitoring else "0")),
            patch.object(media, "get_supabase", return_value=object()) as supabase,
            patch.object(media, "get_media_by_id", side_effect=lookup) as media_lookup,
            patch.object(media, "get_drive_service", return_value=object()) as drive_client,
            patch.object(media, "get_drive_file_size", side_effect=metadata) as drive_metadata,
            patch.object(media, "download_file_range", side_effect=read_range) as drive_fetch,
            patch("perf_monitor._logger.info") as log,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            response = client.get(
                f"/media/media-1/thumbnail?access={event_token(access_event)}"
            )
        return response, supabase, media_lookup, drive_client, drive_metadata, drive_fetch, log

    def test_dedicated_thumbnail_keeps_drive_metadata_and_streaming(self):
        response, supabase, lookup, _, metadata, fetch, log = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.content)
        self.assertEqual(response.headers["content-length"], str(len(self.content)))
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertEqual(supabase.call_count, 1)
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(metadata.call_count, 1)
        self.assertEqual(fetch.call_args.args[1], "thumbnail-1")
        event = json.loads(log.call_args_list[0].args[0])
        self.assertEqual(event["operation"], "thumbnail_prepare")
        self.assertTrue({"supabase_client", "media_lookup", "access_check",
                         "drive_client", "drive_metadata", "response_prepare"}
                        <= event["phases_ms"].keys())

    def test_legacy_thumbnail_reuses_original_size(self):
        record = dict(self.record, thumbnail_drive_file_id=None)
        response, supabase, lookup, drive_client, metadata, fetch, _ = self.request(record=record)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.content)
        self.assertEqual(response.headers["content-length"], str(len(self.content)))
        self.assertEqual(supabase.call_count, 1)
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(metadata.call_count, 0)
        # Only the streaming worker needs a Drive client.
        self.assertEqual(drive_client.call_count, 1)
        self.assertEqual(fetch.call_args.args[1], "original-1")

    def test_legacy_missing_size_uses_drive_metadata(self):
        record = dict(self.record, thumbnail_drive_file_id=None, size_bytes=None)
        response, _, _, _, metadata, _, _ = self.request(record=record)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(metadata.call_count, 1)

    def test_unauthorized_media_never_calls_drive(self):
        response, _, lookup, drive_client, metadata, fetch, _ = self.request(access_event=8)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(drive_client.call_count, 0)
        self.assertEqual(metadata.call_count, 0)
        self.assertEqual(fetch.call_count, 0)

    def test_deleted_media_and_supabase_error_never_call_drive(self):
        from fastapi import HTTPException
        for error, expected in ((HTTPException(404, "Media not found."), 404),
                                (RuntimeError("Supabase failed"), 500)):
            with self.subTest(error=type(error).__name__):
                response, _, _, drive_client, metadata, fetch, _ = self.request(
                    lookup_error=error
                )
                self.assertEqual(response.status_code, expected)
                self.assertEqual(drive_client.call_count, 0)
                self.assertEqual(metadata.call_count, 0)
                self.assertEqual(fetch.call_count, 0)

    def test_drive_metadata_error_is_not_hidden(self):
        response, _, _, _, metadata, fetch, log = self.request(
            metadata_error=RuntimeError("Drive failed")
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(metadata.call_count, 1)
        self.assertEqual(fetch.call_count, 0)
        event = json.loads(log.call_args_list[0].args[0])
        self.assertEqual(event["outcome"], "error")

    def test_monitoring_disabled_keeps_response_and_emits_no_trace(self):
        record = dict(self.record, thumbnail_drive_file_id=None)
        response, _, _, _, metadata, _, log = self.request(
            record=record, monitoring=False
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.content)
        self.assertEqual(metadata.call_count, 0)
        log.assert_not_called()


if __name__ == "__main__":
    unittest.main()
