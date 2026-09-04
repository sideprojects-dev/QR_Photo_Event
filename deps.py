import os
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


def require_admin(x_admin_password: str = Header(None)):
    # Folosit ca dependency FastAPI (Depends(require_admin)) în locul
    # verificării manuale repetate în fiecare endpoint de admin.
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
