import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import deps
from main import app
from routers import events, locations
from guest_access import event_token, location_token


TEST_ENV = {
    "ADMIN_PASSWORD": "example-password-123",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "FOLDER_ID": "test-drive-folder",
    "GOOGLE_DRIVE_TOKEN_JSON": '{"token":"test-token"}',
    "QR_ACCESS_SECRET": "test-secret-with-at-least-32-characters",
}
ADMIN = {"x-admin-password": TEST_ENV["ADMIN_PASSWORD"]}


class AtomicActivationTests(unittest.TestCase):
    def request_activation(self, outcome="activated", location="venue", error=None):
        db = Mock()
        db.rpc.return_value.execute.return_value = SimpleNamespace(data={"result": outcome})
        db.rpc.return_value.execute.side_effect = error
        with (patch.dict(os.environ, TEST_ENV),
              patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
              patch.object(events, "get_supabase", return_value=db),
              TestClient(app) as client):
            response = client.post(
                f"/api/events/event-a/activate?location_slug={location}", headers=ADMIN
            )
        return response, db

    def test_activation_with_or_without_previous_active_event_uses_one_rpc(self):
        for outcome in ("activated", "already_active"):
            with self.subTest(outcome=outcome):
                response, db = self.request_activation(outcome)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"success": True, "slug": "event-a"})
                db.rpc.assert_called_once_with("activate_event_atomic", {
                    "p_event_slug": "event-a", "p_location_slug": "venue"
                })
                db.table.assert_not_called()

    def test_missing_event_location_or_wrong_location_is_rejected(self):
        for outcome, status in (("event_not_found", 404),
                                ("location_not_found", 404),
                                ("location_mismatch", 404),
                                ("event_unbound", 400)):
            with self.subTest(outcome=outcome):
                response, _ = self.request_activation(outcome)
                self.assertEqual(response.status_code, status)

    def test_database_failure_and_invalid_result_never_report_success(self):
        response, _ = self.request_activation(error=RuntimeError("private database detail"))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private database detail", response.text)
        response, _ = self.request_activation(outcome="unexpected")
        self.assertEqual(response.status_code, 503)

    def test_admin_authentication_is_required_before_rpc(self):
        db = Mock()
        with (patch.dict(os.environ, TEST_ENV),
              patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
              patch.object(events, "get_supabase", return_value=db),
              TestClient(app) as client):
            response = client.post("/api/events/event-a/activate?location_slug=venue")
        self.assertEqual(response.status_code, 401)
        db.rpc.assert_not_called()

    def test_new_event_remains_archived_if_activation_fails(self):
        db = Mock()
        location_table = Mock()
        event_table = Mock()
        db.table.side_effect = lambda name: (
            location_table if name == "locations" else event_table
        )
        location_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[{"id": 9, "folder_id": "location-folder"}])
        )
        event_table.select.return_value.eq.return_value.execute.return_value = (
            SimpleNamespace(data=[])
        )
        event_table.insert.return_value.execute.return_value = (
            SimpleNamespace(data=[{"id": 2}])
        )
        db.rpc.return_value.execute.side_effect = RuntimeError("simulated DB failure")
        drive = Mock()
        drive.files.return_value.create.return_value.execute.return_value = (
            {"id": "new-folder"}
        )
        with (patch.dict(os.environ, TEST_ENV),
              patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
              patch.object(events, "get_supabase", return_value=db),
              patch.object(events, "get_drive_service", return_value=drive),
              TestClient(app) as client):
            response = client.post(
                "/api/create-event?event_name=Event%20B&location_slug=venue",
                headers=ADMIN,
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(event_table.insert.call_args.args[0]["status"], "archived")
        event_table.update.assert_not_called()
        drive.files.return_value.delete.assert_not_called()

    def test_concurrent_http_requests_each_use_database_rpc(self):
        # This verifies routing only; actual row locking needs PostgreSQL.
        db = Mock()
        called = []
        lock = threading.Lock()

        def execute():
            with lock:
                called.append(1)
            return SimpleNamespace(data={"result": "activated"})

        db.rpc.return_value.execute.side_effect = execute
        with (patch.dict(os.environ, TEST_ENV),
              patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
              patch.object(events, "get_supabase", return_value=db)):
            def activate(slug):
                with TestClient(app) as client:
                    return client.post(f"/api/events/{slug}/activate?location_slug=venue", headers=ADMIN)
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(activate, ("event-a", "event-b")))
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(len(called), 2)
        db.table.assert_not_called()

    def test_requests_for_different_locations_are_not_locked_in_python(self):
        db = Mock()
        first_started = threading.Event()
        release_first = threading.Event()

        def rpc(name, params):
            call = Mock()
            if params["p_location_slug"] == "venue-a":
                def slow():
                    first_started.set()
                    if not release_first.wait(2):
                        raise RuntimeError("test timed out")
                    return SimpleNamespace(data={"result": "activated"})
                call.execute.side_effect = slow
            else:
                call.execute.return_value = SimpleNamespace(data={"result": "activated"})
            return call

        db.rpc.side_effect = rpc
        with (patch.dict(os.environ, TEST_ENV),
              patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
              patch.object(events, "get_supabase", return_value=db)):
            def activate(slug, venue):
                with TestClient(app) as client:
                    return client.post(
                        f"/api/events/{slug}/activate?location_slug={venue}", headers=ADMIN
                    )
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(activate, "event-a", "venue-a")
                try:
                    self.assertTrue(first_started.wait(1))
                    second = pool.submit(activate, "event-b", "venue-b")
                    self.assertEqual(second.result(timeout=1).status_code, 200)
                finally:
                    release_first.set()
                self.assertEqual(first.result(timeout=1).status_code, 200)

    def test_master_qr_uses_current_active_event_after_activation(self):
        db = Mock()
        location_table = Mock()
        event_table = Mock()
        db.table.side_effect = lambda name: (
            location_table if name == "locations" else event_table
        )
        location_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[{"id": 9}])
        )
        event_query = event_table.select.return_value.eq.return_value.eq.return_value.limit.return_value
        event_query.execute.side_effect = [
            SimpleNamespace(data=[{"id": 1, "slug": "event-a"}]),
            SimpleNamespace(data=[{"id": 2, "slug": "event-b"}]),
        ]
        db.rpc.return_value.execute.return_value = SimpleNamespace(data={"result": "activated"})
        with (patch.dict(os.environ, TEST_ENV),
              patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
              patch.object(locations, "get_supabase", return_value=db),
              patch.object(events, "get_supabase", return_value=db)):
            first = locations.master_redirect_location("venue", location_token(9))
            events.activate_event("event-b", "venue")
            second = locations.master_redirect_location("venue", location_token(9))
        with patch.dict(os.environ, TEST_ENV):
            self.assertEqual(first.headers["location"], f"/event/event-a?access={event_token(1)}")
            self.assertEqual(second.headers["location"], f"/event/event-b?access={event_token(2)}")


if __name__ == "__main__":
    unittest.main()
