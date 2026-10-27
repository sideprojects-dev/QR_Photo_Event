import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError
from httplib2 import Response

import deps
from main import app
from routers import admin_media


TEST_ENV = {
    "ADMIN_PASSWORD": "example-password-123",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "FOLDER_ID": "test-drive-folder",
    "GOOGLE_DRIVE_TOKEN_JSON": '{"token":"test-token"}',
    "QR_ACCESS_SECRET": "test-secret-with-at-least-32-characters",
}
HEADERS = {"x-admin-password": TEST_ENV["ADMIN_PASSWORD"]}
BASE = "/api/admin/events/party/media"


def database(record=None, deleted=None):
    db = Mock()
    events = Mock()
    media = Mock()
    db.table.side_effect = lambda name: {"events": events, "media": media}[name]
    event_query = Mock()
    event_query.eq.return_value = event_query
    event_query.limit.return_value = event_query
    event_query.execute.return_value = SimpleNamespace(
        data=[{"id": 7, "name": "Petrecere", "slug": "party"}]
    )
    events.select.return_value = event_query
    media_query = Mock()
    media_query.eq.return_value = media_query
    media_query.like.return_value = media_query
    media_query.order.return_value = media_query
    media_query.range.return_value = media_query
    media_query.limit.return_value = media_query
    media_query.execute.return_value = SimpleNamespace(data=record or [])
    media.select.return_value = media_query
    delete_query = Mock()
    delete_query.eq.return_value = delete_query
    delete_query.execute.return_value = SimpleNamespace(data=deleted or [])
    media.delete.return_value = delete_query
    return db, media, media_query, delete_query


def drive_mock(fail_trash=None):
    drive = Mock()
    files = drive.files.return_value
    files.get.side_effect = lambda **kwargs: SimpleNamespace(
        execute=lambda: {"trashed": False}
    )
    actions = []

    def update(**kwargs):
        def execute():
            actions.append((kwargs["fileId"], kwargs["body"]["trashed"]))
            if kwargs["fileId"] == fail_trash and kwargs["body"]["trashed"]:
                raise RuntimeError("private Drive detail")
            return {"id": kwargs["fileId"]}
        return SimpleNamespace(execute=execute)

    files.update.side_effect = update
    return drive, actions


