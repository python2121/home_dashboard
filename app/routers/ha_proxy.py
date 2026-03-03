"""Proxy routes that forward requests to the Home Assistant REST API.

The browser never sees the HA token — all auth happens server-side.
"""

import asyncio
import logging
import re
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.models import SceneToggle, ServiceCall

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ha", tags=["home-assistant"])

REQUEST_TIMEOUT = 10.0

# Strict patterns to prevent SSRF via path traversal
_ENTITY_ID_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
_SLUG_RE = re.compile(r"^[a-z0-9_]+$")


def _validate_entity_id(entity_id: str) -> None:
    """Validate entity_id matches HA format and contains no path traversal."""
    if not _ENTITY_ID_RE.match(entity_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity_id format: {entity_id!r}. Expected 'domain.name'.",
        )


def _validate_slug(value: str, label: str) -> None:
    """Validate a domain or service slug contains only safe characters."""
    if not _SLUG_RE.match(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {label}: {value!r}. Only lowercase letters and underscores allowed.",
        )


async def _ha_request(
    method: str,
    path: str,
    json_body: Optional[dict] = None,
) -> Any:
    """Send an authenticated request to Home Assistant and return the JSON response."""
    url = f"{settings.ha_base_url}/api/{path}"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=settings.ha_headers,
                json=json_body,
            )
    except httpx.ConnectError as exc:
        logger.error("Cannot connect to Home Assistant at %s", settings.ha_base_url)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cannot connect to Home Assistant",
        ) from exc
    except httpx.TimeoutException as exc:
        logger.error("Timeout connecting to Home Assistant at %s", settings.ha_base_url)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Home Assistant request timed out",
        ) from exc

    if response.status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Home Assistant rejected the access token — check HA_TOKEN in .env",
        )

    if response.status_code >= 400:
        logger.warning(
            "HA returned %s for %s %s: %s",
            response.status_code,
            method,
            path,
            response.text[:200],
        )
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Home Assistant error: {response.text[:200]}",
        )

    try:
        return response.json()
    except ValueError as exc:
        logger.error("Non-JSON response from HA for %s %s", method, path)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Home Assistant returned a non-JSON response",
        ) from exc


@router.get("/states")
async def get_all_states() -> Any:
    """Fetch every entity state from Home Assistant."""
    return await _ha_request("GET", "states")


@router.get("/states/{entity_id}")
async def get_entity_state(entity_id: str) -> Any:
    """Fetch the state of a single entity."""
    _validate_entity_id(entity_id)
    return await _ha_request("GET", f"states/{entity_id}")


@router.post("/services/{domain}/{service}")
async def call_service(domain: str, service: str, body: ServiceCall) -> Any:
    """Call a Home Assistant service (e.g. light/turn_on, fan/turn_off)."""
    _validate_slug(domain, "domain")
    _validate_slug(service, "service")
    _validate_entity_id(body.entity_id)
    payload: dict = {"entity_id": body.entity_id}
    if body.extra:
        # Prevent extra from overriding entity_id
        extra = {k: v for k, v in body.extra.items() if k != "entity_id"}
        payload.update(extra)
    return await _ha_request("POST", f"services/{domain}/{service}", json_body=payload)


@router.post("/scene-toggle")
async def scene_toggle(body: SceneToggle) -> Any:
    """Toggle a group of lights on or off.

    When turning on, each member is set to its own brightness concurrently.
    When turning off, all members are turned off in a single HA call.
    All entity_ids must belong to the 'light' domain.
    """
    for member in body.members:
        _validate_entity_id(member.entity_id)
        domain = member.entity_id.split(".", 1)[0]
        if domain != "light":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scene tiles only support 'light' entities, got: {member.entity_id!r}",
            )

    if body.action == "on":
        # Fan out — each member may have a different brightness
        results = await asyncio.gather(
            *[
                _ha_request(
                    "POST",
                    "services/light/turn_on",
                    json_body={"entity_id": member.entity_id, "brightness": member.brightness},
                )
                for member in body.members
            ]
        )
        return results
    else:
        return await _ha_request(
            "POST",
            "services/light/turn_off",
            json_body={"entity_id": [m.entity_id for m in body.members]},
        )


@router.post("/toggle/{entity_id}")
async def toggle_entity(entity_id: str) -> Any:
    """Convenience endpoint: toggle an entity using its domain's toggle service.

    Derives the domain from the entity_id prefix (e.g. "light.kitchen" → "light").
    """
    _validate_entity_id(entity_id)
    domain = entity_id.split(".", 1)[0]

    return await _ha_request(
        "POST",
        f"services/{domain}/toggle",
        json_body={"entity_id": entity_id},
    )
