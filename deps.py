import os
from secrets import compare_digest

from fastapi import HTTPException, Header
from supabase import create_client

from config import ADMIN_PASSWORD


def get_supabase():
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not service_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is missing from environment")

    return create_client(
        os.getenv("SUPABASE_URL"),
        service_key
    )


def count_rows(supabase, table: str, filters=(), media_kind: str | None = None) -> int:
    """Count rows through PostgREST without downloading them."""
    query = supabase.table(table).select("id", count="exact", head=True)
    for column, value in filters:
        query = query.eq(column, value)
    if media_kind:
        query = query.like("content_type", f"{media_kind}/%")
    result = query.execute()
    if result.count is None:
        raise RuntimeError("Supabase did not return a count")
    return result.count


def require_admin(x_admin_password: str = Header(None)):
    # Folosit ca dependency FastAPI (Depends(require_admin)) în locul
    # verificării manuale repetate în fiecare endpoint de admin.
    if (
        not ADMIN_PASSWORD
        or not x_admin_password
        or not compare_digest(x_admin_password, ADMIN_PASSWORD)
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")
