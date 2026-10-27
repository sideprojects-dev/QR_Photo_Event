import asyncio
import os
import threading
import unittest
from unittest.mock import patch

import httpx
from starlette.responses import PlainTextResponse

from main import app
from routers import media
from upload_limits import UploadAdmissionMiddleware


TEST_ENV = {
    "ADMIN_PASSWORD": "example-password-123",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "FOLDER_ID": "test-drive-folder",
    "GOOGLE_DRIVE_TOKEN_JSON": '{"token":"test-token"}',
    "QR_ACCESS_SECRET": "test-secret-with-at-least-32-characters",
}


async def no_body():
    raise AssertionError("An overloaded request must not read its body")


async def request(middleware, path="/upload/event", method="POST"):
    sent = []

    async def send(message):
        sent.append(message)

    await middleware(
        {"type": "http", "path": path, "method": method, "headers": []},
        no_body,
        send,
    )
    return sent


class UploadAdmissionTests(unittest.TestCase):
    def test_concurrent_limit_rejects_before_body_and_releases_after_completion(self):
        async def scenario():
            release = asyncio.Event()
            started = asyncio.Event()
            count = 0

            async def slow_app(scope, receive, send):
                nonlocal count
                count += 1
                if count == 2:
                    started.set()
                await release.wait()
                await PlainTextResponse("ok")(scope, receive, send)

            limiter = UploadAdmissionMiddleware(slow_app, max_active=2, per_minute=60, burst=10)
            first = asyncio.create_task(request(limiter))
            second = asyncio.create_task(request(limiter))
            await asyncio.wait_for(started.wait(), 1)
            refused = await request(limiter)
            self.assertEqual(refused[0]["status"], 429)
            self.assertIn((b"retry-after", b"2"), refused[0]["headers"])
            self.assertEqual(count, 2)
            self.assertEqual(limiter.active, 2)
            release.set()
            await asyncio.gather(first, second)
            self.assertEqual(limiter.active, 0)
            accepted = await request(limiter)
            self.assertEqual(accepted[0]["status"], 200)

        asyncio.run(scenario())

    def test_rate_limit_refills_without_using_ip_or_qr(self):
        async def immediate(scope, receive, send):
            await PlainTextResponse("ok")(scope, receive, send)

        async def scenario():
            now = [0.0]
            limiter = UploadAdmissionMiddleware(
                immediate, max_active=2, per_minute=60, burst=2,
                clock=lambda: now[0],
            )
            self.assertEqual((await request(limiter))[0]["status"], 200)
            self.assertEqual((await request(limiter))[0]["status"], 200)
            refused = await request(limiter)
            self.assertEqual(refused[0]["status"], 429)
            self.assertIn((b"retry-after", b"1"), refused[0]["headers"])
            self.assertEqual((await request(limiter, "/"))[0]["status"], 200)
            now[0] = 1.0
            self.assertEqual((await request(limiter))[0]["status"], 200)

        asyncio.run(scenario())

    def test_error_and_cancellation_release_active_slot(self):
        async def scenario():
            async def failing(scope, receive, send):
                raise RuntimeError("simulated failure")

            limiter = UploadAdmissionMiddleware(failing, max_active=1, per_minute=60, burst=3)
            with self.assertRaises(RuntimeError):
                await request(limiter)
            self.assertEqual(limiter.active, 0)

            started = asyncio.Event()

            async def waiting(scope, receive, send):
                started.set()
                await asyncio.Event().wait()

            limiter.app = waiting
            pending = asyncio.create_task(request(limiter))
            await started.wait()
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
            self.assertEqual(limiter.active, 0)

        asyncio.run(scenario())

    def test_slow_drive_upload_does_not_block_other_endpoint(self):
        async def scenario():
            started = threading.Event()
            release = threading.Event()

            def slow_drive_upload(**kwargs):
                started.set()
                if not release.wait(3):
                    raise RuntimeError("simulated timeout")
                return "drive-file"

            with (
                patch.object(media, "get_supabase", return_value=object()),
                patch.object(media, "get_event_by_slug", return_value={"id": 1, "folder_id": "folder"}),
                patch.object(media, "has_event_access", return_value=True),
                patch.object(media, "get_drive_service", return_value=object()),
                patch.object(media, "upload_file_to_drive", side_effect=slow_drive_upload),
                patch.object(media, "save_media_record", return_value={"id": 1}),
            ):
                protected_app = UploadAdmissionMiddleware(
                    app, max_active=1, per_minute=60, burst=3
                )
                transport = httpx.ASGITransport(app=protected_app)
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                    file_data = {"file": ("clip.mp4", b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isom", "video/mp4")}
                    upload = asyncio.create_task(client.post(
                        "/upload/event?access=test",
                        files=file_data,
                    ))
                    try:
                        self.assertTrue(await asyncio.to_thread(started.wait, 2))
                        refused = await client.post("/upload/event?access=test", files=file_data)
                        self.assertEqual(refused.status_code, 429)
                        self.assertEqual(refused.headers["Retry-After"], "2")
                        page = await asyncio.wait_for(client.get("/"), 1)
                        self.assertEqual(page.status_code, 200)
                    finally:
                        release.set()
                    self.assertEqual((await upload).status_code, 200)
                    self.assertEqual((await client.post("/upload/event?access=test", files=file_data)).status_code, 200)

        with patch.dict(os.environ, TEST_ENV):
            asyncio.run(scenario())
