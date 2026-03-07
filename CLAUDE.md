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

Every plan below follows the exact conventions visible in the codebase: Pydantic models with `Field(description=...)`, `"use strict"` IIFE modules exposing a global, `escapeHTML()` via the textContent trick, `grid-stack-item-content` inner div, `data-*` attributes for serialization, `DashboardApp.getEditingTile()` / `DashboardApp.closeAddModal()` for modal flow, and CSS custom properties for all theme colors.

---

### 1. Clock / Date Tile (`tile_type: "clock"`)

**What it does**: Displays current time, date, and optionally day-of-week. Universal on wall-mounted dashboards. Pure frontend — no backend route needed.

**Scaling behavior**:
- 1×1: Time only (e.g., "2:45")
- 2×1: Time + AM/PM
- 2×2: Large time + full date ("Friday, March 6")
- 4×2: Giant clock with seconds + date + day-of-week

**Implementation plan**:

**Step 1 — Model** (`app/models.py`):
- Add `ClockTile(BaseModel)` following the `WeatherTile` pattern (no entity_id, display-only):
  ```python
  class ClockTile(BaseModel):
      tile_type: Literal["clock"] = "clock"
      id: str = Field(description="Unique tile identifier")
      label: str = Field(default="Clock", description="Display label shown on the tile")
      format_24h: bool = Field(default=False, description="Use 24-hour format")
      show_seconds: bool = Field(default=False, description="Display seconds")
      x: int = Field(default=0, ge=0)
      y: int = Field(default=0, ge=0)
      w: int = Field(default=2, ge=1)
      h: int = Field(default=2, ge=1)
  ```
- Add `ClockTile` to the `AnyTile` union: `Union[EntityTile, WeatherTile, SceneTile, ForecastChartTile, ClockTile]`
- No new `model_validator` needed — old layouts without clock tiles are unaffected

**Step 2 — Frontend JS** (`app/static/js/clock.js` — new file):
- Create `ClockTiles` IIFE following the `WeatherTiles` pattern (weather.js):
  - `escapeHTML(str)` — same textContent trick used in every module
  - `buildTileHTML(tile)` — returns edit/remove buttons (matching `tile__edit` / `tile__remove` classes exactly) + clock container:
    ```html
    <button class="tile__edit" data-tile-id="${safeId}" title="Edit tile">
      <i class="mdi mdi-pencil"></i>
    </button>
    <button class="tile__remove" data-tile-id="${safeId}" title="Remove tile">
      <i class="mdi mdi-close"></i>
    </button>
    <div class="clock-tile">
      <div class="clock-time">--:--</div>
      <div class="clock-date"></div>
    </div>
    ```
  - `renderTime(gridItem)` — reads `dataset.format24h`, `dataset.showSeconds`, formats via `Intl.DateTimeFormat` with appropriate options, updates `.clock-time` text and `.clock-date` text (e.g., "Friday, March 6")
  - `startClock()` — single `setInterval(1000)` that calls `renderTime()` on every `[data-tile-type="clock"]` element. Only one interval regardless of tile count.
  - `addClockTileToGrid(tile, grid)` — following the exact `addWeatherTileToGrid` pattern:
    ```javascript
    function addClockTileToGrid(tile, grid) {
      const el = document.createElement("div");
      el.className = "tile--clock";
      el.dataset.tileType    = "clock";
      el.dataset.tileId      = tile.id;
      el.dataset.label       = tile.label || "Clock";
      el.dataset.format24h   = tile.format_24h ? "true" : "false";
      el.dataset.showSeconds = tile.show_seconds ? "true" : "false";

      const content = document.createElement("div");
      content.className = "grid-stack-item-content";
      content.innerHTML = buildTileHTML(tile);
      el.appendChild(content);

      grid.addWidget(el, { x: tile.x, y: tile.y, w: tile.w, h: tile.h });
      renderTime(el); // immediate render, don't wait for interval
    }
    ```
  - `populateForEdit(tileEl)` — pre-fills form fields from dataset (matching `ForecastChartTiles.populateForEdit` pattern)
  - `initModal()` — handles form submit following the `WeatherTiles.initModal()` pattern: read form values, check for `DashboardApp.getEditingTile()` to decide add vs. update, call `addClockTileToGrid` or update dataset attrs, call `DashboardApp.closeAddModal()`
  - Public API: `{ addClockTileToGrid, populateForEdit, initModal, startClock }`

**Step 3 — CSS** (`app/static/css/style.css`):
- Add theme variable `--clock-bg` to each theme block (dark: `#1b2040`, light: `#e8edf5`, eink: `#f5f5f5`) — subtle tint like `--weather-bg`
- Add clock tile styles:
  ```css
  .clock-tile {
    container-name: clock;
    container-type: size;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    background: var(--clock-bg);
    color: var(--text);
    gap: 4px;
  }
  .clock-time {
    font-size: max(1.5rem, min(45cqi, 60cqb));
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
    color: var(--text);
  }
  .clock-date {
    font-size: max(0.5rem, min(12cqi, 16cqb));
    color: var(--text-dim);
    text-align: center;
  }
  @container clock (max-height: 80px) {
    .clock-date { display: none; }
  }
  @container clock (max-width: 100px) {
    .clock-time { font-size: max(1rem, min(35cqi, 50cqb)); }
  }
  ```
