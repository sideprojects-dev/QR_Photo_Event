import socket
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx
from google_auth_oauthlib.flow import Flow

from reauthorize_drive import SetupError, wait_for_google_callback


class DriveReauthorizationTests(unittest.TestCase):
    def test_local_callback_code_exchange_keeps_https_token_endpoint(self):
        class ReachedTokenEndpoint(Exception):
            pass

        config = {"web": {
            "client_id": "dummy",
            "client_secret": "dummy",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8000/auth/callback"],
        }}
        flow = Flow.from_client_config(
            config,
            scopes=["https://www.googleapis.com/auth/drive.file"],
            redirect_uri="http://localhost:8000/auth/callback",
        )
        flow.authorization_url(access_type="offline", prompt="consent")
        with patch.object(
            flow.oauth2session, "request", side_effect=ReachedTokenEndpoint
        ):
            with self.assertRaises(ReachedTokenEndpoint):
                flow.fetch_token(code="fake-code")

    def test_occupied_callback_port_fails_before_opening_browser(self):
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen()
            port = blocker.getsockname()[1]
            redirect = urlsplit(f"http://127.0.0.1:{port}/auth/callback")
            with patch("reauthorize_drive.webbrowser.open") as open_browser:
                with self.assertRaises(SetupError) as error:
                    wait_for_google_callback(
                        redirect, "expected-state", "https://accounts.google.com/example", 1
                    )
                self.assertIn("ocupat", str(error.exception))
                open_browser.assert_not_called()

    def test_callback_rejects_wrong_state_before_accepting_code(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        redirect = urlsplit(f"http://127.0.0.1:{port}/auth/callback")
        with (
            patch("reauthorize_drive.webbrowser.open", return_value=True),
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            future = pool.submit(
                wait_for_google_callback,
                redirect,
                "expected-state",
                "https://accounts.google.com/example",
                5,
            )
            with httpx.Client(timeout=1) as client:
                for _ in range(20):
                    try:
                        wrong = client.get(
                            f"http://127.0.0.1:{port}/auth/callback",
                            params={"state": "wrong", "code": "fake-code"},
                        )
                        break
                    except httpx.ConnectError:
                        time.sleep(0.05)
                else:
                    self.fail("OAuth callback server did not start")
                self.assertEqual(wrong.status_code, 400)
                self.assertFalse(future.done())
                correct = client.get(
                    f"http://127.0.0.1:{port}/auth/callback",
                    params={"state": "expected-state", "code": "fake-code"},
                )
                self.assertEqual(correct.status_code, 200)

            authorization_code = future.result(timeout=5)
            self.assertEqual(authorization_code, "fake-code")


if __name__ == "__main__":
    unittest.main()
