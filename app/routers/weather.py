"""Weather data routes.

Fetches current conditions and 3-day forecast from Open-Meteo (no API key required).
Geocoding (ZIP → lat/lon) uses Nominatim (OpenStreetMap).
Responses are cached in-process for 30 minutes to respect rate limits.
"""

import logging
import time
from typing import Any, Dict, List, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/weather", tags=["weather"])

# In-process cache: cache_key → {"expires": float, "data": dict}
_cache: Dict[str, Any] = {}
_CACHE_TTL = 1800  # 30 minutes

# WMO weather interpretation code → (description, MDI icon name)
# https://open-meteo.com/en/docs#weathervariables
_WMO_ICONS: Dict[int, Tuple[str, str]] = {
    0:  ("Clear sky",               "mdi-weather-sunny"),
    1:  ("Mainly clear",            "mdi-weather-sunny"),
    2:  ("Partly cloudy",           "mdi-weather-partly-cloudy"),
    3:  ("Overcast",                "mdi-weather-cloudy"),
    45: ("Foggy",                   "mdi-weather-fog"),
    48: ("Icy fog",                 "mdi-weather-fog"),
    51: ("Light drizzle",           "mdi-weather-drizzle"),
    53: ("Drizzle",                 "mdi-weather-drizzle"),
    55: ("Heavy drizzle",           "mdi-weather-drizzle"),
    56: ("Freezing drizzle",        "mdi-weather-drizzle"),
    57: ("Heavy freezing drizzle",  "mdi-weather-drizzle"),
    61: ("Slight rain",             "mdi-weather-rainy"),
    63: ("Rain",                    "mdi-weather-rainy"),
    65: ("Heavy rain",              "mdi-weather-pouring"),
    66: ("Freezing rain",           "mdi-weather-snowy-rainy"),
    67: ("Heavy freezing rain",     "mdi-weather-snowy-rainy"),
    71: ("Slight snow",             "mdi-weather-snowy"),
    73: ("Snow",                    "mdi-weather-snowy"),
    75: ("Heavy snow",              "mdi-weather-snowy-heavy"),
    77: ("Snow grains",             "mdi-weather-snowy"),
    80: ("Slight showers",          "mdi-weather-partly-rainy"),
    81: ("Rain showers",            "mdi-weather-partly-rainy"),
    82: ("Violent showers",         "mdi-weather-pouring"),
    85: ("Snow showers",            "mdi-weather-snowy"),
    86: ("Heavy snow showers",      "mdi-weather-snowy-heavy"),
    95: ("Thunderstorm",            "mdi-weather-lightning"),
    96: ("Thunderstorm w/ hail",    "mdi-weather-lightning-rainy"),
    99: ("Thunderstorm w/ hail",    "mdi-weather-lightning-rainy"),
}


def _wmo_info(code: int) -> Tuple[str, str]:
    """Return (description, MDI icon) for a WMO weather code."""
    return _WMO_ICONS.get(code, ("Unknown", "mdi-weather-cloudy"))


async def _geocode(zip_code: str, country_code: str) -> Tuple[float, float]:
    """Convert a ZIP / postal code to (latitude, longitude) via Nominatim."""
    params = {
        "postalcode": zip_code,
        "country": country_code,
        "format": "json",
        "limit": 1,
    }
    headers = {"User-Agent": "home-dashboard/1.0 (self-hosted)"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params=params,
                headers=headers,
            )
    except httpx.ConnectError as exc:
        raise HTTPException(status_code=502, detail="Cannot connect to geocoding service") from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Geocoding service timed out") from exc

    if resp.status_code != 200 or not resp.json():
        raise HTTPException(
            status_code=404,
            detail=f"Could not locate ZIP code '{zip_code}' in country '{country_code}'",
        )
    result = resp.json()[0]
    return float(result["lat"]), float(result["lon"])


async def _fetch_weather(lat: float, lon: float, unit: str) -> Dict[str, Any]:
    """Fetch current conditions and 4-day forecast from Open-Meteo."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "temperature_unit": unit,
        "forecast_days": 4,
        "timezone": "auto",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
    except httpx.ConnectError as exc:
        raise HTTPException(status_code=502, detail="Cannot connect to weather service") from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Weather service timed out") from exc

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Weather service returned an error")
    return resp.json()  # type: ignore[no-any-return]


def _build_response(raw: Dict[str, Any], unit: str) -> Dict[str, Any]:
    """Transform Open-Meteo payload into the dashboard weather response shape."""
    current = raw["current"]
    daily = raw["daily"]

    cur_code = int(current["weather_code"])
    cur_desc, cur_icon = _wmo_info(cur_code)
    unit_symbol = "\u00b0F" if unit == "fahrenheit" else "\u00b0C"

    forecast: List[Dict[str, Any]] = []
    for i in range(1, 4):  # indices 1, 2, 3 → tomorrow + next 2 days
        code = int(daily["weather_code"][i])
        desc, icon = _wmo_info(code)
        forecast.append(
            {
                "date": daily["time"][i],
                "icon": icon,
                "desc": desc,
                "high": round(daily["temperature_2m_max"][i]),
                "low": round(daily["temperature_2m_min"][i]),
            }
        )

    return {
        "current": {
            "temp": round(current["temperature_2m"]),
            "high": round(daily["temperature_2m_max"][0]),
            "low": round(daily["temperature_2m_min"][0]),
            "icon": cur_icon,
            "desc": cur_desc,
            "unit": unit_symbol,
        },
        "forecast": forecast,
    }


@router.get("")
async def get_weather(
    zip_code: str = Query(..., description="ZIP / postal code"),
    country_code: str = Query(default="US", description="ISO 3166-1 alpha-2 country code"),
    unit: str = Query(
        default="fahrenheit", description="Temperature unit: 'fahrenheit' or 'celsius'"
    ),
) -> Dict[str, Any]:
    """Return current conditions and 3-day forecast for a ZIP code.

    Responses are cached server-side for 30 minutes.
    """
    if unit not in ("fahrenheit", "celsius"):
        raise HTTPException(
            status_code=400, detail="unit must be 'fahrenheit' or 'celsius'"
        )

    cache_key = f"{zip_code.strip()}:{country_code.upper()}:{unit}"
    now = time.time()
    if cache_key in _cache and _cache[cache_key]["expires"] > now:
        logger.debug("Weather cache hit for %s", cache_key)
        return _cache[cache_key]["data"]

    logger.info("Fetching weather for zip=%s country=%s unit=%s", zip_code, country_code, unit)
    lat, lon = await _geocode(zip_code.strip(), country_code.strip())
    raw = await _fetch_weather(lat, lon, unit)
    data = _build_response(raw, unit)

    _cache[cache_key] = {"expires": now + _CACHE_TTL, "data": data}
    return data