- Tile container inherits existing `.grid-stack-item-content` border-radius and padding

**Step 4 — Modal HTML** (`app/templates/index.html`):
- Add `"clock"` button to `.modal__tabs` div (after the "Chart" tab):
  ```html
  <button class="modal__tab" data-tab="clock">Clock</button>
  ```
- Add clock form section (after `chart-form-section`):
  ```html
  <div id="clock-form-section" class="section--hidden">
    <form id="add-clock-form">
      <label>
        Label
        <input id="clock-label" type="text" placeholder="e.g. Kitchen Clock" />
      </label>
      <label class="checkbox-row">
        <input id="clock-24h" type="checkbox" />
        24-hour format
      </label>
      <label class="checkbox-row">
        <input id="clock-seconds" type="checkbox" />
        Show seconds
      </label>
      <div class="modal__actions">
        <button type="button" id="btn-cancel-clock" class="btn">Cancel</button>
        <button type="submit" class="btn btn--primary">Add</button>
      </div>
    </form>
  </div>
  ```
- Add `<script src="/static/js/clock.js"></script>` between chart.js and app.js

**Step 5 — Wire into app.js**:
- In `addTileToGrid(tile)`: add case before the entity fallback:
  ```javascript
  if (tile.tile_type === "clock") {
    ClockTiles.addClockTileToGrid(tile, grid);
    return;
  }
  ```
- In `serializeLayout()`: add clock case to the serialization switch:
  ```javascript
  } else if (tileType === "clock") {
    tiles.push({
      ...base,
      label:        d.label,
      format_24h:   d.format24h === "true",
      show_seconds: d.showSeconds === "true",
    });
  ```
- In `refreshTileStates()`: add `if (type === "clock") continue;` (display-only, no HA state)
- In `handleTileClick()`: add `if (type === "clock") return;` (display-only, no toggle)
- In `activateTab()`: add `document.getElementById("clock-form-section").classList.toggle("section--hidden", tabName !== "clock");`
- In `openEditModal()`: add clock branch:
  ```javascript
  } else if (type === "clock") {
    activateTab("clock");
    ClockTiles.populateForEdit(tileEl);
    document.querySelector("#add-clock-form button[type='submit']").textContent = "Save";
  }
  ```
- In `closeAddModal()`: reset clock form and restore button text:
  ```javascript
  const clockForm = document.getElementById("add-clock-form");
  if (clockForm) clockForm.reset();
  const clockSubmit = document.querySelector("#add-clock-form button[type='submit']");
  if (clockSubmit) clockSubmit.textContent = "Add";
  ```
- In `init()`: call `ClockTiles.initModal()` and `ClockTiles.startClock()`

**Step 6 — Tests**:
- No backend route, so model-only tests. Add to existing test file or create `tests/test_models.py`:
  - `test_clock_tile_defaults()` — verify `format_24h=False`, `show_seconds=False`, `w=2`, `h=2`
  - `test_clock_tile_in_layout()` — round-trip: create Layout with a ClockTile, serialize, deserialize, assert fields match
  - `test_clock_tile_discriminator()` — verify `tile_type="clock"` round-trips through the `AnyTile` union

---

### 2. Calendar / Agenda Tile (`tile_type: "calendar"`)

**What it does**: Shows upcoming events from Home Assistant's calendar integration (Google Calendar, CalDAV, local). Common on kitchen/hallway dashboards. Read-only display — no toggles.

**Scaling behavior**:
- 2×1: Single next event one-liner ("Meeting 2:00 PM")
- 2×2: Next 2–3 events (time + title)
- 3×3: Next 5+ events grouped by day with date headers
- 4×4: Full agenda view with all events across multiple days

**Implementation plan**:

**Step 1 — Model** (`app/models.py`):
- Add `CalendarTile(BaseModel)`:
  ```python
  class CalendarTile(BaseModel):
      tile_type: Literal["calendar"] = "calendar"
      id: str = Field(description="Unique tile identifier")
      label: str = Field(default="Calendar", description="Display label shown on the tile")
      entity_id: str = Field(description="HA calendar entity ID, e.g. calendar.family")
      days_ahead: int = Field(default=3, ge=1, le=14, description="Number of days to look ahead")
      max_events: int = Field(default=10, ge=1, le=50, description="Maximum events to display")
      x: int = Field(default=0, ge=0)
      y: int = Field(default=0, ge=0)
      w: int = Field(default=3, ge=1)
      h: int = Field(default=3, ge=1)
  ```
