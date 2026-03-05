"""Tests for the /api/weather/chart endpoint.

_geocode, _fetch_pirate_weather, and _fetch_open_meteo_chart are patched at
the module level so tests run without network access.
"""

import time
from unittest.mock import AsyncMock, patch

import app.routers.weather as weather_module

# ── Fixtures / helpers ───────────────────────────────────────────────────────

_GEOCODE_RESULT = (40.7128, -74.0060)  # NYC lat/lon

# 60 minutes of data with rain (prob > 0.10 in first half)
_PIRATE_RAIN = {
    "minutely": {
        "data": [
            {"time": 1700000000 + i * 60, "precipProbability": 0.5 if i < 30 else 0.05}
            for i in range(60)
        ]
    }
}

# 60 minutes of data with no rain (all probs <= 0.10)
_PIRATE_NO_RAIN = {
    "minutely": {
        "data": [
            {"time": 1700000000 + i * 60, "precipProbability": 0.05}
            for i in range(60)
        ]
    }
}

# Open-Meteo hourly chart response (48 hours so start_idx always finds 6 points)
_METEO_CHART = {
    "utc_offset_seconds": 0,
    "hourly": {
        "time": [f"2024-06-{1 + h // 24:02d}T{h % 24:02d}:00" for h in range(48)],
        "temperature_2m": [70.0 + (h % 10) for h in range(48)],
    },
    "daily": {
        "sunrise": ["2024-06-01T06:30"],
        "sunset":  ["2024-06-01T20:15"],
    },
}


# ── Happy path ───────────────────────────────────────────────────────────────


@patch("app.routers.weather._fetch_open_meteo_chart", new_callable=AsyncMock)
@patch("app.routers.weather._fetch_pirate_weather", new_callable=AsyncMock)
@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_rain_mode_when_prob_exceeds_threshold(mock_geo, mock_pirate, mock_meteo, client):
    mock_geo.return_value    = _GEOCODE_RESULT
    mock_pirate.return_value = _PIRATE_RAIN
    mock_meteo.return_value  = _METEO_CHART

    resp = client.get("/api/weather/chart?zip_code=10001&country_code=US&unit=fahrenheit")
    assert resp.status_code == 200

    data = resp.json()
    assert data["mode"] == "rain"
    assert "bars" in data
    assert len(data["bars"]) == 60
    # First bar should have prob = 0.5
    assert data["bars"][0]["prob"] == 0.5
    assert data["bars"][0]["min"] == 0


@patch("app.routers.weather._fetch_open_meteo_chart", new_callable=AsyncMock)
@patch("app.routers.weather._fetch_pirate_weather", new_callable=AsyncMock)
@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_temp_mode_when_no_rain(mock_geo, mock_pirate, mock_meteo, client):
    mock_geo.return_value    = _GEOCODE_RESULT
    mock_pirate.return_value = _PIRATE_NO_RAIN
    mock_meteo.return_value  = _METEO_CHART

    resp = client.get("/api/weather/chart?zip_code=10001&country_code=US&unit=fahrenheit")
    assert resp.status_code == 200

    data = resp.json()
    assert data["mode"] == "temp"
    assert "points" in data
    assert len(data["points"]) == 6
    assert data["unit"] == "\u00b0F"
    assert "sunrise_iso" in data
    assert "sunset_iso" in data


@patch("app.routers.weather._fetch_open_meteo_chart", new_callable=AsyncMock)
@patch("app.routers.weather._fetch_pirate_weather", new_callable=AsyncMock)
@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_temp_mode_celsius(mock_geo, mock_pirate, mock_meteo, client):
    mock_geo.return_value    = _GEOCODE_RESULT
    mock_pirate.return_value = _PIRATE_NO_RAIN
    mock_meteo.return_value  = _METEO_CHART

    resp = client.get("/api/weather/chart?zip_code=10001&unit=celsius")
    assert resp.status_code == 200
    assert resp.json()["unit"] == "\u00b0C"


# ── Caching ──────────────────────────────────────────────────────────────────


@patch("app.routers.weather._fetch_open_meteo_chart", new_callable=AsyncMock)
@patch("app.routers.weather._fetch_pirate_weather", new_callable=AsyncMock)
@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_chart_cache_hit(mock_geo, mock_pirate, mock_meteo, client):
    mock_geo.return_value    = _GEOCODE_RESULT
    mock_pirate.return_value = _PIRATE_NO_RAIN
    mock_meteo.return_value  = _METEO_CHART

    # First request populates the cache
    resp1 = client.get("/api/weather/chart?zip_code=10001")
    assert resp1.status_code == 200
    assert mock_geo.call_count == 1
    assert mock_pirate.call_count == 1
    assert mock_meteo.call_count == 1

    # Second request should come from cache
    resp2 = client.get("/api/weather/chart?zip_code=10001")
    assert resp2.status_code == 200
    assert mock_geo.call_count == 1    # not called again
    assert mock_pirate.call_count == 1  # not called again
    assert mock_meteo.call_count == 1   # not called again
    assert resp2.json() == resp1.json()


