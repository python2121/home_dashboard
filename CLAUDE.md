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

### 2. Calendar / Agenda Tile (`tile_type: "calendar"`)

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

### 3. Energy Monitor Tile (`tile_type: "energy"`)

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

### 4. Garbage / Recycling Collection Tile (`tile_type: "waste"`)

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
