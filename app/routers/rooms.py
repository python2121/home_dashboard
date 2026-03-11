"""Rooms routes — named layout contexts.

Each room has its own saved layout file.  Rooms are stored as a JSON
list at ``data/rooms.json`` (same directory as the layout file).
"""

import contextlib
import json
import logging
import os
import re
import secrets
import tempfile
from typing import List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.config import settings
from app.models import Room

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rooms", tags=["rooms"])

ROOM_ID_RE = re.compile(r"^[a-z0-9_]{1,40}$")


class RoomCreate(BaseModel):
    name: str


def _rooms_path():
    return settings.layout_file.parent / "rooms.json"


def _read_rooms() -> List[Room]:
    path = _rooms_path()
    if not path.exists():
        return [Room(id="default", name="Default")]
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return [Room(**r) for r in data]
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("Corrupt rooms file at %s — returning default", path)
        return [Room(id="default", name="Default")]


def _write_rooms(rooms: List[Room]) -> None:
    path = _rooms_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [r.model_dump() for r in rooms]
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, str(path))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@router.get("", response_model=List[Room])
async def list_rooms() -> List[Room]:
    """Return all rooms."""
    return _read_rooms()


@router.post("", response_model=Room, status_code=status.HTTP_201_CREATED)
async def create_room(body: RoomCreate) -> Room:
    """Create a new room."""
    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room name cannot be empty",
        )
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "room"
    slug = slug[:20]
    room_id = f"{slug}_{secrets.token_hex(3)}"
    rooms = _read_rooms()
    new_room = Room(id=room_id, name=name)
    rooms.append(new_room)
    _write_rooms(rooms)
    return new_room


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(room_id: str) -> None:
    """Delete a room and its layout file. Cannot delete the last room."""
    if not ROOM_ID_RE.match(room_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid room ID",
        )
    rooms = _read_rooms()
    if len(rooms) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the last room",
        )
    new_rooms = [r for r in rooms if r.id != room_id]
    if len(new_rooms) == len(rooms):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    _write_rooms(new_rooms)
    # Delete the layout file for this room (ignore if absent)
    layout_file = settings.layout_file.parent / f"layout_{room_id}.json"
    with contextlib.suppress(OSError):
        layout_file.unlink()
