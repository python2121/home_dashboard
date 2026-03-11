"""Moon phase data routes.

Computes lunar phase/illumination/age locally using the synodic month cycle.
Moonrise/moonset/transit times are fetched from the US Naval Observatory API
(free, no API key).  Geocoding (ZIP -> lat/lon) reuses the weather module's
_geocode helper.  Responses are cached in-process for 1 hour.
"""

import datetime
import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Query

from app.routers.weather import _geocode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/moon", tags=["moon"])

# In-process cache: cache_key -> {"expires": float, "data": dict}
_moon_cache: Dict[str, Any] = {}
_CACHE_TTL = 3600  # 1 hour

# Known new moon reference: January 6, 2000 18:14 UTC
_NEW_MOON_REF = datetime.datetime(2000, 1, 6, 18, 14, 0, tzinfo=datetime.timezone.utc)
_SYNODIC_MONTH = 29.53058770576  # days

# Phase names and their ranges (in fraction of synodic month).
# Key phases (new, quarters, full) get a ±2% window; intermediate phases fill the rest.
_PHASE_NAMES: List[Tuple[float, str]] = [
    (0.0, "New Moon"),
    (0.02, "Waxing Crescent"),
    (0.23, "First Quarter"),
    (0.27, "Waxing Gibbous"),
    (0.48, "Full Moon"),
    (0.52, "Waning Gibbous"),
    (0.73, "Last Quarter"),
    (0.77, "Waning Crescent"),
    (0.98, "New Moon"),
    (1.0, "New Moon"),
]


def _compute_moon_phase(dt: datetime.datetime) -> Dict[str, Any]:
    """Compute moon phase, illumination, and age from the synodic month cycle.

    Returns dict with keys: phase, illumination (0-100), age (days), fraction (0-1).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    diff = (dt - _NEW_MOON_REF).total_seconds() / 86400.0
    cycles = diff / _SYNODIC_MONTH
    position = cycles % 1.0  # 0..1 position in current cycle
    age = position * _SYNODIC_MONTH

    # Illumination: 0 at new moon, 1 at full moon, using cosine approximation
    illumination = (1 - math.cos(2 * math.pi * position)) / 2

    # Determine phase name
    phase_name = "New Moon"
    for i in range(len(_PHASE_NAMES) - 1):
        if _PHASE_NAMES[i][0] <= position < _PHASE_NAMES[i + 1][0]:
            phase_name = _PHASE_NAMES[i][1]
            break

    return {
        "phase": phase_name,
        "illumination": round(illumination * 100, 1),
        "age": round(age, 2),
        "fraction": round(illumination, 4),
    }


def _relative_time(time_str: str) -> str:
    """Return a human-friendly relative description like 'in 3 hours' or '2 hours ago'.

    Expects time_str in "HH:MM" 24-hour format.  Comparison is against local time.
    """
    try:
        now = datetime.datetime.now()
        hour, minute = map(int, time_str.split(":"))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        diff_minutes = int((target - now).total_seconds() / 60)

        if abs(diff_minutes) < 2:
            return "now"

        if diff_minutes > 0:
            if diff_minutes < 60:
                return f"in {diff_minutes} min"
            hours = diff_minutes // 60
            return f"in {hours} hr" if hours == 1 else f"in {hours} hrs"
        else:
            ago = -diff_minutes
            if ago < 60:
                return f"{ago} min ago"
            hours = ago // 60
            return f"{hours} hr ago" if hours == 1 else f"{hours} hrs ago"
    except (ValueError, TypeError):
        return ""


async def _fetch_usno(
    lat: float, lon: float, date_str: str
) -> Optional[Dict[str, str]]:
    """Fetch moonrise/moonset/transit times from US Naval Observatory API.

    Returns a dict with 'Rise', 'Set', 'Upper Transit' keys mapped to 'HH:MM'
    strings, or None if the request fails (graceful degradation).
    """
    url = "https://aa.usno.navy.mil/api/rstt/oneday"
    params = {"date": date_str, "coords": f"{lat},{lon}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
    except (httpx.ConnectError, httpx.TimeoutException):
        logger.warning("USNO API unavailable — returning phase data only")
        return None

    if resp.status_code != 200:
        logger.warning("USNO API returned %s — returning phase data only", resp.status_code)
        return None

    data = resp.json()
    properties = data.get("properties", {}).get("data", {})
    moon_data = properties.get("moondata", [])

    result: Dict[str, str] = {}
    for entry in moon_data:
        phen = entry.get("phen", "")
        time_val = entry.get("time", "")
        if phen == "Rise":
            result["Rise"] = time_val
        elif phen == "Set":
            result["Set"] = time_val
        elif phen in ("Upper Transit", "U. Transit"):
            result["Upper Transit"] = time_val
    return result


@router.get("")
async def get_moon(
    zip_code: str = Query(..., description="ZIP / postal code"),
    country_code: str = Query(default="US", description="ISO 3166-1 alpha-2 country code"),
) -> Dict[str, Any]:
    """Return moon phase, illumination, age, and rise/set/transit times for a ZIP code.

    Phase data is computed locally (no external API).  Rise/set/transit times
    come from the US Naval Observatory API (graceful degradation if unavailable).
    Responses are cached server-side for 1 hour.
    """
    cache_key = f"moon:{zip_code.strip()}:{country_code.upper()}"
    now = time.time()
    if cache_key in _moon_cache and _moon_cache[cache_key]["expires"] > now:
        logger.debug("Moon cache hit for %s", cache_key)
        return _moon_cache[cache_key]["data"]

    logger.info("Fetching moon data for zip=%s country=%s", zip_code, country_code)
    lat, lon = await _geocode(zip_code.strip(), country_code.strip())

    today = datetime.date.today()
    date_str = today.strftime("%Y-%m-%d")

    moon = _compute_moon_phase(datetime.datetime.now(datetime.timezone.utc))
    usno = await _fetch_usno(lat, lon, date_str)

    moonrise = (usno or {}).get("Rise", "")
    moonset = (usno or {}).get("Set", "")
    transit = (usno or {}).get("Upper Transit", "")

    data: Dict[str, Any] = {
        "phase": moon["phase"],
        "illumination": moon["illumination"],
        "age": moon["age"],
        "moonrise": moonrise,
        "moonrise_relative": _relative_time(moonrise) if moonrise else "",
        "moonset": moonset,
        "moonset_relative": _relative_time(moonset) if moonset else "",
        "moon_transit": transit,
        "moon_transit_relative": _relative_time(transit) if transit else "",
        "fraction": moon["fraction"],
    }

    _moon_cache[cache_key] = {"expires": now + _CACHE_TTL, "data": data}
    return data
