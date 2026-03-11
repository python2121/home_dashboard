"""Tests for the rooms API."""

import pytest


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


# ── Room CRUD ────────────────────────────────────────────────────────


def test_list_rooms_default(client):
    """GET /api/rooms returns a default room when no rooms.json exists."""
    res = client.get("/api/rooms")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == "default"
    assert data[0]["name"] == "Default"


def test_create_room(client):
    """POST /api/rooms creates a new room and returns it."""
    res = client.post("/api/rooms", json={"name": "Living Room"})
    assert res.status_code == 201
    room = res.json()
    assert room["name"] == "Living Room"
    assert "living_room" in room["id"]

    # Room appears in list
    rooms = client.get("/api/rooms").json()
    assert len(rooms) == 2
    assert any(r["id"] == room["id"] for r in rooms)


def test_create_room_empty_name(client):
    """POST /api/rooms with empty name returns 400."""
    res = client.post("/api/rooms", json={"name": "   "})
    assert res.status_code == 400


def test_delete_room(client):
    """DELETE /api/rooms/{room_id} removes a room."""
    # Create a room first
    new = client.post("/api/rooms", json={"name": "Bedroom"}).json()
    room_id = new["id"]

    res = client.delete(f"/api/rooms/{room_id}")
    assert res.status_code == 204

    # Room is gone
    rooms = client.get("/api/rooms").json()
    assert not any(r["id"] == room_id for r in rooms)


def test_delete_last_room_fails(client):
    """DELETE /api/rooms/{room_id} fails when only one room remains."""
    res = client.delete("/api/rooms/default")
    assert res.status_code == 400


def test_delete_nonexistent_room(client):
    """DELETE /api/rooms/{room_id} returns 404 for unknown room."""
    # Create a second room so we can attempt delete of a third
    client.post("/api/rooms", json={"name": "Extra"})
    res = client.delete("/api/rooms/does_not_exist")
    assert res.status_code == 404


def test_delete_room_invalid_id(client):
    """DELETE /api/rooms/{room_id} returns 400 for invalid IDs."""
    res = client.delete("/api/rooms/../../etc/passwd")
    assert res.status_code in (400, 404, 422)


# ── Per-room layout isolation ────────────────────────────────────────


def test_layout_isolated_per_room(client):
    """Layouts saved to different rooms don't bleed into each other."""
    layout_a = {
        "columns": 12,
        "tiles": [
            {
                "tile_type": "entity",
                "id": "tile_a",
                "entity_id": "light.room_a",
                "label": "Room A Light",
                "icon": "mdi-lightbulb",
                "domain": "light",
                "x": 0,
                "y": 0,
                "w": 2,
                "h": 2,
            }
        ],
    }
    layout_b = {
        "columns": 12,
        "tiles": [
            {
                "tile_type": "entity",
                "id": "tile_b",
                "entity_id": "light.room_b",
                "label": "Room B Light",
                "icon": "mdi-lightbulb",
                "domain": "light",
                "x": 0,
                "y": 0,
                "w": 2,
                "h": 2,
            }
        ],
    }

    # Create a second room
    room_b = client.post("/api/rooms", json={"name": "Room B"}).json()
    room_b_id = room_b["id"]

    # Save layouts to their respective rooms
    client.put("/api/layout?room_id=default", json=layout_a)
    client.put(f"/api/layout?room_id={room_b_id}", json=layout_b)

    # Retrieve and verify isolation
    res_a = client.get("/api/layout?room_id=default").json()
    res_b = client.get(f"/api/layout?room_id={room_b_id}").json()

    assert res_a["tiles"][0]["id"] == "tile_a"
    assert res_b["tiles"][0]["id"] == "tile_b"


def test_layout_invalid_room_id(client):
    """GET/PUT /api/layout with invalid room_id returns 400."""
    res = client.get("/api/layout?room_id=../../etc/passwd")
    assert res.status_code == 400

    res = client.put(
        "/api/layout?room_id=../../etc/passwd",
        json={"columns": 12, "tiles": []},
    )
    assert res.status_code == 400


def test_layout_unknown_room_returns_empty(client):
    """GET /api/layout for a valid but unused room_id returns empty layout."""
    res = client.get("/api/layout?room_id=nonexistent_room")
    assert res.status_code == 200
    assert res.json()["tiles"] == []