@patch("app.routers.weather._fetch_open_meteo_chart", new_callable=AsyncMock)
@patch("app.routers.weather._fetch_pirate_weather", new_callable=AsyncMock)
@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_chart_cache_expired_triggers_refresh(mock_geo, mock_pirate, mock_meteo, client):
    mock_geo.return_value    = _GEOCODE_RESULT
    mock_pirate.return_value = _PIRATE_NO_RAIN
    mock_meteo.return_value  = _METEO_CHART

    client.get("/api/weather/chart?zip_code=10001")
    assert mock_geo.call_count == 1

    # Manually expire the cache entry
    key = "chart:10001:US:fahrenheit"
    weather_module._chart_cache[key]["expires"] = time.time() - 1

    client.get("/api/weather/chart?zip_code=10001")
    assert mock_geo.call_count == 2   # fetched again after expiry


# ── Validation errors ────────────────────────────────────────────────────────


def test_invalid_unit_returns_400(client):
    resp = client.get("/api/weather/chart?zip_code=10001&unit=kelvin")
    assert resp.status_code == 400
    assert "unit" in resp.json()["detail"]


def test_missing_zip_returns_422(client):
    resp = client.get("/api/weather/chart")
    assert resp.status_code == 422


# ── Missing API key ──────────────────────────────────────────────────────────


def test_missing_pirate_key_returns_503(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.pirate_weather_key", "")
    resp = client.get("/api/weather/chart?zip_code=10001")
    assert resp.status_code == 503
    assert "key" in resp.json()["detail"].lower()


# ── Upstream error propagation ───────────────────────────────────────────────


@patch("app.routers.weather._fetch_open_meteo_chart", new_callable=AsyncMock)
@patch("app.routers.weather._fetch_pirate_weather", new_callable=AsyncMock)
@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_pirate_weather_error_returns_502(mock_geo, mock_pirate, mock_meteo, client):
    from fastapi import HTTPException

    mock_geo.return_value   = _GEOCODE_RESULT
    mock_pirate.side_effect = HTTPException(status_code=502, detail="Pirate Weather error")
    mock_meteo.return_value = _METEO_CHART

    resp = client.get("/api/weather/chart?zip_code=10001")
    assert resp.status_code == 502


@patch("app.routers.weather._fetch_open_meteo_chart", new_callable=AsyncMock)
@patch("app.routers.weather._fetch_pirate_weather", new_callable=AsyncMock)
@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_open_meteo_chart_error_returns_502(mock_geo, mock_pirate, mock_meteo, client):
    from fastapi import HTTPException

    mock_geo.return_value   = _GEOCODE_RESULT
    mock_pirate.return_value = _PIRATE_RAIN
    mock_meteo.side_effect  = HTTPException(status_code=502, detail="Open-Meteo error")

    resp = client.get("/api/weather/chart?zip_code=10001")
    assert resp.status_code == 502


@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_geocode_not_found_returns_404(mock_geo, client):
    from fastapi import HTTPException

    mock_geo.side_effect = HTTPException(status_code=404, detail="Cannot locate ZIP")

    resp = client.get("/api/weather/chart?zip_code=00000")
    assert resp.status_code == 404


# ── Cache key isolation ──────────────────────────────────────────────────────


@patch("app.routers.weather._fetch_open_meteo_chart", new_callable=AsyncMock)
@patch("app.routers.weather._fetch_pirate_weather", new_callable=AsyncMock)
@patch("app.routers.weather._geocode", new_callable=AsyncMock)
def test_different_units_use_separate_cache_keys(mock_geo, mock_pirate, mock_meteo, client):
    mock_geo.return_value    = _GEOCODE_RESULT
    mock_pirate.return_value = _PIRATE_NO_RAIN
    mock_meteo.return_value  = _METEO_CHART

    client.get("/api/weather/chart?zip_code=10001&unit=fahrenheit")
    client.get("/api/weather/chart?zip_code=10001&unit=celsius")

    # Each unit triggers its own upstream fetch (different cache keys)
    assert mock_pirate.call_count == 2
    assert mock_meteo.call_count == 2
