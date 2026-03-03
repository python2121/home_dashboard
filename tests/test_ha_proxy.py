"""Tests for the Home Assistant proxy routes.

These tests mock httpx to avoid real HA connections.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx


def _mock_response(status_code=200, json_data=None):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or []
    resp.text = ""
    return resp


@patch("app.routers.ha_proxy.httpx.AsyncClient")
def test_get_all_states(mock_client_cls, client, mock_ha_states):
    mock_instance = AsyncMock()
    mock_instance.request = AsyncMock(return_value=_mock_response(200, mock_ha_states))
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_instance

    resp = client.get("/api/ha/states")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]["entity_id"] == "light.living_room"


@patch("app.routers.ha_proxy.httpx.AsyncClient")
def test_get_single_entity_state(mock_client_cls, client):
    state = {"entity_id": "light.living_room", "state": "on", "attributes": {}}
    mock_instance = AsyncMock()
    mock_instance.request = AsyncMock(return_value=_mock_response(200, state))
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_instance

    resp = client.get("/api/ha/states/light.living_room")
    assert resp.status_code == 200
    assert resp.json()["state"] == "on"


@patch("app.routers.ha_proxy.httpx.AsyncClient")
def test_call_service(mock_client_cls, client):
    mock_instance = AsyncMock()
    mock_instance.request = AsyncMock(return_value=_mock_response(200, []))
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_instance

    resp = client.post(
        "/api/ha/services/light/turn_on",
        json={"entity_id": "light.living_room"},
    )
    assert resp.status_code == 200

    # Verify the request was made to the correct HA endpoint
    call_args = mock_instance.request.call_args
    assert "services/light/turn_on" in call_args.kwargs["url"]
    assert call_args.kwargs["json"]["entity_id"] == "light.living_room"


@patch("app.routers.ha_proxy.httpx.AsyncClient")
def test_call_service_with_extra_data(mock_client_cls, client):
    mock_instance = AsyncMock()
    mock_instance.request = AsyncMock(return_value=_mock_response(200, []))
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_instance

    resp = client.post(
        "/api/ha/services/light/turn_on",
        json={
            "entity_id": "light.living_room",
            "extra": {"brightness": 128},
        },
    )
    assert resp.status_code == 200

    call_args = mock_instance.request.call_args
    payload = call_args.kwargs["json"]
    assert payload["entity_id"] == "light.living_room"
    assert payload["brightness"] == 128


@patch("app.routers.ha_proxy.httpx.AsyncClient")
def test_toggle_entity(mock_client_cls, client):
    mock_instance = AsyncMock()
    mock_instance.request = AsyncMock(return_value=_mock_response(200, []))
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_instance

    resp = client.post("/api/ha/toggle/light.living_room")
    assert resp.status_code == 200

    call_args = mock_instance.request.call_args
    assert "services/light/toggle" in call_args.kwargs["url"]


def test_toggle_invalid_entity_id(client):
    resp = client.post("/api/ha/toggle/invalid_no_dot")
    assert resp.status_code == 400
    assert "Invalid entity_id" in resp.json()["detail"]


def test_entity_id_with_special_chars_blocked(client):
    """SSRF prevention: entity_id with uppercase or special chars must be rejected."""
    resp = client.get("/api/ha/states/light.UPPER_CASE")
    assert resp.status_code == 400

    resp = client.get("/api/ha/states/light.has spaces")
    assert resp.status_code == 400


def test_service_domain_with_special_chars_blocked(client):
    """SSRF prevention: domain/service must only contain lowercase, digits, and underscores."""
    resp = client.post(
        "/api/ha/services/LIGHT/turn_on",
        json={"entity_id": "light.test"},
    )
    assert resp.status_code == 400

    resp = client.post(
        "/api/ha/services/light/turn-on",
        json={"entity_id": "light.test"},
    )
    assert resp.status_code == 400


@patch("app.routers.ha_proxy.httpx.AsyncClient")
def test_extra_does_not_override_entity_id(mock_client_cls, client):
    mock_instance = AsyncMock()
    mock_instance.request = AsyncMock(return_value=_mock_response(200, []))
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_instance

    resp = client.post(
        "/api/ha/services/light/turn_on",
        json={
            "entity_id": "light.living_room",
            "extra": {"entity_id": "light.HACKED", "brightness": 50},
        },
    )
    assert resp.status_code == 200

    call_args = mock_instance.request.call_args
    payload = call_args.kwargs["json"]
    # entity_id must NOT be overridden by extra
    assert payload["entity_id"] == "light.living_room"
    assert payload["brightness"] == 50


@patch("app.routers.ha_proxy.httpx.AsyncClient")
def test_ha_connection_error(mock_client_cls, client):
    mock_instance = AsyncMock()
    mock_instance.request = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_instance

    resp = client.get("/api/ha/states")
    assert resp.status_code == 502
    assert "Cannot connect" in resp.json()["detail"]


@patch("app.routers.ha_proxy.httpx.AsyncClient")
def test_ha_timeout(mock_client_cls, client):
    mock_instance = AsyncMock()
    mock_instance.request = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_instance

    resp = client.get("/api/ha/states")
    assert resp.status_code == 504


@patch("app.routers.ha_proxy.httpx.AsyncClient")
def test_ha_unauthorized(mock_client_cls, client):
    mock_instance = AsyncMock()
    mock_instance.request = AsyncMock(return_value=_mock_response(401))
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_instance

    resp = client.get("/api/ha/states")
    assert resp.status_code == 401
    assert "token" in resp.json()["detail"].lower()
