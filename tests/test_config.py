"""Tests for application configuration."""

from app.config import Settings


def test_default_settings():
    s = Settings(ha_base_url="http://localhost:8123", ha_token="abc123")
    assert s.ha_base_url == "http://localhost:8123"
    assert s.ha_token == "abc123"


def test_ha_headers():
    s = Settings(ha_token="my-secret-token")
    headers = s.ha_headers
    assert headers["Authorization"] == "Bearer my-secret-token"
    assert headers["Content-Type"] == "application/json"


def test_default_layout_file():
    s = Settings()
    assert s.layout_file.name == "layout.json"
    assert "data" in str(s.layout_file)
