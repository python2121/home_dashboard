"""Tests for the layout persistence API."""


def test_get_layout_returns_default_when_no_file(client):
    resp = client.get("/api/layout")
    assert resp.status_code == 200
    data = resp.json()
    assert data["columns"] == 12
    assert data["tiles"] == []


def test_save_and_load_layout(client, sample_layout):
    # Save
    resp = client.put("/api/layout", json=sample_layout)
    assert resp.status_code == 200
    assert len(resp.json()["tiles"]) == 2

    # Load back
    resp = client.get("/api/layout")
    assert resp.status_code == 200
    data = resp.json()
    assert data["columns"] == 12
    assert len(data["tiles"]) == 2
    assert data["tiles"][0]["entity_id"] == "light.living_room"
    assert data["tiles"][1]["label"] == "Bedroom Fan"


def test_save_layout_rejects_duplicate_tile_ids(client, sample_layout):
    sample_layout["tiles"][1]["id"] = sample_layout["tiles"][0]["id"]
    resp = client.put("/api/layout", json=sample_layout)
    assert resp.status_code == 400
    assert "Duplicate" in resp.json()["detail"]


def test_save_layout_validates_tile_fields(client):
    bad_layout = {
        "columns": 12,
        "tiles": [
            {
                "id": "t1",
                "entity_id": "light.test",
                "label": "Test",
                "domain": "light",
                "w": 0,  # invalid: must be >= 1
                "h": 2,
                "x": 0,
                "y": 0,
            }
        ],
    }
    resp = client.put("/api/layout", json=bad_layout)
    assert resp.status_code == 422


def test_corrupt_layout_file_returns_default(client, tmp_path, monkeypatch):
    layout_file = tmp_path / "corrupt.json"
    layout_file.write_text("not valid json{{{", encoding="utf-8")
    monkeypatch.setattr("app.config.settings.layout_file", layout_file)

    resp = client.get("/api/layout")
    assert resp.status_code == 200
    assert resp.json()["tiles"] == []
