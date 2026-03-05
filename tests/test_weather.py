"""Tests for the weather route.

_geocode and _fetch_weather are patched at the module level so tests run
without network access and without complex httpx mocking.
"""

import time
from unittest.mock import AsyncMock, patch

import app.routers.weather as weather_module

# ── Fixtures / helpers ───────────────────────────────────────────────────────

_GEOCODE_RESULT = (40.7128, -74.0060)  # lat, lon for NYC

_OPEN_METEO_PAYLOAD = {
    "current": {
        "temperature_2m": 72.4,
        "weather_code": 0,
    },
    "daily": {
        "time": [
            "2024-06-01", "2024-06-02", "2024-06-03",
            "2024-06-04", "2024-06-05", "2024-06-06",
        ],
        "weather_code": [0, 2, 61, 3, 0, 80],
        "temperature_2m_max": [78.1, 75.0, 70.2, 68.0, 72.0, 69.5],
        "temperature_2m_min": [65.3, 62.0, 58.8, 55.0, 60.0, 57.0],
    },
}


def _mock_geocode(result=_GEOCODE_RESULT):
    return AsyncMock(return_value=result)


def _mock_fetch(payload=_OPEN_METEO_PAYLOAD):
    return AsyncMock(return_value=payload)


# ── Happy path ───────────────────────────────────────────────────────────────


@patch("app.routers.weather._fetch_weather", new_callable=AsyncMock)
@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_get_weather_success(mock_geo, mock_fetch, client):
    mock_geo.return_value = _GEOCODE_RESULT
    mock_fetch.return_value = _OPEN_METEO_PAYLOAD

    resp = client.get("/api/weather?zip_code=10001&country_code=US&unit=fahrenheit")
    assert resp.status_code == 200

    data = resp.json()
    cur = data["current"]
    assert cur["temp"] == 72       # round(72.4)
    assert cur["high"] == 78       # round(78.1)
    assert cur["low"] == 65        # round(65.3)
    assert cur["icon"] == "mdi-weather-sunny"
    assert cur["desc"] == "Clear sky"
    assert cur["unit"] == "\u00b0F"

    assert len(data["forecast"]) == 5
    # Tomorrow: weather_code=2 → partly cloudy
    assert data["forecast"][0]["date"] == "2024-06-02"
    assert data["forecast"][0]["icon"] == "mdi-weather-partly-cloudy"
    assert data["forecast"][0]["high"] == 75
    assert data["forecast"][0]["low"] == 62


@patch("app.routers.weather._fetch_weather", new_callable=AsyncMock)
@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_get_weather_celsius(mock_geo, mock_fetch, client):
    mock_geo.return_value = _GEOCODE_RESULT
    mock_fetch.return_value = _OPEN_METEO_PAYLOAD

    resp = client.get("/api/weather?zip_code=10001&unit=celsius")
    assert resp.status_code == 200
    assert resp.json()["current"]["unit"] == "\u00b0C"


# ── Caching ──────────────────────────────────────────────────────────────────


@patch("app.routers.weather._fetch_weather", new_callable=AsyncMock)
@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_cache_hit_skips_upstream(mock_geo, mock_fetch, client):
    mock_geo.return_value = _GEOCODE_RESULT
    mock_fetch.return_value = _OPEN_METEO_PAYLOAD

    # First request populates the cache
    resp1 = client.get("/api/weather?zip_code=10001")
    assert resp1.status_code == 200
    assert mock_geo.call_count == 1
    assert mock_fetch.call_count == 1

    # Second request should come from cache
    resp2 = client.get("/api/weather?zip_code=10001")
    assert resp2.status_code == 200
    assert mock_geo.call_count == 1   # not called again
    assert mock_fetch.call_count == 1  # not called again
    assert resp2.json() == resp1.json()


@patch("app.routers.weather._fetch_weather", new_callable=AsyncMock)
@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_cache_expired_triggers_refresh(mock_geo, mock_fetch, client):
    mock_geo.return_value = _GEOCODE_RESULT
    mock_fetch.return_value = _OPEN_METEO_PAYLOAD

    client.get("/api/weather?zip_code=10001")
    assert mock_geo.call_count == 1

    # Manually expire the cache entry
    key = "10001:US:fahrenheit"
    weather_module._cache[key]["expires"] = time.time() - 1

    client.get("/api/weather?zip_code=10001")
    assert mock_geo.call_count == 2   # fetched again after expiry


# ── Validation errors ────────────────────────────────────────────────────────


def test_invalid_unit_returns_400(client):
    resp = client.get("/api/weather?zip_code=10001&unit=kelvin")
    assert resp.status_code == 400
    assert "unit" in resp.json()["detail"]


def test_missing_zip_returns_422(client):
    resp = client.get("/api/weather")
    assert resp.status_code == 422


# ── Upstream error propagation ───────────────────────────────────────────────


@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_geocode_not_found_returns_404(mock_geo, client):
    from fastapi import HTTPException

    mock_geo.side_effect = HTTPException(status_code=404, detail="Cannot locate ZIP")

    resp = client.get("/api/weather?zip_code=00000")
    assert resp.status_code == 404


@patch("app.routers.weather._fetch_weather", new_callable=AsyncMock)
@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_weather_api_error_returns_502(mock_geo, mock_fetch, client):
    from fastapi import HTTPException

    mock_geo.return_value = _GEOCODE_RESULT
    mock_fetch.side_effect = HTTPException(status_code=502, detail="Weather service error")

    resp = client.get("/api/weather?zip_code=10001")
    assert resp.status_code == 502


# ── Cache key isolation ──────────────────────────────────────────────────────


@patch("app.routers.weather._fetch_weather", new_callable=AsyncMock)
@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_different_units_use_separate_cache_keys(mock_geo, mock_fetch, client):
    mock_geo.return_value = _GEOCODE_RESULT
    mock_fetch.return_value = _OPEN_METEO_PAYLOAD

    client.get("/api/weather?zip_code=10001&unit=fahrenheit")
    client.get("/api/weather?zip_code=10001&unit=celsius")

    # Each unit triggers its own upstream fetch (different cache keys)
    assert mock_fetch.call_count == 2
