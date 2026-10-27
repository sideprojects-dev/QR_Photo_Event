import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from PIL import Image

from guest_access import absolute_guest_url, event_path, event_token, location_token, master_path
import deps
from main import app
from routers import events, locations


TEST_ENV = {
    "ADMIN_PASSWORD": "example-password-123",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "FOLDER_ID": "test-drive-folder",
    "GOOGLE_DRIVE_TOKEN_JSON": '{"token":"test-token"}',
    "QR_ACCESS_SECRET": "test-secret-with-at-least-32-characters",
    "RENDER_EXTERNAL_URL": "",
}


class QRAccessTests(unittest.TestCase):
    def test_absolute_url_falls_back_when_render_variable_is_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            request = SimpleNamespace(base_url="http://localhost:8000/")
            self.assertEqual(
                absolute_guest_url(request, "/event/example"),
                "http://localhost:8000/event/example",
            )

    def test_event_qr_is_admin_only_and_contains_event_access(self):
        db = Mock()
        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[{"id": 7}])
        )
        qr = Mock()
        qr.make_image.return_value = Image.new("RGB", (2, 2))

        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
            patch.object(events, "get_supabase", return_value=db),
            patch.object(events.qrcode, "QRCode", return_value=qr),
            TestClient(app) as client,
        ):
            self.assertEqual(client.get("/api/qr/event-one").status_code, 401)
            response = client.get(
                "/api/qr/event-one",
                headers={"x-admin-password": TEST_ENV["ADMIN_PASSWORD"]},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                qr.add_data.call_args.args[0],
                f"http://testserver/event/event-one?access={event_token(7)}",
            )

    def test_permanent_qr_contains_location_access(self):
        db = Mock()
        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[{"id": 9}])
        )
        qr = Mock()
        qr.make_image.return_value = Image.new("RGB", (2, 2))

        with (
            patch.dict(os.environ, TEST_ENV),
            patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
            patch.object(locations, "get_supabase", return_value=db),
            patch.object(locations.qrcode, "QRCode", return_value=qr),
            TestClient(app) as client,
        ):
            response = client.get(
                "/api/locations/venue/master-qr",
                headers={"x-admin-password": TEST_ENV["ADMIN_PASSWORD"]},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                qr.add_data.call_args.args[0],
                f"http://testserver/event/master/venue?access={location_token(9)}",
            )

    def test_render_qr_urls_use_external_https_base(self):
        external_url = "https://example.onrender.com/"
        db = Mock()
        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[{"id": 7}])
        )
        qr = Mock()
        qr.make_image.return_value = Image.new("RGB", (2, 2))

        with (
            patch.dict(os.environ, {**TEST_ENV, "RENDER_EXTERNAL_URL": external_url}),
            patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
            patch.object(events, "get_supabase", return_value=db),
            patch.object(events.qrcode, "QRCode", return_value=qr),
            TestClient(app) as client,
        ):
            response = client.get(
                "/api/qr/event-one",
                headers={"x-admin-password": TEST_ENV["ADMIN_PASSWORD"]},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                qr.add_data.call_args.args[0],
                "https://example.onrender.com" + event_path("event-one", 7),
            )

        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[{"id": 9}])
        )

        with (
            patch.dict(os.environ, {**TEST_ENV, "RENDER_EXTERNAL_URL": external_url}),
            patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
            patch.object(locations, "get_supabase", return_value=db),
            patch.object(locations.qrcode, "QRCode", return_value=qr),
            TestClient(app) as client,
        ):
            response = client.get(
                "/api/locations/venue/master-qr",
                headers={"x-admin-password": TEST_ENV["ADMIN_PASSWORD"]},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                qr.add_data.call_args.args[0],
                "https://example.onrender.com" + master_path("venue", 9),
            )

    def test_created_event_url_uses_local_or_render_base(self):
        for external_url, expected_base in (
            ("", "http://testserver"),
            ("https://example.onrender.com/", "https://example.onrender.com"),
        ):
            with self.subTest(external_url=bool(external_url)):
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
                    SimpleNamespace(data=[{"id": 7}])
                )
                drive = Mock()
                drive.files.return_value.create.return_value.execute.return_value = (
                    {"id": "event-folder"}
                )

                with (
                    patch.dict(os.environ, {**TEST_ENV, "RENDER_EXTERNAL_URL": external_url}),
                    patch.object(deps, "ADMIN_PASSWORD", TEST_ENV["ADMIN_PASSWORD"]),
                    patch.object(events, "get_supabase", return_value=db),
                    patch.object(events, "get_drive_service", return_value=drive),
                    TestClient(app) as client,
                ):
                    response = client.post(
                        "/api/create-event?event_name=New%20Event&location_slug=venue",
                        headers={"x-admin-password": TEST_ENV["ADMIN_PASSWORD"]},
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        response.json()["url"],
                        expected_base + event_path("new-event", 7),
                    )


if __name__ == "__main__":
    unittest.main()
