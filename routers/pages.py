from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])


@router.get("/")
def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.get("/admin")
def admin_panel():
    with open("static/admin.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())
