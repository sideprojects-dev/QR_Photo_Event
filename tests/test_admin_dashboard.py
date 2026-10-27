import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import deps
from guest_access import event_path, master_path
from main import app
from routers import events, locations


TEST_ENV = {
    "ADMIN_PASSWORD": "example-password-123",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "FOLDER_ID": "test-drive-folder",
    "GOOGLE_DRIVE_TOKEN_JSON": '{"token":"test-token"}',
    "QR_ACCESS_SECRET": "test-secret-with-at-least-32-characters",
}
HEADERS = {"x-admin-password": TEST_ENV["ADMIN_PASSWORD"]}


class AdminDashboardTests(unittest.TestCase):
    def test_count_rows_requests_only_exact_head_count(self):
        db = Mock()
        query = db.table.return_value.select.return_value
        query.eq.return_value = query
        query.like.return_value = query
        query.execute.return_value = SimpleNamespace(count=4)

        result = deps.count_rows(db, "media", (("event_id", 7),), "image")

        self.assertEqual(result, 4)
        db.table.assert_called_once_with("media")
        db.table.return_value.select.assert_called_once_with(
            "id", count="exact", head=True
        )
        query.eq.assert_called_once_with("event_id", 7)
        query.like.assert_called_once_with("content_type", "image/%")

    def test_stats_are_admin_only_and_use_live_counts(self):
        db = Mock()
        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
            patch.object(events, "get_supabase", return_value=db),
            patch.object(events, "count_rows", side_effect=[2, 3, 4, 12, 5]) as count,
            TestClient(app) as client,
        ):
            self.assertEqual(client.get("/api/admin/stats").status_code, 401)
            self.assertEqual(client.get("/api/admin/stats", headers={
                "x-admin-password": "wrong"
            }).status_code, 401)
            response = client.get("/api/admin/stats", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.json(), {
            "locations": 2, "active_events": 3, "archived_events": 4,
            "photos": 12, "videos": 5,
        })
        self.assertEqual(count.call_count, 5)
        count.assert_any_call(db, "events", (("status", "active"),))
        count.assert_any_call(db, "events", (("status", "archived"),))

    def test_stats_failure_does_not_expose_backend_error(self):
        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
            patch.object(events, "get_supabase", return_value=Mock()),
            patch.object(events, "count_rows", side_effect=RuntimeError("private details")),
            TestClient(app) as client,
        ):
            response = client.get("/api/admin/stats", headers=HEADERS)

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private details", response.text)

    def test_location_events_include_real_media_counts_and_qr_links(self):
        db = Mock()
        location_table = Mock()
        event_table = Mock()
        db.table.side_effect = lambda name: {
            "locations": location_table, "events": event_table
        }[name]
        location_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[{"id": 9, "name": "Locație", "slug": "venue"}])
        )
        event_table.select.return_value.eq.return_value.order.return_value.execute.return_value = (
            SimpleNamespace(data=[{"id": 7, "slug": "party", "name": "Petrecere", "status": "active"}])
        )
        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
            patch.object(locations, "get_supabase", return_value=db),
            patch.object(locations, "count_rows", side_effect=[6, 2]) as count,
            TestClient(app) as client,
        ):
            response = client.get("/api/locations/venue/events", headers=HEADERS)
            expected_master = master_path("venue", 9)
            expected_guest = event_path("party", 7)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.json()["master_url"], expected_master)
        event = response.json()["events"][0]
        self.assertEqual(event["guest_url"], expected_guest)
        self.assertEqual((event["photo_count"], event["video_count"]), (6, 2))
        count.assert_any_call(db, "media", (("event_id", 7),), media_kind="image")
        count.assert_any_call(db, "media", (("event_id", 7),), media_kind="video")

    def test_event_list_remains_available_if_media_counts_fail(self):
        db = Mock()
        location_table = Mock()
        event_table = Mock()
        db.table.side_effect = lambda name: {
            "locations": location_table, "events": event_table
        }[name]
        location_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[{"id": 9, "name": "Locație", "slug": "venue"}])
        )
        event_table.select.return_value.eq.return_value.order.return_value.execute.return_value = (
            SimpleNamespace(data=[{"id": 7, "slug": "party", "name": "Petrecere", "status": "active"}])
        )
        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
            patch.object(locations, "get_supabase", return_value=db),
            patch.object(locations, "count_rows", side_effect=RuntimeError("private details")),
            TestClient(app) as client,
        ):
            response = client.get("/api/locations/venue/events", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["events"][0]["photo_count"])
        self.assertIsNone(response.json()["events"][0]["video_count"])


if __name__ == "__main__":
    unittest.main()