- Add to `AnyTile` union

**Step 2 — Backend** (`app/routers/calendar.py` — new file):
- Follow the `weather.py` pattern exactly: `APIRouter(prefix="/api/calendar", tags=["calendar"])`, import `settings`, use `httpx.AsyncClient(timeout=10)`, same error handling (`502` for connection errors, `504` for timeouts).
- Route: `GET /api/calendar`
  - Query params: `entity_id: str`, `days: int = Query(default=3)`
  - Validate `entity_id` matches `^calendar\.[a-z0-9_]+$` regex (consistent with `ha_proxy.py` validation)
  - Calculate date range: `start = datetime.date.today().isoformat()`, `end = (today + timedelta(days=days)).isoformat()`
  - Proxy to HA: `GET {ha_base_url}/api/calendars/{entity_id}?start={start}T00:00:00&end={end}T23:59:59` with `settings.ha_headers`
  - HA returns: `[{summary, start: {dateTime|date}, end: {dateTime|date}, ...}, ...]`
  - Normalize response — map each event to:
    ```python
    {
        "title": event["summary"],
        "start_iso": event["start"].get("dateTime") or event["start"].get("date"),
        "end_iso": event["end"].get("dateTime") or event["end"].get("date"),
        "all_day": "date" in event["start"],
    }
    ```
  - Sort by `start_iso`, truncate to `max_events` (passed as query param)
  - Cache: 5-minute in-memory per `(entity_id, days)` — same dict pattern as `_cache` in weather.py
- Register in `app/main.py`: `from app.routers import calendar` then `app.include_router(calendar.router)`

**Step 3 — Frontend JS** (`app/static/js/calendar.js` — new file):
- Create `CalendarTiles` IIFE following `WeatherTiles` pattern:
  - `REFRESH_INTERVAL = 5 * 60 * 1000` (5 minutes)
  - `escapeHTML(str)` — same textContent trick
  - `buildTileHTML(tile)` — edit/remove buttons + scrollable event container:
    ```html
    <button class="tile__edit" ...></button>
    <button class="tile__remove" ...></button>
    <div class="calendar-tile">
      <div class="calendar-header">${safeLabel}</div>
      <div class="calendar-events"><span class="calendar-loading">Loading…</span></div>
    </div>
    ```
  - `formatEventTime(startIso, endIso, allDay)` — returns "All day", "2:00 PM", or "2:00–3:30 PM" using `Intl.DateTimeFormat`
  - `formatDateHeader(isoDate)` — returns "Today", "Tomorrow", or "Wed, Mar 12" relative to current date
  - `renderEvents(contentEl, events)`:
    - Group events by date (extract `YYYY-MM-DD` from `start_iso`)
    - For each group: append a `.calendar-date-header` div, then `.calendar-event` rows
    - Each event row: `.calendar-time` span + `.calendar-title` span (escaped)
    - Add `.calendar-event--past` class if event end time is before now
    - Use `document.createElement` + `textContent` for all user data (XSS safe)
  - `refreshTile(gridItem)` — fetch from `/api/calendar?entity_id=...&days=...&max_events=...`, call `renderEvents` on success, show "Failed to load" on error (same pattern as `WeatherTiles.refreshTile`)
  - `refreshAllTiles()` — iterate `[data-tile-type="calendar"]` elements
  - `startRefreshTimer()` — `setInterval(refreshAllTiles, REFRESH_INTERVAL)`
  - `addCalendarTileToGrid(tile, grid)` — create element, set dataset attrs (`tileType`, `tileId`, `label`, `entityId`, `daysAhead`, `maxEvents`), build content, call `grid.addWidget`, call `refreshTile` immediately
  - `populateForEdit(tileEl)` — fill form fields from dataset
  - `initModal()` — form submit handler following `WeatherTiles.initModal` pattern
  - Public API: `{ addCalendarTileToGrid, populateForEdit, initModal, startRefreshTimer, refreshTile }`

