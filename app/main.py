"""Home Dashboard — FastAPI application entrypoint."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import PROJECT_ROOT, settings
from app.routers import ha_proxy, layout, moon, weather

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

app = FastAPI(
    title="Home Dashboard",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

# ---------- Static files & templates ----------
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "app" / "static")), name="static")
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))

# ---------- Routers ----------
app.include_router(ha_proxy.router)
app.include_router(layout.router)
app.include_router(weather.router)
app.include_router(moon.router)


# ---------- Pages ----------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Serve the main dashboard page."""
    return templates.TemplateResponse(request, "index.html")
