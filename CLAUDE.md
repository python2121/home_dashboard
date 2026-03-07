# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A self-hosted web-based home dashboard designed to display on an Android tablet or iPad browser. It connects to a local Home Assistant instance via its REST API and provides large, touch-friendly controls for lights, fans, switches, and scenes.

The UI consists of resizable, repositionable tiles with rounded corners that snap to a 12-column grid. An "edit mode" allows layout customization (drag, resize, add, remove tiles); outside of edit mode the layout is locked. Tile contents (icons, labels) scale with tile size using CSS container queries.

## Tech Stack

- **Backend**: Python (3.9+) with [FastAPI](https://fastapi.tiangolo.com/) — proxies Home Assistant API calls so credentials never reach the browser
- **Templating**: Jinja2 (served by FastAPI) for the initial HTML shell
- **Frontend**: Vanilla JS + CSS — tile drag/resize uses [GridStack.js](https://gridstackjs.com/) v10
- **Icons**: [Material Design Icons](https://materialdesignicons.com/) (font CDN)
- **Dependency management**: [Poetry](https://python-poetry.org/) (package-mode = false)
- **Containerization**: Docker + Docker Compose (runtime image uses Python 3.11)
- **CI/CD**: GitHub Actions — lint + test on push/PR, Docker build + push to GHCR on merge to main
- **Linting**: ruff (target py39)
- **Testing**: pytest + pytest-asyncio

## Tile Types

There are four tile types, stored as a discriminated union (`tile_type` field):

### EntityTile (`tile_type: "entity"`)
Controls a single Home Assistant entity (light, switch, fan, cover, lock, climate, media_player). Tapping toggles on/off. Lights show a brightness slider when on. Can display an optional badge from a related sensor (e.g., filter life percentage).

### WeatherTile (`tile_type: "weather"`)
Displays current weather conditions + 5-day forecast for a ZIP code. Uses Open-Meteo (no API key) for forecast and Nominatim for geocoding. Data refreshes every 30 minutes. Responsive via container queries — hides forecast/description on small tiles.

### SceneTile (`tile_type: "scene"`)
Controls a group of lights, each at its own brightness level. Tapping activates all member lights at their saved brightness, or turns them all off. Shows average brightness as a badge. Scene is considered "on" when all member lights are on AND within ±15 brightness of their targets. Activating one scene automatically marks overlapping scenes as off.

### ForecastChartTile (`tile_type: "forecast_chart"`)
Displays an SVG chart — either rain probability bars (next 60 minutes from Pirate Weather) or a temperature curve (next 12 hours from Open-Meteo). Mode is auto-selected: rain if any minute has >10% precipitation probability, otherwise temperature. Always enforced to h=1 (single grid row). Refreshes every 5 minutes.

## Home Assistant Integration

Home Assistant exposes a REST API at `http://<HA_HOST>:8123/api/`. All requests require:

```
Authorization: Bearer <LONG_LIVED_ACCESS_TOKEN>
Content-Type: application/json
```

The FastAPI backend acts as a thin proxy: the browser calls `/api/ha/...` routes, the server attaches the Bearer token, forwards to Home Assistant, and returns the result. This keeps the token server-side only.

All path parameters (entity_id, domain, service) are validated with strict regex patterns to prevent SSRF/path traversal:
- entity_id: `^[a-z_]+\.[a-z0-9_]+$`
- domain/service: `^[a-z_]+$`

## Credentials & Configuration

All secrets live in a `.env` file at the project root (never committed). Copy `.env.example` to `.env` and fill in values.

```
HA_BASE_URL=http://192.168.x.x:8123
HA_TOKEN=<long-lived access token>
PIRATE_WEATHER_KEY=<optional, for rain chart mode>
DEBUG=false
```

Settings class (`app/config.py`):
- `ha_base_url` — Home Assistant server address (default: `http://localhost:8123`)
- `ha_token` — Long-lived access token (required)
- `pirate_weather_key` — API key for Pirate Weather rain data (optional)
- `debug` — Enables `/docs` Swagger UI (default: false)
- `layout_file` — Path to layout JSON (default: `data/layout.json`)

The application loads config via Pydantic `BaseSettings`. No credentials are hardcoded anywhere.

## Project Structure

```
home_dashboard/
├── app/
│   ├── main.py            # FastAPI app entrypoint
│   ├── config.py          # Pydantic BaseSettings loaded from .env
│   ├── models.py          # Pydantic models (discriminated union of tile types)
│   ├── routers/
│   │   ├── ha_proxy.py    # /api/ha/* proxy routes to Home Assistant
│   │   ├── layout.py      # /api/layout — tile layout persistence (atomic writes)
│   │   └── weather.py     # /api/weather — Open-Meteo forecast + Pirate Weather rain + caching
│   ├── static/
│   │   ├── css/style.css  # Dark/light/e-ink themes, container queries, 959 lines
│   │   └── js/
│   │       ├── app.js     # Main module: GridStack grid, edit mode, state polling, entity tiles
│   │       ├── scene.js   # SceneTiles module: scene builder UI, state tracking, overlapping scene logic
│   │       ├── weather.js # WeatherTiles module: rendering, 30-min refresh timer
│   │       └── chart.js   # ForecastChartTiles module: SVG rain bars / temp curve, 5-min refresh
│   └── templates/
│       └── index.html     # Jinja2 shell — loads GridStack + MDI from CDN, multi-tab add-tile modal
├── tests/
│   ├── conftest.py        # Fixtures: isolated settings, weather cache clearing, mock HA states
│   ├── test_main.py       # Homepage route test
│   ├── test_ha_proxy.py   # HA proxy tests (11 tests, including SSRF prevention)
│   ├── test_layout.py     # Layout persistence tests (5 tests, including corruption recovery)
│   ├── test_weather.py    # Weather API tests (caching, units)
│   ├── test_config.py     # Configuration tests
│   └── test_forecast_chart.py  # Chart endpoint tests (rain/temp mode selection)
├── data/                  # Layout JSON stored here (gitignored, Docker volume)
├── .env.example           # Committed credential template
├── Dockerfile             # Multi-stage: builder (Poetry) → slim runtime, non-root user
├── docker-compose.yml     # GHCR image, volume for data/, healthcheck
├── pyproject.toml         # Poetry deps: fastapi, uvicorn, httpx, jinja2, pydantic-settings
└── poetry.lock
```

## API Endpoints

### Home Page
- `GET /` — Returns `index.html` (Jinja2 template)

### Home Assistant Proxy (`/api/ha/...`)
- `GET /api/ha/states` — Fetch all entity states from HA
- `GET /api/ha/states/{entity_id}` — Fetch single entity state (validates entity_id regex)
- `POST /api/ha/toggle/{entity_id}` — Toggle entity on/off (derives domain from entity_id prefix)
- `POST /api/ha/services/{domain}/{service}` — Call any HA service with `{"entity_id": "...", "extra": {...}}` body. The `extra` dict cannot override `entity_id` (security).
- `POST /api/ha/scene-toggle` — Toggle a scene: body `{"members": [{entity_id, brightness}, ...], "action": "on"|"off"}`. "On" fans out concurrent `light/turn_on` calls per member; "off" sends a single call with all entity IDs.

**Error codes**: 400 (validation), 401 (HA token rejected), 502 (HA unreachable), 504 (timeout, 10s limit)

### Layout Persistence (`/api/layout`)
- `GET /api/layout` — Fetch layout (returns empty default if file missing or corrupt)
- `PUT /api/layout` — Save layout (validates unique tile IDs, atomic write via temp file + os.replace)

### Weather Data (`/api/weather/...`)
- `GET /api/weather?zip_code=...&country_code=US&unit=fahrenheit` — Current conditions + 5-day forecast. Geocoding via Nominatim, forecast via Open-Meteo. 30-minute cache.
- `GET /api/weather/chart?zip_code=...&country_code=US&unit=fahrenheit` — Returns rain bars or temp curve. Rain mode uses Pirate Weather (requires `PIRATE_WEATHER_KEY`); temp mode uses Open-Meteo. 5-minute cache.

## Data Models (`app/models.py`)

- **EntityTile** — `id, entity_id, label, icon, domain, badge_entity (optional), x, y, w, h`
- **WeatherTile** — `id, label, zip_code, country_code, unit, x, y, w, h`
- **SceneTile** — `id, label, icon, members: List[SceneMember{entity_id, brightness}], x, y, w, h`. Has backward-compat migration from old `entity_ids + brightness` format.
- **ForecastChartTile** — `id, label, zip_code, country_code, unit, x, y, w, h`
- **Layout** — `columns (default 12), tiles: List[AnyTile]` (discriminated union). Validator injects `tile_type="entity"` for old layouts missing the field.
- **ServiceCall** — `entity_id, extra: Optional[Dict]` (extra cannot override entity_id)
- **SceneToggle** — `members: List[SceneMember], action: "on"|"off"`

## Frontend Architecture

### Grid & Layout
- GridStack.js v10 manages the 12-column grid (100px cell height, 6px margin)
- Layout serialized as JSON and persisted to backend via `PUT /api/layout`
- Edit mode toggle: floating action button (bottom-right) opens toolbar with Add Tile button and Done button
- In edit mode: `grid.setStatic(false)`, dashed tile outlines, edit/remove buttons visible
- In normal mode: `grid.setStatic(true)`, clean tile appearance, no edit controls

### State Management
- Entity states polled every 5 seconds via `GET /api/ha/states`
- Optimistic UI on toggle: tile updates immediately, rolls back on failure
- `pendingToggles` set prevents duplicate requests while one is in-flight
- Scene states tracked explicitly in `_sceneStates` map with overlap detection

### Tile Rendering
- Entity tiles: icon + label + optional badge + brightness slider (lights only, visible when on)
- Icons and labels scale with tile size via CSS container queries (`cqi`/`cqb` units)
- Tile state classes: `tile--on` (blue background, yellow icon) / `tile--off` (dark background, gray icon)
- Brightness slider: debounced 150ms, disabled in edit mode, hidden when light is off

### Themes
Three themes stored in localStorage (`dashboard-theme`), selectable in edit mode toolbar:
- **Dark** (default): dark blue background, blue on-state, yellow icons
- **Light**: light gray background, light blue on-state
- **E-Ink**: black on white, no shadows/transitions/hover effects, 1px icon borders

Theme changes re-render all ForecastChartTiles (SVG colors read from CSS variables).

### Add Tile Modal
Multi-tab modal with four tabs: Entity, Scene, Weather, Chart. Each tab has its own form fields. The modal supports both "add new" and "edit existing" modes.

### Scene Builder
Two-step UI in the Scene tab:
1. Pick label, icon, and lights (multi-select list from HA entities)
2. Per-light brightness sliders with live HA preview (debounced 150ms, sends actual `light/turn_on` calls)

### Icon Picker
80+ Material Design Icons organized in a scrollable grid. Includes lights, lamps, switches, fans, home, doors, and furniture icons.

### JS Module Load Order
`scene.js` → `weather.js` → `chart.js` → `app.js` (app.js depends on all other modules being defined)

## CSS Architecture (`app/static/css/style.css`)

- CSS custom properties (variables) define all colors per theme via `:root[data-theme]`
- Container queries (`container-type: size`) enable tile-level responsive scaling
- Weather tiles hide forecast below 210px height / 130px width
- Chart tiles: SVG with `viewBox="0 0 200 40"`, `preserveAspectRatio="none"` for flexible stretch
- Tile icons: `font-size: max(1rem, min(30cqi, 42cqb))` — dual-axis scaling
- Modal: centered, 90% width, max 420px, 16px rounded corners

## Security

- **Token protection**: HA token stays server-side; browser only calls `/api/ha/*` proxy routes
- **SSRF prevention**: Strict regex on entity_id, domain, service path params
- **Injection prevention**: `extra` dict in ServiceCall cannot override `entity_id`
- **XSS prevention**: All user text HTML-escaped via `escapeHTML()` (textContent trick) before DOM insertion; icon names sanitized with regex
- **No built-in dashboard auth**: Assumes trusted LAN. Add reverse proxy auth (Nginx, Authelia) if exposing to internet.

## After Making Code Changes

Always run the test suite and linter before considering a task complete:

```bash
poetry run pytest -v
poetry run ruff check .
```

Both must pass with no errors before the work is done.

## Commands

```bash
# Install dependencies
poetry install --no-root

# Run dev server (hot reload)
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
poetry run pytest

# Run a single test file
poetry run pytest tests/test_ha_proxy.py

# Lint
poetry run ruff check .

# Format
poetry run ruff format .

# Build Docker image
docker build -t home-dashboard .

# Run via Docker Compose
docker compose up -d

# View logs
docker compose logs -f
```

## Docker & Deployment

- **Dockerfile**: Multi-stage build — builder stage installs Poetry 1.8.5 and dependencies into a venv; runtime stage copies only the venv and `app/` directory. Runs as non-root `appuser` (UID 1000).
- **docker-compose.yml**: Uses `ghcr.io/python2121/home_dashboard:latest` image, loads `.env` via `env_file`, persists layout in `dashboard-data` volume, healthcheck every 30s.
- **Healthcheck**: `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')"` (30s interval, 5s timeout, 3 retries)
- **Layout persistence**: Local dev uses `data/layout.json` (gitignored); Docker uses named volume at `/app/data`. Both use atomic writes (temp file + `os.replace`).

## CI/CD

GitHub Actions pipeline:
1. Runs linting (`ruff`) and tests (`pytest`) on every push/PR
2. Builds the Docker image and pushes to GitHub Container Registry (GHCR) on merges to `main`
3. Uses a self-hosted runner for deployment

## Python Compatibility Note

Dev machine runs Python 3.9.6; Docker image uses Python 3.11. Pydantic models must use `typing.Optional`/`typing.Dict` etc. (not `X | Y` syntax) for 3.9 compatibility.

## Caching

- **Weather data**: 30-minute in-memory cache keyed by `(zip_code, country_code, unit)`
- **Chart data**: 5-minute in-memory cache keyed by `(zip_code, country_code, unit)`
- Both caches are cleared between tests via a conftest fixture

## Backward Compatibility

- **Layout tile_type backfill**: Old layouts saved before tile types were introduced lack the `tile_type` field. `Layout.model_validator(mode="before")` injects `tile_type="entity"` during load.
- **Scene member migration**: Older scene format had `entity_ids` array + single `brightness` value. `SceneTile` validator auto-migrates to new `members: List[SceneMember]` format.

## Next Steps — New Tile Ideas & Implementation Plans

The following are common features found in popular home dashboards (HADashboard, Dakboard, Home Assistant Lovelace, Hubitat, SmartThings, WallPanel, TileBoard, Fully Kiosk). Each is designed as a new tile type that follows the existing discriminated-union pattern, scales via container queries, and plugs into the existing add-tile modal as a new tab.

---

### 1. Clock / Date Tile (`tile_type: "clock"`)

**What it does**: Displays current time, date, and optionally day-of-week. Universal on wall-mounted dashboards. Pure frontend — no backend needed.

**Scaling behavior**:
- 1×1: Time only (e.g., "2:45")
- 2×1: Time + AM/PM
- 2×2: Large time + full date ("Friday, March 6")
- 4×2: Giant clock with seconds + date + day-of-week

**Implementation plan**:

1. **Model** (`app/models.py`):
   - Add `ClockTile` with fields: `id, label, tile_type="clock", format_24h: bool (default False), show_seconds: bool (default False), timezone: Optional[str] (default None = browser local), x, y, w, h`
   - Add to `AnyTile` union

2. **Frontend** (`app/static/js/clock.js` — new file):
   - `ClockTiles` IIFE module
   - `buildTileHTML(tile)` — container div with `data-format24h`, `data-show-seconds`, `data-timezone`
   - `startClock()` — single `setInterval(1000)` updates ALL clock tiles every second
   - `renderTime(el)` — reads dataset, formats via `Intl.DateTimeFormat`, updates `.clock-time` and `.clock-date` spans
   - `addClockTileToGrid(tile, grid)` — creates DOM, adds to grid, starts clock if first tile

3. **CSS** (`app/static/css/style.css`):
   - `.clock-tile` with `container-type: size`
   - `.clock-time` — `font-size: max(1.5rem, min(45cqi, 60cqb))`, `font-weight: 700`, `font-variant-numeric: tabular-nums` (prevents jitter)
   - `.clock-date` — `font-size: max(0.5rem, min(12cqi, 16cqb))`, `color: var(--text-dim)`
   - `@container clock (max-height: 80px)` — hide date, show time only
   - `@container clock (max-width: 100px)` — hide seconds and AM/PM

4. **Modal** (`app/templates/index.html`):
   - Add "Clock" tab to add-tile modal
   - Fields: label, 12h/24h toggle, show seconds checkbox, timezone dropdown (optional)

5. **Script load order**: `scene.js` → `weather.js` → `chart.js` → `clock.js` → `app.js`

6. **Tests** (`tests/test_models.py` or extend existing):
   - Validate ClockTile serialization, timezone field optional, default values

---

### 2. Camera Feed Tile (`tile_type: "camera"`)

**What it does**: Shows a live or periodically-refreshed snapshot from a Home Assistant camera entity (doorbell, security cam, baby monitor). Common in Ring, Nest, Frigate setups.

**Scaling behavior**:
- Any size: Image fills tile, maintains aspect ratio with `object-fit: cover`
- Small: Just the image
- Large: Image + camera name overlay + last-updated timestamp

**Implementation plan**:

1. **Model** (`app/models.py`):
   - Add `CameraTile` with fields: `id, entity_id, label, refresh_interval: int (default 10, seconds), x, y, w, h`
   - Validate entity_id starts with `camera.`

2. **Backend** (`app/routers/ha_proxy.py`):
   - Add `GET /api/ha/camera/{entity_id}` — proxies to HA's `GET /api/camera_proxy/{entity_id}` which returns JPEG binary
   - Returns image with `Content-Type: image/jpeg`
   - Same entity_id regex validation as other routes

3. **Frontend** (`app/static/js/camera.js` — new file):
   - `CameraTiles` IIFE module
   - `buildTileHTML(tile)` — `<img>` element with `loading="lazy"`, label overlay at bottom
   - `refreshTile(el)` — sets `img.src = "/api/ha/camera/{entity_id}?t=" + Date.now()` (cache-bust)
   - `startRefreshTimer()` — per-tile interval based on `data-refresh-interval` (default 10s)
   - `addCameraTileToGrid(tile, grid)` — creates DOM, starts refresh

4. **CSS**:
   - `.camera-tile` — `overflow: hidden`, `position: relative`
   - `.camera-tile img` — `width: 100%`, `height: 100%`, `object-fit: cover`
   - `.camera-label` — `position: absolute`, `bottom: 0`, `background: rgba(0,0,0,0.6)`, `padding: 4px 8px`
   - `@container camera (max-height: 80px)` — hide label overlay

5. **Modal**: Camera tab — entity dropdown filtered to `camera.*` entities, label, refresh interval slider (5–60s)

6. **Tests**:
   - Mock HA camera proxy, verify image passthrough, validate entity_id must start with `camera.`

---

### 3. Media Player Tile (`tile_type: "media_player"`)

**What it does**: Shows now-playing info (album art, track, artist) with playback controls (play/pause, next, previous) and volume slider. Works with Sonos, Chromecast, Apple TV, Spotify Connect, etc.

**Scaling behavior**:
- 2×2: Album art background + track name + play/pause button
- 3×2: Art + track + artist + prev/play/next buttons
- 4×2: Art + track + artist + full transport controls + volume slider
- 1×1: Just album art with play/pause overlay

**Implementation plan**:

1. **Model** (`app/models.py`):
   - Add `MediaPlayerTile` with fields: `id, entity_id, label, icon (default "mdi-music"), x, y, w, h`
   - Validate entity_id starts with `media_player.`

2. **Backend**: No new routes needed — existing `/api/ha/states/{entity_id}` returns `media_title`, `media_artist`, `media_album_name`, `entity_picture` in `attributes`. Existing `/api/ha/services/media_player/{service}` handles `media_play_pause`, `media_next_track`, `media_previous_track`, `volume_set`.

3. **Frontend** (`app/static/js/media.js` — new file):
   - `MediaPlayerTiles` IIFE module
   - `buildTileHTML(tile)` — container with album art background (CSS `background-image`), info overlay, transport buttons
   - `updateFromState(el, state)` — called during poll cycle:
     - Sets `background-image` from `state.attributes.entity_picture` (proxied through HA)
     - Updates `.media-title`, `.media-artist` text
     - Updates play/pause icon based on `state.state` ("playing" vs "paused"/"idle")
   - `handleTransport(el, action)` — calls `/api/ha/services/media_player/{action}` with entity_id
   - `handleVolume(el, value)` — debounced call to `media_player/volume_set` with `extra: {volume_level: 0.0-1.0}`
   - Register with `app.js` so `refreshTileStates()` calls `updateFromState`

4. **CSS**:
   - `.media-tile` — `container-type: size`, `position: relative`, `overflow: hidden`
   - `.media-art` — `position: absolute`, `inset: 0`, `background-size: cover`, `filter: blur(0)` at large, `blur(8px)` at small + darker overlay
   - `.media-info` — `position: relative`, `z-index: 1`, `text-shadow: 0 1px 4px rgba(0,0,0,0.8)`
   - `.media-controls` — flex row of transport buttons, `font-size: max(0.8rem, min(16cqi, 20cqb))`
   - `.media-volume` — styled like brightness slider
   - `@container media (max-width: 130px)` — hide artist, prev/next buttons, volume
   - `@container media (max-height: 100px)` — hide artist, show only title + play/pause

5. **Album art proxy**: HA's `entity_picture` is a relative URL like `/api/media_player_proxy/...`. The frontend image src should go through the existing proxy: `/api/ha/camera/{path}` or add a generic image proxy route.

6. **Tests**: Mock HA state with media attributes, verify service calls for transport controls

---

### 4. Climate / Thermostat Tile (`tile_type: "climate"`)

**What it does**: Displays current temperature, target setpoint, and HVAC mode (heat/cool/auto/off) with interactive controls. Works with Nest, Ecobee, Z-Wave thermostats, etc.

**Scaling behavior**:
- 2×2: Current temp (large) + target temp + mode icon
- 3×2: Current temp + target temp with +/- buttons + mode selector (heat/cool/auto/off)
- 4×3: Full display with humidity, current temp, setpoint controls, mode buttons, fan mode
- 1×1: Current temp only with color indicating mode (orange=heat, blue=cool)

**Implementation plan**:

1. **Model** (`app/models.py`):
   - Add `ClimateTile` with fields: `id, entity_id, label, icon (default "mdi-thermostat"), show_humidity: bool (default True), x, y, w, h`
   - Validate entity_id starts with `climate.`

2. **Backend**: No new routes — existing proxy handles:
   - `GET /api/ha/states/{entity_id}` returns `current_temperature`, `temperature` (setpoint), `hvac_mode`, `hvac_modes`, `current_humidity`, `fan_mode`, `fan_modes` in attributes
   - `POST /api/ha/services/climate/set_temperature` with `extra: {temperature: N}`
   - `POST /api/ha/services/climate/set_hvac_mode` with `extra: {hvac_mode: "heat"|"cool"|"auto"|"off"}`

3. **Frontend** (`app/static/js/climate.js` — new file):
   - `ClimateTiles` IIFE module
   - `buildTileHTML(tile)` — current temp display, target temp with +/- buttons, mode icons row
   - `updateFromState(el, state)` — updates current temp, target, mode indicator, humidity
   - `setTemp(el, delta)` — increments/decrements target by 0.5 or 1 degree, calls `climate/set_temperature` (debounced 500ms to allow rapid +/+ clicks)
   - `setMode(el, mode)` — calls `climate/set_hvac_mode`
   - Color coding: tile background tint shifts — `--climate-heat: #3d1f00` (warm), `--climate-cool: #0e2440` (cool), neutral for off/auto
   - Register with `app.js` poll cycle

4. **CSS**:
   - `.climate-tile` — `container-type: size`
   - `.climate-current` — `font-size: max(1.5rem, min(35cqi, 50cqb))`, `font-weight: 700`
   - `.climate-target` — smaller, with `+`/`-` buttons flanking
   - `.climate-modes` — flex row of mode icons (`mdi-fire`, `mdi-snowflake`, `mdi-autorenew`, `mdi-power`), active mode highlighted
   - `.climate-humidity` — small badge "💧 45%" at corner
   - `@container climate (max-width: 130px)` — hide mode buttons and humidity, show only current + target
   - `@container climate (max-height: 100px)` — hide target controls, show current temp only

5. **Modal**: Climate tab — entity dropdown filtered to `climate.*`, label, show humidity toggle

6. **Tests**: Mock thermostat state, verify setpoint calls, mode changes

---

### 5. Calendar / Agenda Tile (`tile_type: "calendar"`)

**What it does**: Shows upcoming events from Home Assistant's calendar integration (Google Calendar, CalDAV, local). Common on kitchen/hallway dashboards. Read-only display.

**Scaling behavior**:
- 2×2: Next 2 events (time + title)
- 3×3: Next 5 events with color-coded calendar source
- 4×4: Full day agenda view with time blocks
- 2×1: Single next event one-liner

**Implementation plan**:

1. **Model** (`app/models.py`):
   - Add `CalendarTile` with fields: `id, label, entity_id, days_ahead: int (default 3), max_events: int (default 10), x, y, w, h`
   - Validate entity_id starts with `calendar.`

2. **Backend** (`app/routers/calendar.py` — new file):
   - `GET /api/calendar?entity_id=calendar.xxx&days=3` — proxies to HA's `GET /api/calendars/{entity_id}?start=...&end=...`
   - HA returns `[{summary, start: {dateTime|date}, end: {dateTime|date}, description, location}, ...]`
   - Backend normalizes response: `[{title, start_iso, end_iso, all_day: bool}, ...]`
   - Cache: 5-minute in-memory per entity_id
   - Register router in `app/main.py`

3. **Frontend** (`app/static/js/calendar.js` — new file):
   - `CalendarTiles` IIFE module
   - `buildTileHTML(tile)` — scrollable list container
   - `renderEvents(el, events)` — groups events by date, renders date headers + event rows
   - Event row: time range (or "All day") + title, truncated with ellipsis
   - Today's events highlighted, past events dimmed
   - `refreshTile(el)` — fetches from `/api/calendar?entity_id=...&days=...`
   - `startRefreshTimer()` — refresh all calendar tiles every 5 minutes

4. **CSS**:
   - `.calendar-tile` — `container-type: size`, `overflow-y: auto` (scrollable)
   - `.calendar-date-header` — `font-size: max(0.5rem, min(8cqi, 11cqb))`, `font-weight: 600`, `color: var(--text-dim)`, `border-bottom: 1px solid`
   - `.calendar-event` — flex row, `padding: 4px 0`
   - `.calendar-time` — `min-width: 3em`, `color: var(--primary)`, `font-size: max(0.45rem, min(7cqi, 10cqb))`
   - `.calendar-title` — `white-space: nowrap`, `overflow: hidden`, `text-overflow: ellipsis`
   - `.calendar-event--past` — `opacity: 0.4`
   - `@container calendar (max-height: 100px)` — show only next 2 events, hide date headers
   - `@container calendar (max-width: 130px)` — hide time column, title only

5. **Modal**: Calendar tab — entity dropdown filtered to `calendar.*`, label, days ahead slider (1–14), max events slider (3–20)

6. **Tests** (`tests/test_calendar.py`):
   - Mock HA calendar API, verify event normalization, caching, date range calculation

---

### 6. Energy Monitor Tile (`tile_type: "energy"`)

**What it does**: Displays real-time power consumption, daily energy usage, and optionally solar production / grid import-export. Works with smart plugs, whole-home monitors (Emporia Vue, Sense), and HA energy dashboard sensors.

**Scaling behavior**:
- 1×1: Current watts (e.g., "1.2 kW")
- 2×2: Current watts + today's kWh + simple bar sparkline
- 3×2: Current watts + today's kWh + cost estimate + SVG usage chart (last 6 hours)
- 4×3: Full display with solar production, grid import/export, net consumption, 12-hour chart

**Implementation plan**:

1. **Model** (`app/models.py`):
   - Add `EnergyTile` with fields: `id, label, power_entity: str (sensor for current watts), energy_entity: Optional[str] (sensor for daily kWh), solar_entity: Optional[str] (sensor for solar production), cost_per_kwh: Optional[float], icon (default "mdi-lightning-bolt"), x, y, w, h`

2. **Backend** (`app/routers/energy.py` — new file):
   - `GET /api/energy/history?entity_id=sensor.xxx&hours=12` — proxies to HA's `GET /api/history/period/{start}?filter_entity_id={id}&minimal_response`
   - Returns simplified timeseries: `[{time_iso, value: float}, ...]` sampled to ~1 point per 10 minutes
   - Cache: 2-minute in-memory per entity_id

3. **Frontend** (`app/static/js/energy.js` — new file):
   - `EnergyTiles` IIFE module
   - `buildTileHTML(tile)` — current power display, daily usage, optional solar section, SVG chart area
   - `updateFromState(el, entityStates)` — reads current watts from `power_entity`, daily kWh from `energy_entity`, solar from `solar_entity`
   - `renderChart(canvasEl, history)` — SVG area chart (similar style to ForecastChartTile), filled below line
   - Format helpers: auto-scale W/kW, kWh with 1 decimal, cost as `$X.XX`
   - Refresh chart data every 5 minutes

4. **CSS**:
   - `.energy-tile` — `container-type: size`
   - `.energy-current` — `font-size: max(1.2rem, min(30cqi, 40cqb))`, `font-weight: 700`
   - `.energy-unit` — `font-size: 0.5em`, `color: var(--text-dim)`
   - `.energy-daily` — smaller, "Today: 12.4 kWh ($1.86)"
   - `.energy-solar` — green-tinted, `mdi-solar-power` icon
   - `.energy-chart` — SVG area, same pattern as chart.js
   - `@container energy (max-height: 100px)` — hide chart and daily, show watts only
   - `@container energy (max-width: 130px)` — hide daily and solar

5. **Modal**: Energy tab — power sensor dropdown, optional energy/solar sensor dropdowns, cost per kWh input

6. **Tests**: Mock HA history API, verify timeseries sampling, cost calculation

---

### 7. Person / Presence Tile (`tile_type: "person"`)

**What it does**: Shows whether a household member is home or away, with optional zone info (Work, School, Gym). Uses HA's `person` and `device_tracker` entities. Common on family dashboards.

**Scaling behavior**:
- 1×1: Colored dot (green=home, red=away) + initials
- 2×1: Name + home/away badge
- 2×2: Name + zone name + last-changed time + avatar/initials circle
- 3×2: Multiple people in a row (for a "Who's Home" group tile)

**Implementation plan**:

1. **Model** (`app/models.py`):
   - Add `PersonTile` with fields: `id, entity_id, label, icon (default "mdi-account"), initials: Optional[str] (default: derived from label), x, y, w, h`
   - Validate entity_id starts with `person.` or `device_tracker.`

2. **Backend**: No new routes — existing state proxy returns `state` ("home"/"not_home"/zone name) and `attributes.friendly_name`.

3. **Frontend** (`app/static/js/person.js` — new file):
   - `PersonTiles` IIFE module
   - `buildTileHTML(tile)` — avatar circle (initials or icon) + name + zone badge
   - `updateFromState(el, state)`:
     - "home" → green dot, badge "Home"
     - "not_home" → red dot, badge "Away"
     - zone name → blue dot, badge with zone name
     - Update `data-last-changed` for "since" display (e.g., "Home since 2:30 PM")
   - Register with `app.js` poll cycle (non-interactive tile, no toggle on click)

4. **CSS**:
   - `.person-tile` — `container-type: size`, `cursor: default` (not toggleable)
   - `.person-avatar` — `border-radius: 50%`, `background: var(--primary)`, `font-size: max(0.8rem, min(20cqi, 28cqb))`, centered initials
   - `.person-status` — small colored dot, absolute positioned on avatar
   - `.person-zone` — badge below name, `font-size: max(0.4rem, min(7cqi, 10cqb))`
   - `.person-since` — dim text, relative time
   - Home: `--person-home: #22c55e`, Away: `--person-away: #ef4444`
   - `@container person (max-height: 80px)` — hide zone and since, show avatar + dot only
   - `@container person (max-width: 100px)` — hide name, show avatar only

5. **Modal**: Person tab — entity dropdown filtered to `person.*`/`device_tracker.*`, label, initials override

6. **Tests**: Verify state mapping (home/not_home/zone), non-toggleable behavior

---

### 8. Sensor Gauge Tile (`tile_type: "gauge"`)

**What it does**: Displays a numeric sensor value with a circular arc gauge or linear bar. Works for temperature, humidity, CO2, PM2.5, battery level, etc. Very common in environment monitoring dashboards.

**Scaling behavior**:
- 1×1: Value only with unit (e.g., "45%")
- 2×2: Circular SVG arc gauge + value + label
- 3×2: Gauge + value + min/max range + trend arrow (up/down/stable)
- 1×2 (tall): Vertical bar gauge

**Implementation plan**:

1. **Model** (`app/models.py`):
   - Add `GaugeTile` with fields: `id, entity_id, label, icon (default "mdi-gauge"), unit: Optional[str] (auto-detect from HA), min_value: float (default 0), max_value: float (default 100), warning_above: Optional[float], critical_above: Optional[float], x, y, w, h`

2. **Backend**: No new routes — existing state proxy returns `state` (numeric value) and `attributes.unit_of_measurement`.

3. **Frontend** (`app/static/js/gauge.js` — new file):
   - `GaugeTiles` IIFE module
   - `buildTileHTML(tile)` — SVG arc gauge (270-degree arc) + value text + label
   - `renderGauge(el, value, min, max)`:
     - SVG arc using `stroke-dasharray` / `stroke-dashoffset` technique
     - Arc color: green (normal), yellow (warning), red (critical) based on thresholds
     - Smooth CSS transition on value change
   - `updateFromState(el, state)` — reads numeric value, updates gauge arc and text
   - Register with `app.js` poll cycle

4. **CSS**:
   - `.gauge-tile` — `container-type: size`
   - `.gauge-svg` — centered, `max-width: min(90%, 90cqb)` (aspect-ratio locked)
   - `.gauge-arc-bg` — `stroke: var(--surface)`, `stroke-width: 8`
   - `.gauge-arc-fill` — `stroke: var(--gauge-color)`, `stroke-linecap: round`, `transition: stroke-dashoffset 0.5s ease`
   - `.gauge-value` — centered inside arc, `font-size: max(1rem, min(25cqi, 35cqb))`, `font-weight: 700`
   - `.gauge-unit` — `font-size: 0.5em`, `color: var(--text-dim)`
   - `--gauge-normal: #22c55e`, `--gauge-warning: #eab308`, `--gauge-critical: #ef4444`
   - `@container gauge (max-height: 80px)` — hide arc, show value + unit only
   - `@container gauge (max-width: 100px)` — shrink arc, hide label

5. **Modal**: Gauge tab — entity dropdown (filtered to `sensor.*`), label, min/max inputs, warning/critical thresholds, unit override

6. **Tests**: Verify value normalization, threshold color mapping, arc calculation

---

### 9. Garbage / Recycling Collection Tile (`tile_type: "waste"`)

**What it does**: Shows next pickup dates for trash, recycling, and yard waste. Uses HA integrations (Waste Collection Schedule, custom sensors). Very popular on kitchen dashboards to answer "is it trash day?"

**Scaling behavior**:
- 1×1: Colored icon indicating which bin is next
- 2×1: "Trash: Tomorrow" one-liner
- 2×2: Next 2–3 pickup types with dates and colored icons
- 3×2: Full week view with all waste types

**Implementation plan**:

1. **Model** (`app/models.py`):
   - Add `WasteTile` with fields: `id, label, members: List[WasteMember], x, y, w, h`
   - `WasteMember`: `entity_id: str, waste_type: str ("trash"|"recycling"|"yard"|"compost"|custom), color: str (hex, e.g., "#4caf50"), icon: str (default varies by type)`
   - Default icons: trash → `mdi-trash-can`, recycling → `mdi-recycle`, yard → `mdi-leaf`, compost → `mdi-compost`

2. **Backend**: No new routes — waste sensors are standard HA sensors with `state` as a date string or days-until count.

3. **Frontend** (`app/static/js/waste.js` — new file):
   - `WasteTiles` IIFE module
   - `buildTileHTML(tile)` — list of waste entries
   - `updateFromState(el, entityStates)` — for each member:
     - Parse state as date or number (days until)
     - Format: "Today", "Tomorrow", "Wed", or "Mar 12"
     - Sort by soonest first
     - Highlight today/tomorrow entries with attention color
   - Register with `app.js` poll cycle

4. **CSS**:
   - `.waste-tile` — `container-type: size`
   - `.waste-entry` — flex row: colored icon + type label + date
   - `.waste-icon` — circle with `background: var(--waste-color)`, white icon
   - `.waste-today` — pulsing border or highlighted background
   - `.waste-tomorrow` — slightly highlighted
   - `@container waste (max-height: 80px)` — show only next pickup (soonest)
   - `@container waste (max-width: 130px)` — hide type label, show icon + date only

5. **Modal**: Waste tab — dynamic member list builder (add rows: pick entity, waste type dropdown, color picker, icon)

6. **Tests**: Verify date parsing (ISO date, days-until number), sorting, relative date formatting

---

### 10. Timer / Countdown Tile (`tile_type: "timer"`)

**What it does**: Displays an active countdown timer from Home Assistant's `timer` domain or `input_datetime` entities. Useful for cooking timers, laundry, sprinklers. Shows remaining time with a progress ring.

**Scaling behavior**:
- 1×1: MM:SS countdown
- 2×2: Circular progress ring + MM:SS + label + start/pause/cancel buttons
- 3×2: Ring + time + label + full controls + "Finished!" flash animation

**Implementation plan**:

1. **Model** (`app/models.py`):
   - Add `TimerTile` with fields: `id, entity_id, label, icon (default "mdi-timer-outline"), x, y, w, h`
   - Validate entity_id starts with `timer.`

2. **Backend**: No new routes — `timer` entities have `state` ("idle"/"active"/"paused"), `attributes.duration`, `attributes.remaining`, `attributes.finishes_at`.

3. **Frontend** (`app/static/js/timer.js` — new file):
   - `TimerTiles` IIFE module
   - `buildTileHTML(tile)` — SVG progress ring + time display + control buttons (start/pause/cancel)
   - `updateFromState(el, state)`:
     - "active": calculate remaining from `finishes_at`, start local `requestAnimationFrame` countdown for smooth seconds
     - "paused": show frozen remaining time, pause button → play icon
     - "idle": show duration, reset ring to full
   - `renderRing(el, fraction)` — SVG circle `stroke-dashoffset` based on fraction remaining
   - `handleControl(el, action)` — calls `timer/start`, `timer/pause`, `timer/cancel` via service proxy
   - Flash animation when timer reaches 0:00 (CSS `@keyframes timer-flash`)
   - 1-second `requestAnimationFrame` loop for smooth countdown (not dependent on 5s poll)

4. **CSS**:
   - `.timer-tile` — `container-type: size`
   - `.timer-ring` — SVG circle, `stroke: var(--primary)`, `transition: stroke-dashoffset 1s linear`
   - `.timer-time` — `font-size: max(1rem, min(30cqi, 40cqb))`, `font-variant-numeric: tabular-nums`
   - `.timer-controls` — flex row of icon buttons (play, pause, stop)
   - `.timer-finished` — `animation: timer-flash 0.5s ease infinite alternate` (alternates background between accent and surface)
   - `@container timer (max-height: 80px)` — hide controls, show time only
   - `@container timer (max-width: 100px)` — hide label and ring, show time only

5. **Modal**: Timer tab — entity dropdown filtered to `timer.*`, label

6. **Tests**: Verify state transitions (idle→active→paused→idle), remaining time calculation from `finishes_at`

---

### 11. Alarm Panel Tile (`tile_type: "alarm"`)

**What it does**: Arm/disarm a security alarm panel. Shows current state (armed_home, armed_away, disarmed, triggered, arming, pending). Works with Honeywell, DSC, Envisalink, Alarmo, etc.

**Scaling behavior**:
- 1×1: Shield icon with color (green=disarmed, red=armed, flashing=triggered)
- 2×2: Shield + state text + arm home / arm away buttons
- 3×3: Full keypad grid for PIN entry + mode buttons + state

**Implementation plan**:

1. **Model** (`app/models.py`):
   - Add `AlarmTile` with fields: `id, entity_id, label, icon (default "mdi-shield-home"), require_pin: bool (default True), x, y, w, h`
   - Validate entity_id starts with `alarm_control_panel.`

2. **Backend**: No new routes — uses existing service proxy:
   - `POST /api/ha/services/alarm_control_panel/alarm_arm_home` with `extra: {code: "1234"}`
   - `POST /api/ha/services/alarm_control_panel/alarm_arm_away`
   - `POST /api/ha/services/alarm_control_panel/alarm_disarm`
   - `POST /api/ha/services/alarm_control_panel/alarm_trigger`

3. **Frontend** (`app/static/js/alarm.js` — new file):
   - `AlarmTiles` IIFE module
   - `buildTileHTML(tile)` — shield icon + state badge + mode buttons + optional PIN keypad
   - `updateFromState(el, state)`:
     - `disarmed` → green shield, "Disarmed"
     - `armed_home` → yellow shield, "Armed Home"
     - `armed_away` → red shield, "Armed Away"
     - `arming` → pulsing yellow, "Arming..."
     - `triggered` → flashing red with CSS animation, "TRIGGERED"
     - `pending` → pulsing, "Pending"
   - `showKeypad(el, action)` — overlays 0-9 keypad grid on tile, collects PIN, calls service
   - `armPanel(el, mode, pin)` — calls appropriate alarm service
   - Register with `app.js` poll cycle

4. **CSS**:
   - `.alarm-tile` — `container-type: size`
   - `.alarm-shield` — large icon, color transitions
   - `.alarm-state` — `font-size: max(0.5rem, min(10cqi, 14cqb))`, uppercase, letter-spacing
   - `.alarm-actions` — flex row/col of mode buttons (Home, Away, Disarm)
   - `.alarm-keypad` — CSS grid 3×4, number buttons + clear/enter
   - `.alarm-triggered` — `animation: alarm-flash 0.3s ease infinite alternate`, `background: var(--accent)`
   - `@container alarm (max-height: 120px)` — hide keypad, show quick-arm buttons only
   - `@container alarm (max-width: 130px)` — hide action labels, show icons only

5. **Modal**: Alarm tab — entity dropdown filtered to `alarm_control_panel.*`, label, require PIN checkbox

6. **Tests**: Verify state-to-color mapping, PIN service calls, all arm modes

---

### 12. Doorbell / Notification Tile (`tile_type: "doorbell"`)

**What it does**: Shows the last doorbell ring event with timestamp, and optionally the most recent camera snapshot. Works with Ring, UniFi Protect, Amcrest, Frigate doorbells.

**Scaling behavior**:
- 1×1: Doorbell icon, pulsing if recently rung (last 2 minutes)
- 2×2: Last snapshot image + "Rang 2 min ago" overlay
- 3×2: Snapshot + timestamp + event count today

**Implementation plan**:

1. **Model** (`app/models.py`):
   - Add `DoorbellTile` with fields: `id, entity_id, label, camera_entity: Optional[str] (for snapshot), x, y, w, h`
   - Validate entity_id starts with `binary_sensor.` or `event.`

2. **Backend**: Reuses camera proxy route (from Camera Tile above) for snapshot. Doorbell state from existing state proxy — `binary_sensor.*_doorbell` has `state` "on"/"off" and `last_changed`.

3. **Frontend** (`app/static/js/doorbell.js` — new file):
   - `DoorbellTiles` IIFE module
   - `buildTileHTML(tile)` — snapshot `<img>` (if camera_entity) + doorbell icon overlay + timestamp
   - `updateFromState(el, state)`:
     - Calculate time since `last_changed`
     - If < 2 minutes: apply `.doorbell-recent` pulse animation
     - Format relative time: "Just now", "2 min ago", "1 hour ago", "Today 3:42 PM"
   - Refresh snapshot image on state change (doorbell ring)

4. **CSS**:
   - `.doorbell-tile` — `container-type: size`, `position: relative`
   - `.doorbell-snapshot` — `width: 100%`, `height: 100%`, `object-fit: cover`
   - `.doorbell-overlay` — absolute bottom bar with timestamp and icon
   - `.doorbell-recent` — `animation: doorbell-pulse 1s ease infinite`, border glow in accent color
   - `@container doorbell (max-height: 80px)` — hide snapshot, show icon + timestamp only

5. **Modal**: Doorbell tab — doorbell sensor dropdown, optional camera entity dropdown, label

---

### General Implementation Notes for All New Tiles

**Pattern to follow for every new tile**:

1. Add Pydantic model class to `app/models.py`, add to `AnyTile` union
2. Create `app/static/js/{tiletype}.js` as an IIFE exposing a global (e.g., `ClockTiles`)
3. Add `<script>` tag to `index.html` BEFORE `app.js`
4. Add CSS to `style.css` with `container-type: size` and responsive `@container` queries
5. Add tab to the add-tile modal in `index.html`
6. Wire into `app.js`: `addTileToGrid()` switch case, `refreshTileStates()` if state-driven, modal tab switching
7. Add `tile_type` to the `Layout.model_validator` backfill logic if needed
8. Write tests for any new backend routes
9. Run `poetry run pytest -v && poetry run ruff check .` before done

**Scaling philosophy**: Every tile should be usable at 1×1 (minimal info) and gracefully add detail as size increases. Use `@container` queries with `cqi`/`cqb` units for font sizing and show/hide thresholds. Never use viewport-based media queries for tile content.