**Step 4 — CSS** (`app/static/css/style.css`):
- Add `--calendar-bg` theme variable (dark: `#1b2535`, light: `#edf2f7`, eink: `#f5f5f5`)
- Calendar tile styles:
  ```css
  .calendar-tile {
    container-name: calendar;
    container-type: size;
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    background: var(--calendar-bg);
    color: var(--text);
    padding: 8px;
    overflow: hidden;
  }
  .calendar-header {
    font-size: max(0.55rem, min(9cqi, 12cqb));
    font-weight: 600;
    color: var(--text-dim);
    margin-bottom: 4px;
    flex-shrink: 0;
  }
  .calendar-events {
    flex: 1;
    overflow-y: auto;
    scrollbar-width: thin;
  }
  .calendar-date-header {
    font-size: max(0.45rem, min(7cqi, 10cqb));
    font-weight: 600;
    color: var(--text-dim);
    border-bottom: 1px solid var(--edit-outline);
    padding: 4px 0 2px;
    margin-top: 4px;
  }
  .calendar-date-header:first-child { margin-top: 0; }
  .calendar-event {
    display: flex;
    gap: 6px;
    padding: 3px 0;
    align-items: baseline;
  }
  .calendar-time {
    font-size: max(0.4rem, min(6cqi, 9cqb));
    color: var(--primary);
    white-space: nowrap;
    min-width: 3.5em;
    flex-shrink: 0;
  }
  .calendar-title {
    font-size: max(0.45rem, min(7cqi, 10cqb));
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text);
  }
  .calendar-event--past { opacity: 0.4; }
  .calendar-loading {
    font-size: max(0.5rem, min(8cqi, 11cqb));
    color: var(--text-dim);
  }
  @container calendar (max-height: 100px) {
    .calendar-header { display: none; }
    .calendar-date-header { display: none; }
    .calendar-event:nth-child(n+3) { display: none; }
  }
  @container calendar (max-width: 130px) {
    .calendar-time { display: none; }
  }
  ```

**Step 5 — Modal HTML** (`app/templates/index.html`):
- Add `"calendar"` tab button to `.modal__tabs`
- Add form section:
  ```html
  <div id="calendar-form-section" class="section--hidden">
    <form id="add-calendar-form">
      <label>
        Label
        <input id="calendar-label" type="text" placeholder="e.g. Family Calendar" />
      </label>
      <label>
        Calendar Entity
        <input id="calendar-entity" type="text" required placeholder="calendar.family" />
      </label>
      <label>
        Days ahead
        <input id="calendar-days" type="number" value="3" min="1" max="14" />
      </label>
      <label>
        Max events
        <input id="calendar-max-events" type="number" value="10" min="1" max="50" />
      </label>
      <div class="modal__actions">
        <button type="button" id="btn-cancel-calendar" class="btn">Cancel</button>
        <button type="submit" class="btn btn--primary">Add</button>
      </div>
    </form>
  </div>
  ```
- Add `<script src="/static/js/calendar.js"></script>` between chart.js and app.js

**Step 6 — Wire into app.js**:
- `addTileToGrid()`: add `if (tile.tile_type === "calendar") { CalendarTiles.addCalendarTileToGrid(tile, grid); return; }`
- `serializeLayout()`: add calendar case reading `d.entityId`, `d.label`, `d.daysAhead`, `d.maxEvents`
- `refreshTileStates()`: add `if (type === "calendar") continue;` (self-refreshing, not HA-state-driven)
- `handleTileClick()`: add `if (type === "calendar") return;` (display-only)
- `activateTab()`: add calendar-form-section toggle
- `openEditModal()`: add calendar branch calling `CalendarTiles.populateForEdit(tileEl)`
- `closeAddModal()`: reset calendar form
- `init()`: call `CalendarTiles.initModal()` and `CalendarTiles.startRefreshTimer()`

**Step 7 — Tests** (`tests/test_calendar.py`):
- Add `_calendar_cache` clearing to `conftest.py` (same pattern as weather cache clearing)
- `test_get_calendar_success()` — mock `httpx.AsyncClient.get` to return fake HA calendar events, verify response shape `[{title, start_iso, end_iso, all_day}, ...]`
- `test_get_calendar_all_day_event()` — verify `all_day: true` when event uses `date` instead of `dateTime`
- `test_calendar_cache_hit()` — call twice, verify upstream only called once (same pattern as `test_cache_hit_skips_upstream` in test_weather.py)
- `test_calendar_invalid_entity_id()` — verify 400 for entity IDs not matching `calendar.*` regex
- `test_calendar_events_sorted()` — verify events returned in chronological order

---

### 3. Energy Monitor Tile (`tile_type: "energy"`)

**What it does**: Displays real-time power consumption (watts), daily energy usage (kWh), optional cost estimate, and an SVG usage chart. Works with smart plugs, whole-home monitors (Emporia Vue, Sense), and any HA sensor reporting watts or kWh.

**Scaling behavior**:
- 1×1: Current watts only (e.g., "1.2 kW") with lightning bolt icon
- 2×2: Current watts + today's kWh + cost estimate
- 3×2: Watts + kWh + cost + SVG sparkline area chart (last 6 hours)
- 4×3: Full display with solar production row, grid import/export, 12-hour chart

**Implementation plan**:

