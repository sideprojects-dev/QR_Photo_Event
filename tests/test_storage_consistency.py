import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from guest_access import event_token
from main import app
from routers import media
from storage_consistency import check_event_storage


TEST_ENV = {
    "ADMIN_PASSWORD": "example-password-123",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "FOLDER_ID": "test-drive-folder",
    "GOOGLE_DRIVE_TOKEN_JSON": '{"token":"test-token"}',
    "QR_ACCESS_SECRET": "test-secret-with-at-least-32-characters",
}
VIDEO = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isom"
SAVED = {"id": "media-1", "event_id": 7,
         "drive_file_id": "new-drive-id", "content_type": "video/mp4"}


class StorageConsistencyTests(unittest.TestCase):
    def upload(self, save_result=None, save_error=None, lookup_result=None,
               lookup_error=None, cleanup_error=None, access_event=7):
        drive = Mock()
        if cleanup_error:
            drive.files.return_value.delete.return_value.execute.side_effect = cleanup_error
        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(media, "get_supabase", return_value=object()),
            patch.object(media, "get_event_by_slug", return_value={"id": 7, "folder_id": "folder-7"}),
            patch.object(media, "get_drive_service", return_value=drive),
            patch.object(media, "upload_file_to_drive", return_value="new-drive-id") as upload_drive,
            patch.object(media, "save_media_record", return_value=save_result,
                         side_effect=save_error) as save,
            patch.object(media, "find_saved_media", return_value=lookup_result,
                         side_effect=lookup_error) as lookup,
            TestClient(app) as client,
        ):
            response = client.post(
                f"/upload/event-7?access={event_token(access_event)}",
                files={"file": ("clip.mp4", VIDEO, "video/mp4")},
            )
        return response, drive, upload_drive, save, lookup

    def test_successful_insert_returns_media_without_cleanup(self):
        response, drive, _, save, lookup = self.upload(save_result=SAVED)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["media"]["id"], "media-1")
        self.assertEqual(save.call_args.kwargs["event_id"], 7)
        lookup.assert_not_called()
        drive.files.return_value.delete.assert_not_called()

    def test_failed_insert_without_row_cleans_only_new_drive_file(self):
        response, drive, _, _, lookup = self.upload(save_error=RuntimeError("db unavailable"))
        self.assertEqual(response.status_code, 503)
        lookup.assert_called_once()
        drive.files.return_value.delete.assert_called_once_with(fileId="new-drive-id")

    def test_invalid_insert_response_without_row_is_not_success(self):
        response, drive, _, _, _ = self.upload(save_result=None)
        self.assertEqual(response.status_code, 503)
        drive.files.return_value.delete.assert_called_once()

    def test_insert_error_with_confirmed_row_is_success_without_cleanup(self):
        response, drive, _, _, _ = self.upload(
            save_error=RuntimeError("response lost"), lookup_result=SAVED
        )
        self.assertEqual(response.status_code, 200)
        drive.files.return_value.delete.assert_not_called()

    def test_unknown_database_state_preserves_drive_file(self):
        response, drive, _, _, _ = self.upload(
            save_error=RuntimeError("response lost"),
            lookup_error=RuntimeError("lookup unavailable"),
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn("neclar", response.json()["detail"])
        drive.files.return_value.delete.assert_not_called()

    def test_cleanup_failure_reports_manual_review(self):
        response, drive, _, _, _ = self.upload(
            save_result=None, cleanup_error=RuntimeError("Drive unavailable")
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn("manual", response.json()["detail"])
        drive.files.return_value.delete.assert_called_once()

    def test_other_event_cannot_upload(self):
        response, _, upload_drive, _, _ = self.upload(access_event=8)
        self.assertEqual(response.status_code, 404)
        upload_drive.assert_not_called()

    def test_saved_record_must_match_event_and_drive_file(self):
        for row in (None, {"id": 1}, {"id": 1, "event_id": 8,
                                    "drive_file_id": "new-drive-id"},
                    {"id": 1, "event_id": 7, "drive_file_id": "old"}):
            with self.subTest(row=row):
                self.assertFalse(media.valid_saved_media(row, 7, "new-drive-id"))
        self.assertTrue(media.valid_saved_media(SAVED, 7, "new-drive-id"))

    def test_supabase_insert_result_is_checked_before_acceptance(self):
        supabase = Mock()
        insert = supabase.table.return_value.insert.return_value
        for rows, expected in (([SAVED], SAVED), ([], None),
                               ([{"id": "media-1", "event_id": 8,
                                  "drive_file_id": "new-drive-id"}], None)):
            with self.subTest(rows=rows):
                insert.execute.return_value = SimpleNamespace(data=rows)
                result = media.save_media_record(
                    supabase, 7, "new-drive-id", None, None,
                    "clip.mp4", "video/mp4", len(VIDEO),
                )
                self.assertEqual(result, expected)

    def test_read_only_checker_is_scoped_to_one_event(self):
        supabase = Mock()
        # Use separate fluent query mocks for events and media.
        event_table = Mock()
        event_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[{"id": 7, "folder_id": "folder-7"}])
        )
        media_table = Mock()
        media_table.select.return_value.eq.return_value.range.return_value.execute.return_value = (
            SimpleNamespace(data=[{"drive_file_id": "file-a",
                                   "thumbnail_drive_file_id": None,
                                   "preview_drive_file_id": None}])
        )
        supabase.table.side_effect = lambda name: {"events": event_table, "media": media_table}[name]
        with patch("storage_consistency._drive_children", return_value=iter([
            {"id": "file-a", "mimeType": "image/jpeg"},
            {"id": "orphan", "mimeType": "image/jpeg"},
        ])):
            report = check_event_storage(supabase, Mock(), "event-7")
        self.assertEqual(report["unreferenced_in_event_folders"], ["orphan"])
        media_table.select.return_value.eq.assert_called_once_with("event_id", 7)


if __name__ == "__main__":
    unittest.main()
