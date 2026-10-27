from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import validate_config
from routers import admin_media, locations, events, media, pages
from upload_limits import UploadBodyLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_config()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(UploadBodyLimitMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(pages.router)
app.include_router(locations.router)
app.include_router(events.router)
app.include_router(media.router)
app.include_router(admin_media.router)