**Step 1 — Model** (`app/models.py`):
- Add `EnergyTile(BaseModel)`:
  ```python
  class EnergyTile(BaseModel):
      tile_type: Literal["energy"] = "energy"
      id: str = Field(description="Unique tile identifier")
      label: str = Field(default="Energy", description="Display label shown on the tile")
      power_entity: str = Field(description="Sensor entity for current watts, e.g. sensor.power_consumption")
      energy_entity: Optional[str] = Field(
          default=None, description="Sensor entity for daily kWh (optional)"
      )
      solar_entity: Optional[str] = Field(
          default=None, description="Sensor entity for solar production watts (optional)"
      )
      cost_per_kwh: Optional[float] = Field(
          default=None, ge=0, description="Electricity cost per kWh for cost estimate"
      )
      x: int = Field(default=0, ge=0)
      y: int = Field(default=0, ge=0)
      w: int = Field(default=3, ge=1)
      h: int = Field(default=2, ge=1)
  ```
- Add to `AnyTile` union

**Step 2 — Backend** (`app/routers/energy.py` — new file):
- Follow `weather.py` pattern: `APIRouter(prefix="/api/energy", tags=["energy"])`, logger, cache dict
- Route: `GET /api/energy/history`
  - Query params: `entity_id: str`, `hours: int = Query(default=6, ge=1, le=24)`
  - Validate `entity_id` matches `^sensor\.[a-z0-9_]+$` regex
  - Calculate start time: `(datetime.utcnow() - timedelta(hours=hours)).isoformat()`
  - Proxy to HA: `GET {ha_base_url}/api/history/period/{start}?filter_entity_id={entity_id}&minimal_response&no_attributes` with `settings.ha_headers`
  - HA returns: `[[{state, last_changed}, ...]]` (array of arrays)
  - Downsample to ~1 point per 10 minutes: iterate entries, keep one per 10-min window
  - Return: `{"points": [{"iso": "2024-06-01T14:00:00", "value": 1250.0}, ...]}` — filter out non-numeric states ("unavailable", "unknown")
  - Cache: 2-minute TTL per `(entity_id, hours)` — same dict pattern as weather
- Register in `app/main.py`

**Step 3 — Frontend JS** (`app/static/js/energy.js` — new file):
- Create `EnergyTiles` IIFE:
  - `REFRESH_INTERVAL = 5 * 60 * 1000` (5 minutes for chart data)
  - `escapeHTML(str)`, `cssVar(name)` — same helpers as chart.js
  - `formatPower(watts)` — returns `"1.2 kW"` or `"450 W"` depending on magnitude
  - `formatEnergy(kwh)` — returns `"12.4 kWh"`
  - `formatCost(kwh, rate)` — returns `"$1.86"` or `""` if no rate
  - `buildTileHTML(tile)` — edit/remove buttons + energy container:
    ```html
    <div class="energy-tile">
      <i class="mdi mdi-lightning-bolt energy-icon"></i>
      <div class="energy-current">-- W</div>
      <div class="energy-daily"></div>
      <div class="energy-solar"></div>
      <div class="energy-chart"></div>
    </div>
    ```
  - `updateFromState(el, entityStates)` — called from `refreshTileStates()` in app.js:
    - Read `power_entity` state → update `.energy-current` with `formatPower()`
    - Read `energy_entity` state → update `.energy-daily` with kWh + cost
    - Read `solar_entity` state → update `.energy-solar` with solar watts
    - Color the icon: green if producing (solar > consumption), yellow otherwise
  - `renderChart(chartEl, points)` — SVG area chart using same `svgEl()` / `svgText()` / `makeSVG()` helpers from chart.js (or duplicated locally):
    - viewBox `"0 0 200 40"`, `preserveAspectRatio="none"`
    - Filled area below the line (`<polygon>`) with semi-transparent `var(--primary)` fill
    - Polyline on top with `var(--chart-line)` stroke
    - X-axis time labels ("2p", "3p") at evenly spaced intervals
    - Y-axis: normalize watts to viewBox y range 6–31
  - `refreshChart(gridItem)` — fetch from `/api/energy/history?entity_id=...&hours=6`, call `renderChart`
  - `refreshAllCharts()` — iterate `[data-tile-type="energy"]`, call `refreshChart`
  - `startRefreshTimer()` — `setInterval(refreshAllCharts, REFRESH_INTERVAL)`
  - `addEnergyTileToGrid(tile, grid)` — create element, set all dataset attrs (`powerEntity`, `energyEntity`, `solarEntity`, `costPerKwh`), build content, `grid.addWidget`, call `refreshChart`
  - `populateForEdit(tileEl)` — fill form from dataset
  - `initModal()` — form submit following standard pattern
  - Public API: `{ addEnergyTileToGrid, updateFromState, populateForEdit, initModal, startRefreshTimer }`

