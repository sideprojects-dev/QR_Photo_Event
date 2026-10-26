import asyncio
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from main import app
from upload_limits import UploadBodyLimitMiddleware


TEST_ENV = {
    "ADMIN_PASSWORD": "example-password-123",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "FOLDER_ID": "test-drive-folder",
    "GOOGLE_DRIVE_TOKEN_JSON": '{"token":"test-token"}',
}


class UploadBodyLimitTests(unittest.TestCase):
    def test_large_declared_request_is_rejected_before_endpoint(self):
        with (
            patch.dict(os.environ, TEST_ENV),
            TestClient(UploadBodyLimitMiddleware(app, max_body_size=100)) as client,
        ):
            response = client.post(
                "/upload/test-event",
                files={"file": ("video.mp4", b"123456789", "video/mp4")},
            )
        self.assertEqual(response.status_code, 413)

    def test_received_chunks_are_counted_without_content_length(self):
        async def consume_body(scope, receive, send):
            while True:
                message = await receive()
                if not message.get("more_body", False):
                    break
            await PlainTextResponse("ok")(scope, receive, send)

        messages = iter([
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"67890", "more_body": False},
        ])
        sent = []

        async def receive():
            return next(messages)

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "path": "/upload/test-event", "headers": []}
        middleware = UploadBodyLimitMiddleware(consume_body, max_body_size=8)
        asyncio.run(middleware(scope, receive, send))

        self.assertEqual(sent[0]["status"], 413)

    def test_understated_content_length_does_not_bypass_limit(self):
        async def consume_body(scope, receive, send):
            await receive()
            await PlainTextResponse("ok")(scope, receive, send)

        async def receive():
            return {"type": "http.request", "body": b"123456789", "more_body": False}

        sent = []

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http",
            "path": "/upload/test-event",
            "headers": [(b"content-length", b"1")],
        }
        middleware = UploadBodyLimitMiddleware(consume_body, max_body_size=8)
        asyncio.run(middleware(scope, receive, send))

        self.assertEqual(sent[0]["status"], 413)


if __name__ == "__main__":
    unittest.main()
