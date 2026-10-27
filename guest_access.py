import hashlib
import hmac
import os
from urllib.parse import quote, urlencode


def _token(kind: str, record_id) -> str:
    secret = os.environ["QR_ACCESS_SECRET"].encode("utf-8")
    message = f"{kind}:{record_id}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def event_token(event_id) -> str:
    return _token("event", event_id)


def location_token(location_id) -> str:
    return _token("location", location_id)


def has_event_access(event_id, supplied_token: str | None) -> bool:
    return bool(supplied_token) and hmac.compare_digest(
        event_token(event_id), supplied_token
    )


def has_location_access(location_id, supplied_token: str | None) -> bool:
    return bool(supplied_token) and hmac.compare_digest(
        location_token(location_id), supplied_token
    )


def event_path(slug: str, event_id) -> str:
    return f"/event/{quote(slug, safe='')}?{urlencode({'access': event_token(event_id)})}"


def master_path(slug: str, location_id) -> str:
    return (
        f"/event/master/{quote(slug, safe='')}?"
        f"{urlencode({'access': location_token(location_id)})}"
    )


def absolute_guest_url(request, path: str) -> str:
    base_url = os.getenv("RENDER_EXTERNAL_URL", "").strip() or str(request.base_url)
    return f"{base_url.rstrip('/')}{path}"
