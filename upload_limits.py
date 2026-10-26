from starlette.responses import PlainTextResponse


MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_VIDEO_BYTES = 250 * 1024 * 1024
MAX_UPLOAD_REQUEST_BYTES = MAX_VIDEO_BYTES + 1024 * 1024


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
