"""Weather data routes.

Fetches current conditions and 3-day forecast from Open-Meteo (no API key required).
Geocoding (ZIP → lat/lon) uses Nominatim (OpenStreetMap).
Responses are cached in-process for 30 minutes to respect rate limits.
"""

import datetime
import logging
import time
from typing import Any, Dict, List, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/weather", tags=["weather"])

# In-process cache: cache_key → {"expires": float, "data": dict}
_cache: Dict[str, Any] = {}
_CACHE_TTL = 1800  # 30 minutes

# Separate cache for chart endpoint
_chart_cache: Dict[str, Any] = {}
_CHART_CACHE_TTL = 300  # 5 minutes

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


async def _fetch_pirate_weather(lat: float, lon: float) -> Dict[str, Any]:
    """Fetch minutely precipitation data from Pirate Weather (caller must validate key)."""
    key = settings.pirate_weather_key
    url = f"https://api.pirateweather.net/forecast/{key}/{lat},{lon}"
    params = {"exclude": "hourly,daily,alerts,flags", "units": "us"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=502, detail="Cannot connect to Pirate Weather service"
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Pirate Weather service timed out") from exc

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Pirate Weather service returned an error")
    return resp.json()  # type: ignore[no-any-return]


async def _fetch_open_meteo_chart(lat: float, lon: float, unit: str) -> Dict[str, Any]:
    """Fetch hourly temperature + daily sunrise/sunset from Open-Meteo."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m",
        "daily": "sunrise,sunset",
        "temperature_unit": unit,
        "forecast_days": 1,
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


def _build_chart_response(
    pirate_raw: Dict[str, Any], meteo_raw: Dict[str, Any], unit: str
) -> Dict[str, Any]:
    """Decide rain vs. temp mode and build the chart response payload."""
    minutely = pirate_raw.get("minutely", {})
    minute_data = minutely.get("data", [])[:60]
    has_rain = any(m.get("precipProbability", 0) > 0.10 for m in minute_data)

    if has_rain:
        bars = [
            {"min": i, "prob": round(minute_data[i].get("precipProbability", 0), 4)}
            for i in range(len(minute_data))
        ]
        return {"mode": "rain", "bars": bars}

    # Temp mode — pick the next 6 hours starting from now
    unit_symbol = "\u00b0F" if unit == "fahrenheit" else "\u00b0C"
    hourly_times: List[str] = meteo_raw["hourly"]["time"]
    hourly_temps: List[float] = meteo_raw["hourly"]["temperature_2m"]
    daily = meteo_raw["daily"]

    utc_offset: int = meteo_raw.get("utc_offset_seconds", 0)
    now_local = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=utc_offset)
    )
    now_str = now_local.strftime("%Y-%m-%dT%H:00")

    # Default to last 6 available hours if all entries are in the past
    start_idx = max(0, len(hourly_times) - 6)
    for i, t in enumerate(hourly_times):
        if t >= now_str:
            start_idx = i
            break

    points = [
        {"iso": hourly_times[j], "temp": round(hourly_temps[j])}
        for j in range(start_idx, min(start_idx + 6, len(hourly_times)))
    ]

    sunrise_list: List[str] = daily.get("sunrise") or []
    sunset_list: List[str] = daily.get("sunset") or []

    return {
        "mode": "temp",
        "points": points,
        "unit": unit_symbol,
        "sunrise_iso": sunrise_list[0] if sunrise_list else None,
        "sunset_iso": sunset_list[0] if sunset_list else None,
    }


@router.get("/chart")
async def get_chart(
    zip_code: str = Query(..., description="ZIP / postal code"),
    country_code: str = Query(default="US", description="ISO 3166-1 alpha-2 country code"),
    unit: str = Query(
        default="fahrenheit", description="Temperature unit: 'fahrenheit' or 'celsius'"
    ),
) -> Dict[str, Any]:
    """Return rain or temperature chart data for a ZIP code.

    Chooses rain mode when any of the next 60 minutes has >10% precipitation
    probability (requires PIRATE_WEATHER_KEY); otherwise returns a 6-hour
    temperature line-chart from Open-Meteo.  Responses are cached for 5 minutes.
    """
    if unit not in ("fahrenheit", "celsius"):
        raise HTTPException(status_code=400, detail="unit must be 'fahrenheit' or 'celsius'")

    if not settings.pirate_weather_key:
        raise HTTPException(
            status_code=503,
            detail="Pirate Weather API key not configured. Set PIRATE_WEATHER_KEY in .env",
        )

    cache_key = f"chart:{zip_code.strip()}:{country_code.upper()}:{unit}"
    now = time.time()
    if cache_key in _chart_cache and _chart_cache[cache_key]["expires"] > now:
        logger.debug("Chart cache hit for %s", cache_key)
        return _chart_cache[cache_key]["data"]

    logger.info("Fetching chart for zip=%s country=%s unit=%s", zip_code, country_code, unit)
    lat, lon = await _geocode(zip_code.strip(), country_code.strip())
    pirate_raw = await _fetch_pirate_weather(lat, lon)
    meteo_raw = await _fetch_open_meteo_chart(lat, lon, unit)
    data = _build_chart_response(pirate_raw, meteo_raw, unit)

    _chart_cache[cache_key] = {"expires": now + _CHART_CACHE_TTL, "data": data}
    return data


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