**Step 4 — CSS** (`app/static/css/style.css`):
- Add `--energy-bg` theme variable (dark: `#1b2520`, light: `#edf7ed`, eink: `#f5f5f5`)
- Add `--energy-solar: #22c55e` (green) across all themes
- Energy tile styles:
  ```css
  .energy-tile {
    container-name: energy;
    container-type: size;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    background: var(--energy-bg);
    color: var(--text);
    gap: 2px;
    padding: 8px;
  }
  .energy-icon {
    font-size: max(0.8rem, min(16cqi, 22cqb));
    color: var(--icon-on);
  }
  .energy-current {
    font-size: max(1.2rem, min(30cqi, 40cqb));
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
  }
  .energy-daily {
    font-size: max(0.45rem, min(8cqi, 11cqb));
    color: var(--text-dim);
  }
  .energy-solar {
    font-size: max(0.45rem, min(8cqi, 11cqb));
    color: var(--energy-solar);
  }
  .energy-chart {
    width: 100%;
    flex: 1;
    min-height: 0;
  }
  .energy-chart svg {
    width: 100%;
    height: 100%;
    display: block;
  }
  @container energy (max-height: 100px) {
    .energy-chart { display: none; }
    .energy-daily { display: none; }
    .energy-solar { display: none; }
    .energy-icon { display: none; }
  }
  @container energy (max-width: 130px) {
    .energy-daily { display: none; }
    .energy-solar { display: none; }
    .energy-chart { display: none; }
  }
  ```

**Step 5 — Modal HTML** (`app/templates/index.html`):
- Add `"energy"` tab button to `.modal__tabs`
- Add form section:
  ```html
  <div id="energy-form-section" class="section--hidden">
    <form id="add-energy-form">
      <label>
        Label
        <input id="energy-label" type="text" placeholder="e.g. Home Power" />
      </label>
      <label>
        Power sensor (watts)
        <input id="energy-power-entity" type="text" required placeholder="sensor.power_consumption" />
      </label>
      <label>
        Daily energy sensor (kWh) <small style="color: var(--text-dim)">(optional)</small>
        <input id="energy-energy-entity" type="text" placeholder="sensor.daily_energy" />
      </label>
      <label>
        Solar sensor (watts) <small style="color: var(--text-dim)">(optional)</small>
        <input id="energy-solar-entity" type="text" placeholder="sensor.solar_power" />
      </label>
      <label>
        Cost per kWh ($) <small style="color: var(--text-dim)">(optional)</small>
        <input id="energy-cost" type="number" step="0.01" min="0" placeholder="0.12" />
      </label>
      <div class="modal__actions">
        <button type="button" id="btn-cancel-energy" class="btn">Cancel</button>
        <button type="submit" class="btn btn--primary">Add</button>
      </div>
    </form>
  </div>
  ```
- Add `<script src="/static/js/energy.js"></script>` between chart.js and app.js

**Step 6 — Wire into app.js**:
- `addTileToGrid()`: add energy case
- `serializeLayout()`: add energy case reading `d.label`, `d.powerEntity`, `d.energyEntity`, `d.solarEntity`, `d.costPerKwh`
- `refreshTileStates()`: add energy case — call `EnergyTiles.updateFromState(el, entityStates)` (current watts/kWh update from poll; chart refreshes on its own timer)
- `handleTileClick()`: add `if (type === "energy") return;` (display-only)
- `activateTab()`, `openEditModal()`, `closeAddModal()`: add energy form handling
- `init()`: call `EnergyTiles.initModal()` and `EnergyTiles.startRefreshTimer()`

**Step 7 — Tests** (`tests/test_energy.py`):
- Add `_energy_cache` clearing to `conftest.py`
- `test_get_energy_history_success()` — mock HA history API, verify downsampled points
- `test_energy_filters_non_numeric()` — verify "unavailable" / "unknown" states are excluded
- `test_energy_cache_hit()` — call twice, verify upstream only called once
- `test_energy_invalid_entity_id()` — verify 400 for non-sensor entities

---

### 4. Garbage / Recycling Collection Tile (`tile_type: "waste"`)

**What it does**: Shows next pickup dates for trash, recycling, and yard waste. Uses HA integrations (Waste Collection Schedule HACS, custom template sensors). Very popular on kitchen dashboards. Display-only — no toggles.

**Scaling behavior**:
- 1×1: Single colored icon of the soonest pickup type
- 2×1: "Trash: Tomorrow" — soonest pickup as a one-liner
- 2×2: Next 2–3 pickup types with colored dot icons and relative dates
- 3×2: All waste types with icons, type names, and dates

**Implementation plan**:

**Step 1 — Model** (`app/models.py`):
- Add `WasteMember(BaseModel)` and `WasteTile(BaseModel)` following the `SceneMember`/`SceneTile` pattern for multi-member tiles:
  ```python
  class WasteMember(BaseModel):
      entity_id: str = Field(description="HA sensor entity ID for this waste type")
      waste_type: str = Field(description="Display name: Trash, Recycling, Yard Waste, etc.")
      color: str = Field(default="#6b7280", description="Hex color for the icon dot")
      icon: str = Field(default="mdi-trash-can", description="MDI icon name")

  class WasteTile(BaseModel):
      tile_type: Literal["waste"] = "waste"
      id: str = Field(description="Unique tile identifier")
      label: str = Field(default="Collection", description="Display label shown on the tile")
      members: List[WasteMember] = Field(
          description="Waste collection types to track",
          min_length=1,
      )
      x: int = Field(default=0, ge=0)
      y: int = Field(default=0, ge=0)
      w: int = Field(default=2, ge=1)
      h: int = Field(default=2, ge=1)
  ```
