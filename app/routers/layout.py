"""Layout persistence routes.

Tile layout is stored as a JSON file on disk (no database needed).
The file path is configured via settings.layout_file.
"""

import contextlib
import json
import logging
import os
import tempfile

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.models import Layout

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/layout", tags=["layout"])

DEFAULT_LAYOUT = Layout(
    columns=12,
    tiles=[],
)


def _read_layout() -> Layout:
    """Read the layout from disk, returning the default if the file doesn't exist."""
    path = settings.layout_file
    if not path.exists():
        return DEFAULT_LAYOUT
    try:
        raw = path.read_text(encoding="utf-8")
        return Layout.model_validate_json(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Corrupt layout file at %s — returning default layout", path)
        return DEFAULT_LAYOUT


def _write_layout(layout: Layout) -> None:
    """Persist the layout to disk atomically via write-to-temp + rename."""
    path = settings.layout_file
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
async def get_layout() -> Layout:
    """Return the current dashboard layout."""
    return _read_layout()


@router.put("")
async def save_layout(layout: Layout) -> Layout:
    """Replace the entire dashboard layout."""
    # Validate tile IDs are unique
    ids = [t.id for t in layout.tiles]
    if len(ids) != len(set(ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate tile IDs in layout",
        )
    _write_layout(layout)
    return layout
