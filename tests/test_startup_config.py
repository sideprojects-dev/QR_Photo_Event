import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

import deps
from config import validate_config
from main import app


VALID_ENV = {
    "ADMIN_PASSWORD": "example-password-123",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "FOLDER_ID": "test-drive-folder",
    "GOOGLE_DRIVE_TOKEN_JSON": '{"token":"test-token"}',
    "QR_ACCESS_SECRET": "test-secret-with-at-least-32-characters",
}


class StartupConfigTests(unittest.TestCase):
    def test_each_required_setting_is_rejected_when_missing(self):
        for name in VALID_ENV:
            with self.subTest(name=name):
                settings = VALID_ENV.copy()
                del settings[name]
                with self.assertRaisesRegex(RuntimeError, name) as error:
                    validate_config(settings)
                self.assertNotIn(VALID_ENV["SUPABASE_SERVICE_ROLE_KEY"], str(error.exception))

    def test_default_or_short_admin_password_is_rejected(self):
        for password in ("admin123", "short"):
            with self.subTest(password=password):
                settings = {**VALID_ENV, "ADMIN_PASSWORD": password}
                with self.assertRaisesRegex(RuntimeError, "ADMIN_PASSWORD"):
                    validate_config(settings)

    def test_invalid_supabase_url_is_rejected(self):
        settings = {**VALID_ENV, "SUPABASE_URL": "not-a-url"}
        with self.assertRaisesRegex(RuntimeError, "SUPABASE_URL"):
            validate_config(settings)

    def test_app_startup_rejects_invalid_configuration(self):
        settings = {**VALID_ENV, "ADMIN_PASSWORD": "admin123"}
        with patch.dict(os.environ, settings):
            with self.assertRaisesRegex(RuntimeError, "ADMIN_PASSWORD"):
                with TestClient(app):
                    pass

    def test_app_startup_accepts_valid_configuration(self):
        with patch.dict(os.environ, VALID_ENV):
            with TestClient(app):
                pass

    def test_admin_dependency_rejects_missing_password_or_header(self):
        with patch.object(deps, "ADMIN_PASSWORD", None):
            for header in (None, "anything"):
                with self.subTest(header=header):
                    with self.assertRaises(HTTPException) as error:
                        deps.require_admin(header)
                    self.assertEqual(error.exception.status_code, 401)

        with patch.object(deps, "ADMIN_PASSWORD", VALID_ENV["ADMIN_PASSWORD"]):
            for header in (None, "wrong-password"):
                with self.subTest(header=header):
                    with self.assertRaises(HTTPException) as error:
                        deps.require_admin(header)
                    self.assertEqual(error.exception.status_code, 401)
            self.assertIsNone(deps.require_admin(VALID_ENV["ADMIN_PASSWORD"]))


if __name__ == "__main__":
    unittest.main()