class AdminMediaTests(unittest.TestCase):
    def client(self, db, drive=None):
        return (
            patch.dict(os.environ, TEST_ENV),
            patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
            patch.object(admin_media, "get_supabase", return_value=db),
            patch.object(admin_media, "get_drive_service", return_value=drive),
            TestClient(app),
        )

    def test_admin_auth_cannot_be_replaced_with_guest_access(self):
        db, _, _, _ = database()
        env, password, supabase, drive_patch, client = self.client(db)
        with env, password, supabase, drive_patch, client:
            self.assertEqual(client.get(BASE).status_code, 401)
            self.assertEqual(client.get(BASE + "?access=guest-code").status_code, 401)
            self.assertEqual(client.delete(BASE + "/m1?access=guest-code").status_code, 401)

    def test_stats_count_does_not_download_rows(self):
        db = Mock()
        query = db.table.return_value.select.return_value
        query.like.return_value = query
        query.execute.return_value = SimpleNamespace(count=8)
        self.assertEqual(deps.count_rows(db, "media", media_kind="video"), 8)
        db.table.return_value.select.assert_called_once_with(
            "id", count="exact", head=True
        )
        query.like.assert_called_once_with("content_type", "video/%")

    def test_list_filters_sorts_and_pages_with_event_binding(self):
        row = {"id": "m1", "file_name": "photo.jpg", "content_type": "image/jpeg",
               "size_bytes": 1024, "created_at": "2025-01-01T00:00:00Z"}
        db, _, query, _ = database([row])
        env, password, supabase, drive, client = self.client(db)
        with env, password, supabase, drive, client:
            response = client.get(
                BASE + "?kind=image&sort=oldest&limit=10&offset=5", headers=HEADERS
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.json()["event"]["name"], "Petrecere")
        self.assertEqual(response.json()["items"], [row])
        query.eq.assert_called_with("event_id", 7)
        query.like.assert_called_once_with("content_type", "image/%")
        query.order.assert_any_call("created_at", desc=False)
        query.range.assert_called_once_with(5, 15)

    def test_wrong_event_never_touches_drive(self):
        db, media, _, _ = database()
        drive, _ = drive_mock()
        env, password, supabase, drive_patch, client = self.client(db, drive)
        with env, password, supabase, drive_patch, client:
            response = client.delete(BASE + "/m1", headers=HEADERS)
        self.assertEqual(response.status_code, 404)
        drive.files.assert_not_called()
        media.delete.assert_not_called()

    def test_delete_trashes_all_files_then_removes_bound_record(self):
        record = {"id": "m1", "event_id": 7, "drive_file_id": "original",
                  "thumbnail_drive_file_id": "thumb", "preview_drive_file_id": "preview"}
        db, _, _, delete_query = database([record], [record])
        drive, actions = drive_mock()
        env, password, supabase, drive_patch, client = self.client(db, drive)
        with env, password, supabase, drive_patch, client:
            response = client.delete(BASE + "/m1", headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "deleted")
        self.assertEqual(actions, [("original", True), ("thumb", True), ("preview", True)])
        self.assertEqual(delete_query.eq.call_count, 2)
        delete_query.eq.assert_any_call("event_id", 7)

    def test_drive_failure_rolls_back_and_preserves_database_row(self):
        record = {"id": "m1", "event_id": 7, "drive_file_id": "original",
                  "thumbnail_drive_file_id": "thumb"}
        db, media, _, _ = database([record])
        drive, actions = drive_mock(fail_trash="thumb")
        env, password, supabase, drive_patch, client = self.client(db, drive)
        with env, password, supabase, drive_patch, client:
            response = client.delete(BASE + "/m1", headers=HEADERS)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private Drive detail", response.text)
        self.assertEqual(actions, [("original", True), ("thumb", True), ("original", False)])
        media.delete.assert_not_called()

    def test_rollback_failure_is_reported_for_manual_repair(self):
        record = {"id": "m1", "event_id": 7, "drive_file_id": "original"}
        db, _, _, delete_query = database([record])
        delete_query.execute.side_effect = RuntimeError("private Supabase detail")
        drive, actions = drive_mock()
        original_update = drive.files.return_value.update.side_effect

        def fail_restore(**kwargs):
            if kwargs["body"]["trashed"] is False:
                return SimpleNamespace(execute=lambda: (_ for _ in ()).throw(RuntimeError("restore failed")))
            return original_update(**kwargs)

        drive.files.return_value.update.side_effect = fail_restore
        env, password, supabase, drive_patch, client = self.client(db, drive)
        with env, password, supabase, drive_patch, client:
            response = client.delete(BASE + "/m1", headers=HEADERS)
        self.assertEqual(response.status_code, 503)
        self.assertIn("verificare manuală", response.text)
        self.assertEqual(actions, [("original", True)])

    def test_supabase_failure_restores_drive_file(self):
        record = {"id": "m1", "event_id": 7, "drive_file_id": "original"}
        db, _, _, delete_query = database([record])
        delete_query.execute.side_effect = RuntimeError("private Supabase detail")
        drive, actions = drive_mock()
        env, password, supabase, drive_patch, client = self.client(db, drive)
        with env, password, supabase, drive_patch, client:
            response = client.delete(BASE + "/m1", headers=HEADERS)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private Supabase detail", response.text)
        self.assertEqual(actions, [("original", True), ("original", False)])

    def test_ambiguous_supabase_failure_keeps_file_in_trash_for_reconciliation(self):
        record = {"id": "m1", "event_id": 7, "drive_file_id": "original"}
        db, _, media_query, delete_query = database([record])
        delete_query.execute.side_effect = RuntimeError("private write error")
        media_query.execute.side_effect = [SimpleNamespace(data=[record]), RuntimeError("private read error")]
        drive, actions = drive_mock()
        env, password, supabase, drive_patch, client = self.client(db, drive)
        with env, password, supabase, drive_patch, client:
            response = client.delete(BASE + "/m1", headers=HEADERS)
        self.assertEqual(response.status_code, 503)
        self.assertIn("Verifică manual", response.text)
        self.assertEqual(actions, [("original", True)])

    def test_second_delete_reports_missing_material(self):
        db, _, _, _ = database()
        env, password, supabase, drive_patch, client = self.client(db)
        with env, password, supabase, drive_patch, client:
            response = client.delete(BASE + "/m1", headers=HEADERS)
        self.assertEqual(response.status_code, 404)

    def test_record_removed_by_concurrent_request_is_not_restored(self):
        record = {"id": "m1", "event_id": 7, "drive_file_id": "original"}
        db, _, _, _ = database([record], [])
        drive, actions = drive_mock()
        env, password, supabase, drive_patch, client = self.client(db, drive)
        with env, password, supabase, drive_patch, client:
            response = client.delete(BASE + "/m1", headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "already_deleted")
        self.assertEqual(actions, [("original", True)])

    def test_already_trashed_or_missing_drive_file_can_be_reconciled(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                record = {"id": "m1", "event_id": 7, "drive_file_id": "original"}
                db, _, _, _ = database([record], [record])
                drive, actions = drive_mock()
                if missing:
                    drive.files.return_value.get.side_effect = lambda **kwargs: SimpleNamespace(
                        execute=lambda: (_ for _ in ()).throw(
                            HttpError(Response({"status": 404}), b"not found")
                        )
                    )
                else:
                    drive.files.return_value.get.side_effect = lambda **kwargs: SimpleNamespace(
                        execute=lambda: {"trashed": True}
                    )
                env, password, supabase, drive_patch, client = self.client(db, drive)
                with env, password, supabase, drive_patch, client:
                    response = client.delete(BASE + "/m1", headers=HEADERS)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(actions, [])

    def test_dashboard_counts_are_admin_only(self):
        db = Mock()
        env, password, supabase, drive_patch, client = self.client(db)
        with env, password, supabase, drive_patch, patch.object(
            admin_media, "count_rows", side_effect=[1, 2, 3, 4, 5]
        ) as count, client:
            self.assertEqual(client.get("/api/admin/stats").status_code, 401)
            response = client.get("/api/admin/stats", headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["photos"], 4)
        self.assertEqual(response.json()["videos"], 5)
        self.assertEqual(count.call_count, 5)


if __name__ == "__main__":
    unittest.main()