- Add to `AnyTile` union

**Step 2 — Backend**: No new routes needed. Waste collection sensors are standard HA `sensor.*` entities. Their `state` is typically:
- A date string like `"2024-06-05"` (from Waste Collection Schedule HACS integration)
- A number like `"2"` (days until next collection)
- Or a friendly string like `"Tomorrow"` (from custom template sensors)

All readable via the existing `GET /api/ha/states` poll.

**Step 3 — Frontend JS** (`app/static/js/waste.js` — new file):
- Create `WasteTiles` IIFE:
  - `escapeHTML(str)` — same helper
  - `parsePickupDate(stateValue)` — smart parser that handles multiple formats:
    - ISO date string `"2024-06-05"` → `Date` object
    - Number string `"2"` → `Date` = today + 2 days
    - Already-relative `"Today"` / `"Tomorrow"` → `Date` for today/tomorrow
    - Returns `null` for `"unavailable"` / `"unknown"`
  - `formatRelativeDate(date)` — returns human-friendly string:
    - Same day → `"Today"`
    - Tomorrow → `"Tomorrow"`
    - Within 6 days → weekday name `"Wednesday"`
    - Otherwise → `"Mar 12"`
  - `daysUntil(date)` — returns integer days from today (for sorting and urgency)
  - `buildTileHTML(tile)` — edit/remove buttons + waste container:
    ```html
    <div class="waste-tile">
      <div class="waste-header">${safeLabel}</div>
      <div class="waste-entries"></div>
    </div>
    ```
  - `updateFromState(el, entityStates)` — called during poll cycle from `refreshTileStates()`:
    - Parse `members` from `el.dataset.members` (JSON, same pattern as SceneTile)
    - For each member: read `entityStates[member.entity_id]`, call `parsePickupDate`, build entry object `{type, color, icon, date, daysUntil}`
    - Sort entries by `daysUntil` ascending (soonest first)
    - Clear `.waste-entries`, rebuild using `document.createElement`:
      - Each `.waste-entry`: colored `.waste-dot` (inline style `background: member.color`) + `.waste-type` span + `.waste-date` span
      - Add `.waste-entry--today` class if `daysUntil === 0`
      - Add `.waste-entry--tomorrow` class if `daysUntil === 1`
      - Use `textContent` for all user data (XSS safe)
  - `addWasteTileToGrid(tile, grid)` — create element, set dataset attrs (`tileType`, `tileId`, `label`, `members` as JSON string), build content, `grid.addWidget`
  - `populateForEdit(tileEl)` — pre-fill modal form from dataset, rebuild member rows
  - `initModal(getEntityStates)` — needs entity states for sensor dropdown. Dynamic member builder UI:
    - "Add type" button appends a row: sensor entity input + type name input + color picker `<input type="color">` + icon input + remove button
    - On submit: collect all member rows into array, create/update tile
  - `resetModal()` — clear all dynamic member rows (same pattern as `SceneTiles.resetModal`)
  - Public API: `{ addWasteTileToGrid, updateFromState, populateForEdit, initModal, resetModal }`

**Step 4 — CSS** (`app/static/css/style.css`):
- Waste tile styles:
  ```css
  .waste-tile {
    container-name: waste;
    container-type: size;
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    color: var(--text);
    padding: 8px;
    gap: 4px;
  }
  .waste-header {
    font-size: max(0.5rem, min(9cqi, 12cqb));
    font-weight: 600;
    color: var(--text-dim);
    flex-shrink: 0;
  }
  .waste-entries {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex: 1;
    overflow: hidden;
  }
  .waste-entry {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .waste-dot {
    width: max(8px, min(3cqi, 4cqb));
    height: max(8px, min(3cqi, 4cqb));
    border-radius: 50%;
    flex-shrink: 0;
  }
  .waste-type {
    font-size: max(0.45rem, min(7cqi, 10cqb));
    color: var(--text-dim);
    white-space: nowrap;
    min-width: 4em;
  }
  .waste-date {
    font-size: max(0.45rem, min(7cqi, 10cqb));
    color: var(--text);
    font-weight: 500;
    margin-left: auto;
  }
  .waste-entry--today .waste-date {
    color: var(--accent);
    font-weight: 700;
  }
  .waste-entry--tomorrow .waste-date {
    color: var(--icon-on);
    font-weight: 600;
  }
  @container waste (max-height: 80px) {
    .waste-header { display: none; }
    .waste-entry:nth-child(n+2) { display: none; }
  }
  @container waste (max-width: 130px) {
    .waste-type { display: none; }
  }
  ```

