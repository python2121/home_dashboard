"""Tests for the moon phase route.

Phase data is computed locally; _geocode and _fetch_usno are patched at the
module level so tests run without network access.
"""

import time
from unittest.mock import AsyncMock, patch

import app.routers.moon as moon_module

# ── Fixtures / helpers ───────────────────────────────────────────────────────

_GEOCODE_RESULT = (40.7128, -74.0060)

_USNO_PAYLOAD = {
    "Rise": "22:13",
    "Set": "09:49",
    "Upper Transit": "16:01",
}


# ── Happy path ───────────────────────────────────────────────────────────────


@patch("app.routers.moon._fetch_usno", new_callable=AsyncMock)
@patch("app.routers.moon._geocode", new_callable=AsyncMock)
def test_get_moon_success(mock_geo, mock_usno, client):
    mock_geo.return_value = _GEOCODE_RESULT
    mock_usno.return_value = _USNO_PAYLOAD

    resp = client.get("/api/moon?zip_code=10001&country_code=US")
    assert resp.status_code == 200

    data = resp.json()
    # Phase is computed locally — verify all fields are present with correct types
    assert isinstance(data["phase"], str)
    assert len(data["phase"]) > 0
    assert 0 <= data["illumination"] <= 100
    assert 0 <= data["age"] <= 30
    assert 0 <= data["fraction"] <= 1
    assert data["moonrise"] == "22:13"
    assert data["moonset"] == "09:49"
    assert data["moon_transit"] == "16:01"
    assert isinstance(data["moonrise_relative"], str)
    assert isinstance(data["moonset_relative"], str)
    assert isinstance(data["moon_transit_relative"], str)


# ── Local phase computation ──────────────────────────────────────────────────


def test_compute_moon_phase_ranges():
    """Verify computed values are in valid ranges."""
    import datetime

    result = moon_module._compute_moon_phase(datetime.datetime.now(datetime.timezone.utc))
    assert result["phase"] in (
        "New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
        "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent",
    )
    assert 0 <= result["illumination"] <= 100
    assert 0 <= result["age"] <= 30
    assert 0 <= result["fraction"] <= 1


def test_compute_moon_phase_known_full_moon():
    """Jan 13, 2025 was a known full moon — verify high illumination."""
    import datetime

    # Known full moon date
    dt = datetime.datetime(2025, 1, 13, 22, 0, 0, tzinfo=datetime.timezone.utc)
    result = moon_module._compute_moon_phase(dt)
    assert result["illumination"] > 95
    assert result["phase"] == "Full Moon"


def test_compute_moon_phase_known_new_moon():
    """Jan 29, 2025 was a known new moon — verify low illumination."""
    import datetime

    dt = datetime.datetime(2025, 1, 29, 12, 0, 0, tzinfo=datetime.timezone.utc)
    result = moon_module._compute_moon_phase(dt)
    assert result["illumination"] < 5
    assert result["phase"] == "New Moon"


# ── Caching ──────────────────────────────────────────────────────────────────


@patch("app.routers.moon._fetch_usno", new_callable=AsyncMock)
@patch("app.routers.moon._geocode", new_callable=AsyncMock)
def test_moon_cache_hit(mock_geo, mock_usno, client):
    mock_geo.return_value = _GEOCODE_RESULT
    mock_usno.return_value = _USNO_PAYLOAD

    resp1 = client.get("/api/moon?zip_code=10001")
    assert resp1.status_code == 200
    assert mock_geo.call_count == 1

    resp2 = client.get("/api/moon?zip_code=10001")
    assert resp2.status_code == 200
    assert mock_geo.call_count == 1  # not called again
    assert resp2.json() == resp1.json()


@patch("app.routers.moon._fetch_usno", new_callable=AsyncMock)
@patch("app.routers.moon._geocode", new_callable=AsyncMock)
def test_moon_cache_expired(mock_geo, mock_usno, client):
    mock_geo.return_value = _GEOCODE_RESULT
    mock_usno.return_value = _USNO_PAYLOAD

    client.get("/api/moon?zip_code=10001")
    assert mock_geo.call_count == 1

    key = "moon:10001:US"
    moon_module._moon_cache[key]["expires"] = time.time() - 1

    client.get("/api/moon?zip_code=10001")
    assert mock_geo.call_count == 2


# ── Error handling ───────────────────────────────────────────────────────────


@patch("app.routers.moon._fetch_usno", new_callable=AsyncMock)
@patch("app.routers.moon._geocode", new_callable=AsyncMock)
def test_moon_usno_error_graceful(mock_geo, mock_usno, client):
    """When USNO is unavailable, phase data still returns with empty rise/set."""
    mock_geo.return_value = _GEOCODE_RESULT
    mock_usno.return_value = None  # graceful degradation

    resp = client.get("/api/moon?zip_code=10001")
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data["phase"], str)
    assert data["moonrise"] == ""
    assert data["moonset"] == ""
    assert data["moon_transit"] == ""


@patch("app.routers.moon._geocode", new_callable=AsyncMock)
def test_moon_geocode_not_found(mock_geo, client):
    from fastapi import HTTPException

    mock_geo.side_effect = HTTPException(status_code=404, detail="Cannot locate ZIP")

    resp = client.get("/api/moon?zip_code=00000")
    assert resp.status_code == 404


def test_moon_missing_zip_returns_422(client):
    resp = client.get("/api/moon")
    assert resp.status_code == 422
