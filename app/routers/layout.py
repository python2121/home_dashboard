"""Layout persistence routes.

Each room has its own layout file:
  - "default" room  → settings.layout_file  (e.g. data/layout.json)
  - other rooms     → data/layout_{room_id}.json
"""

import contextlib
import json
import logging
import os
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status

from app.config import settings
from app.models import Layout

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/layout", tags=["layout"])

ROOM_ID_RE = re.compile(r"^[a-z0-9_]{1,40}$")

DEFAULT_LAYOUT = Layout(columns=12, tiles=[])


def _layout_path(room_id: str) -> Path:
    base = settings.layout_file
    if room_id == "default":
        return base
    return base.parent / f"layout_{room_id}.json"


def _read_layout(room_id: str) -> Layout:
    path = _layout_path(room_id)
    if not path.exists():
        return DEFAULT_LAYOUT
    try:
        raw = path.read_text(encoding="utf-8")
        return Layout.model_validate_json(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Corrupt layout file at %s — returning default layout", path)
        return DEFAULT_LAYOUT


def _write_layout(layout: Layout, room_id: str) -> None:
    path = _layout_path(room_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(layout.model_dump_json(indent=2))
        os.replace(tmp_path, str(path))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


@router.get("")
async def get_layout(room_id: str = Query(default="default")) -> Layout:
    """Return the layout for the given room."""
    if not ROOM_ID_RE.match(room_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid room_id",
        )
    return _read_layout(room_id)


@router.put("")
async def save_layout(
    layout: Layout,
    room_id: str = Query(default="default"),
) -> Layout:
    """Replace the layout for the given room."""
    if not ROOM_ID_RE.match(room_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid room_id",
        )
    ids = [t.id for t in layout.tiles]
    if len(ids) != len(set(ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate tile IDs in layout",
        )
    _write_layout(layout, room_id)
    return layout
