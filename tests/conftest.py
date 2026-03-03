"""Shared test fixtures."""

import pytest
from fastapi.testclient import TestClient

import app.routers.weather as _weather_module


@pytest.fixture(autouse=True)
def _clear_weather_cache():
    """Reset the in-process weather cache before and after every test."""
    _weather_module._cache.clear()
    yield
    _weather_module._cache.clear()


@pytest.fixture(autouse=True)
def _isolate_settings(tmp_path, monkeypatch):
    """Point layout file to a temp directory so tests don't touch real data."""
    layout_file = tmp_path / "layout.json"
    monkeypatch.setattr("app.config.settings.layout_file", layout_file)
    monkeypatch.setattr("app.config.settings.ha_base_url", "http://ha-test:8123")
    monkeypatch.setattr("app.config.settings.ha_token", "test-token-abc")


@pytest.fixture()
def client():
    """FastAPI test client."""
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def sample_layout():
    """A minimal layout for testing."""
    return {
        "columns": 12,
        "tiles": [
            {
                "id": "tile_1",
                "entity_id": "light.living_room",
                "label": "Living Room",
                "icon": "mdi-lightbulb",
                "domain": "light",
                "x": 0,
                "y": 0,
                "w": 2,
                "h": 2,
            },
            {
                "id": "tile_2",
                "entity_id": "fan.bedroom",
                "label": "Bedroom Fan",
                "icon": "mdi-fan",
                "domain": "fan",
                "x": 2,
                "y": 0,
                "w": 2,
                "h": 2,
            },
        ],
    }


@pytest.fixture()
def mock_ha_states():
    """Fake Home Assistant state response."""
    return [
        {
            "entity_id": "light.living_room",
            "state": "on",
            "attributes": {"friendly_name": "Living Room", "brightness": 255},
        },
        {
            "entity_id": "fan.bedroom",
            "state": "off",
            "attributes": {"friendly_name": "Bedroom Fan"},
        },
        {
            "entity_id": "switch.garage",
            "state": "off",
            "attributes": {"friendly_name": "Garage"},
        },
    ]
