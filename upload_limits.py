import os
import time
from math import ceil
from threading import Lock

from starlette.responses import JSONResponse, PlainTextResponse

from perf_monitor import PerfTrace


MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_VIDEO_BYTES = 250 * 1024 * 1024
MAX_UPLOAD_REQUEST_BYTES = MAX_VIDEO_BYTES + 1024 * 1024
DEFAULT_MAX_ACTIVE_UPLOADS = 3
DEFAULT_UPLOADS_PER_MINUTE = 120
DEFAULT_UPLOAD_BURST = 30


def _positive_setting(name, default):
    value = os.getenv(name, str(default))
    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if number < 1:
        raise ValueError(f"{name} must be a positive integer")
    return number


class UploadAdmissionMiddleware:
    """Per-process admission control, before multipart parsing or file spooling."""

    def __init__(self, app, max_active=None, per_minute=None, burst=None, clock=None):
        self.app = app
        self.max_active = max_active if max_active is not None else _positive_setting(
            "UPLOAD_MAX_ACTIVE", DEFAULT_MAX_ACTIVE_UPLOADS
        )
        self.per_minute = per_minute if per_minute is not None else _positive_setting(
            "UPLOADS_PER_MINUTE", DEFAULT_UPLOADS_PER_MINUTE
        )
        self.burst = burst if burst is not None else _positive_setting("UPLOAD_BURST", DEFAULT_UPLOAD_BURST)
        if min(self.max_active, self.per_minute, self.burst) < 1:
            raise ValueError("Upload limits must be positive")
        self.clock = clock or time.monotonic
        self.lock = Lock()
        self.active = 0
        self.tokens = float(self.burst)
        self.last_refill = self.clock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or not scope.get("path", "").startswith("/upload/"):
            await self.app(scope, receive, send)
            return

        with self.lock:
            now = self.clock()
            elapsed = max(0, now - self.last_refill)
            self.tokens = min(self.burst, self.tokens + elapsed * self.per_minute / 60)
            self.last_refill = now
            if self.active >= self.max_active:
                retry_after = 2
                admitted = False
            elif self.tokens < 1:
                retry_after = max(1, ceil((1 - self.tokens) * 60 / self.per_minute))
                admitted = False
            else:
                self.tokens -= 1
                self.active += 1
                admitted = True

        if not admitted:
            response = JSONResponse(
                {"detail": "Momentan sunt multe încărcări în desfășurare. Încearcă din nou peste câteva secunde."},
                status_code=429,
                headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return

        trace = PerfTrace("upload_request")
        if trace.enabled:
            scope.setdefault("state", {})["perf_trace_id"] = trace.trace_id
        outcome = "error"
        try:
            await self.app(scope, receive, send)
            outcome = "completed"
        finally:
            trace.emit(outcome)
            with self.lock:
                self.active -= 1


class UploadBodyTooLarge(Exception):
    pass


class UploadBodyLimitMiddleware:
    def __init__(self, app, max_body_size=MAX_UPLOAD_REQUEST_BYTES):
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/upload/"):
            await self.app(scope, receive, send)
            return

        for name, value in scope.get("headers", []):
            if name.lower() != b"content-length":
                continue
            try:
                declared_size = int(value)
            except ValueError:
                break
            if declared_size > self.max_body_size:
                await self._reject(scope, receive, send)
                return

        received_size = 0
        response_started = False

        async def limited_receive():
            nonlocal received_size
            message = await receive()
            if message["type"] == "http.request":
                received_size += len(message.get("body", b""))
                if received_size > self.max_body_size:
                    raise UploadBodyTooLarge
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except UploadBodyTooLarge:
            if response_started:
                raise
            await self._reject(scope, receive, send)

    @staticmethod
    async def _reject(scope, receive, send):
        response = PlainTextResponse(
            "Upload request is too large.",
            status_code=413,
        )
        await response(scope, receive, send)