**Step 5 — Modal HTML** (`app/templates/index.html`):
- Add `"waste"` tab button to `.modal__tabs`
- Add form section with dynamic member builder:
  ```html
  <div id="waste-form-section" class="section--hidden">
    <div id="waste-form-inner">
      <label>
        Label
        <input id="waste-label" type="text" placeholder="e.g. Collection Schedule" />
      </label>
      <div class="waste-member-header">
        <span>Collection types</span>
        <button type="button" id="btn-waste-add-row" class="btn btn--small">+ Add</button>
      </div>
      <div id="waste-member-list"></div>
      <div class="modal__actions">
        <button type="button" id="btn-cancel-waste" class="btn">Cancel</button>
        <button type="button" id="btn-waste-confirm" class="btn btn--primary">Add</button>
      </div>
    </div>
  </div>
  ```
- Each dynamically added member row (created in JS):
  ```html
  <div class="waste-member-row">
    <input type="text" placeholder="sensor.trash_pickup" class="waste-row-entity" />
    <input type="text" placeholder="Trash" class="waste-row-type" />
    <input type="color" value="#4caf50" class="waste-row-color" />
    <button type="button" class="waste-row-remove btn btn--small">✕</button>
  </div>
  ```
- Add `<script src="/static/js/waste.js"></script>` between chart.js and app.js

**Step 6 — Wire into app.js**:
- `addTileToGrid()`: add waste case
- `serializeLayout()`: add waste case reading `d.label` and `JSON.parse(d.members)` (same pattern as scene serialization)
- `refreshTileStates()`: add waste case — call `WasteTiles.updateFromState(el, entityStates)` (reads sensor states from the poll)
- `handleTileClick()`: add `if (type === "waste") return;` (display-only)
- `activateTab()`, `openEditModal()`, `closeAddModal()`: add waste form handling. `closeAddModal` must call `WasteTiles.resetModal()` (same pattern as `SceneTiles.resetModal()`)
- `init()`: call `WasteTiles.initModal(() => entityStates)` (passes state getter, same pattern as `SceneTiles.initModal`)

**Step 7 — Tests**:
- Model tests: verify `WasteMember` and `WasteTile` serialization, `min_length=1` on members, default color/icon values
- Verify `WasteTile` round-trips through the `AnyTile` discriminated union
- No backend route tests needed (uses existing HA state proxy)

---

### General Implementation Notes for All New Tiles

**Pattern to follow for every new tile** (checklist):

1. **Model**: Add Pydantic model class to `app/models.py` with `tile_type: Literal["..."]` discriminator, `Field(description=...)` on all fields, grid position fields `x, y, w, h` with `ge=0`/`ge=1`. Add to `AnyTile` union.
2. **JS module**: Create `app/static/js/{tiletype}.js` as a `"use strict"` IIFE exposing a global (e.g., `ClockTiles`). Include `escapeHTML()` helper. Follow the `buildTileHTML` → `addXxxTileToGrid` → `initModal` → public API pattern from weather.js.
3. **HTML**: Add `<script>` tag to `index.html` BEFORE `app.js`. Add tab button to `.modal__tabs`. Add form `<div>` section with `class="section--hidden"`.
4. **CSS**: Add to `style.css` with `container-name` and `container-type: size`. Use `cqi`/`cqb` units for font sizing. Add `@container` queries for small-tile breakpoints. Add theme-specific `--*-bg` variable to all three theme blocks (:root, [data-theme="light"], [data-theme="eink"]).
5. **app.js wiring** — touch all these functions:
   - `addTileToGrid()` — add type case
   - `serializeLayout()` — add serialization case reading from `dataset`
   - `refreshTileStates()` — add `continue` (display-only) or call module's `updateFromState()` (state-driven)
   - `handleTileClick()` — add `return` (display-only) or call module's toggle handler
   - `activateTab()` — add form section toggle
   - `openEditModal()` — add branch calling module's `populateForEdit()`
   - `closeAddModal()` — reset form, restore button text, call module's `resetModal()` if it has one
   - `init()` — call module's `initModal()` and `startRefreshTimer()` / `startClock()` if applicable
6. **Backend** (if needed): Create `app/routers/{name}.py` following `weather.py` pattern: `APIRouter(prefix=..., tags=[...])`, `httpx.AsyncClient(timeout=10)`, in-memory cache dict, same error handling (502/504). Register in `app/main.py`.
7. **Tests**: Mock external APIs with `httpx` mocking pattern from existing tests. Add cache clearing to `conftest.py`. Run `poetry run pytest -v && poetry run ruff check .` before done.

**Scaling philosophy**: Every tile should be usable at 1×1 (minimal info) and gracefully add detail as size increases. Use `@container` queries with `cqi`/`cqb` units for font sizing and show/hide thresholds at specific pixel breakpoints. Never use viewport-based media queries for tile content — tiles are responsive to their own container size, not the screen.
