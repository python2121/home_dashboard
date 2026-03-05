# Home Dashboard

A self-hosted, touch-friendly web dashboard for [Home Assistant](https://www.home-assistant.io/). Designed for full-screen display on an Android tablet or iPad — big tiles, dark theme, instant toggles.

**Features:**
- Resizable, repositionable tiles that snap to a 12-column grid
- Edit mode with drag-and-drop layout customization (locked in normal use)
- Tile contents (icon, label) scale with tile size
- **Entity tiles** — toggle lights, switches, fans, covers, locks, climate, and media players; brightness slider for dimmable lights
- **Scene tiles** — control a group of lights, each at its own brightness, with a two-step builder and live HA preview
- **Weather tiles** — current conditions + 5-day forecast via Open-Meteo (no API key required)
- **Forecast chart tiles** — 12-hour temperature line chart, or minute-by-minute rain probability chart (requires Pirate Weather API key)
- Tile layout persists across restarts
- 5-second state polling with optimistic UI on toggle
- Scene state is determined by brightness matching — only the scene whose targets match the actual light brightness shows as active
- Runs fully self-hosted — no cloud, no external dependencies beyond CDNs for icons and GridStack

---

## Prerequisites

| Requirement | Minimum |
|---|---|
| Python | 3.9+ |
| [Poetry](https://python-poetry.org/docs/#installation) | 1.8+ |
| Home Assistant | Any recent version with REST API enabled (default) |
| Docker + Docker Compose | For container deployment |

---

## Getting a Home Assistant Token

The dashboard authenticates to Home Assistant using a Long-Lived Access Token.

1. Open your Home Assistant UI
2. Click your user avatar (bottom-left)
3. Scroll to **Long-Lived Access Tokens**
4. Click **Create Token**, give it a name (e.g. `home-dashboard`), and copy the value

Keep this token — you'll need it in the configuration step below.

---

## Configuration

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```ini
# Home Assistant — replace with your HA server's IP and the token you just generated
HA_BASE_URL=http://192.168.1.100:8123
HA_TOKEN=your_long_lived_access_token_here

# Optional — required only for the rain chart mode on forecast chart tiles
# Get a free key at https://pirateweather.net
# PIRATE_WEATHER_KEY=your_pirate_weather_key_here

# Optional — set to true to enable /docs (Swagger UI) and verbose logging
# DEBUG=false
```

> `.env` is gitignored and must never be committed.

---

## Running Locally

Install dependencies:

```bash
poetry install --no-root
```

Start the dev server with hot-reload:

```bash
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your browser.

### Running Tests

```bash
# All tests
poetry run pytest -v

# Single test file
poetry run pytest tests/test_ha_proxy.py -v
```

### Linting & Formatting

```bash
poetry run ruff check .
poetry run ruff format .
```

---

## Deploying with Docker

The recommended way to run the dashboard on your home server.

### First-time build and start

```bash
docker compose up -d --build
```

The dashboard will be available at `http://<your-server-ip>:8000`.

The tile layout is stored in a named Docker volume (`dashboard-data`) and survives container restarts and image rebuilds.

### Subsequent deploys (after code changes)

```bash
docker compose up -d --build
```

Docker will rebuild only changed layers thanks to the multi-stage build and layer caching.

### View logs

```bash
docker compose logs -f
```

### Stop

```bash
docker compose down
```

### Check health

```bash
docker compose ps
```

The container has a healthcheck that polls `GET /` every 30 seconds. Status will show `healthy` once the app is fully up.

### Exposing on a different port

Edit `docker-compose.yml`:

```yaml
ports:
  - "80:8000"   # serve on port 80 instead
```

---

## Using the Dashboard

### Normal mode

- **Tap an entity tile** to toggle the entity on/off
- **Drag the brightness slider** (bottom of a light tile) to dim — only visible when the light is on
- **Tap a scene tile** to activate that lighting scene (turns all member lights to their saved brightness). Tapping an active scene turns it off.
- **Weather and chart tiles** are display-only — tapping them does nothing
- The small colored dot in the top-right corner shows Home Assistant connectivity:
  - 🟠 Orange — connecting
  - 🟢 Green — connected and polling
  - 🔴 Red — connection error (check logs)

### Edit mode

- Tap the **pencil FAB** (bottom-right) to enter edit mode
- **Drag tiles** to reposition them on the grid
- **Resize tiles** by dragging the resize handle (bottom-right corner of each tile)
- Tap the **pencil button** on a tile to edit its settings (entity, label, icon, scene members, etc.)
- Tap the **✕** on a tile to remove it
- Tap **Add Tile** to open the tile builder with four tabs:
  - **Entity** — pick a HA entity, label, and icon
  - **Scene** — two-step builder: pick lights, then drag per-light brightness sliders with live HA preview
  - **Weather** — enter a ZIP code and temperature unit
  - **Chart** — enter a ZIP code and temperature unit; displays rain or temperature chart depending on conditions
- Tap **Done** to save the layout and exit edit mode

### Icons

Icons use [Material Design Icons](https://pictogrammers.com/library/mdi/). When adding or editing a tile, an icon picker is shown below the icon field — click any icon to select it, or type in the field to filter. Icon names follow the pattern `mdi-ceiling-fan`, `mdi-floor-lamp`, etc.

### Scenes

A scene tile controls a group of `light.*` entities, each at its own target brightness (1–255). On each state poll, the dashboard checks whether the actual HA brightness of every member light is within ±15 of its saved target. Only the scene whose targets match the current state shows as active — so if your lights are at "TV Time" brightness, only that scene highlights, not "Full Brightness".

Tapping a scene tile:
- **Off → On**: sets each member light to its saved brightness concurrently
- **On → Off**: turns all member lights off

Activating one scene automatically marks any overlapping scene as inactive in the UI.

### Forecast Chart Tiles

The chart tile is a fixed 1-row-tall strip designed to sit along the top or bottom of your layout.

- **Rain mode** — when any of the next 60 minutes has >10% precipitation probability, shows a 60-bar chart of minute-by-minute rain probability. Requires a `PIRATE_WEATHER_KEY` in `.env`.
- **Temp mode** — when no rain is imminent (or no Pirate Weather key is configured), shows a 12-hour temperature line chart with sunrise and sunset markers.

The chart automatically picks the appropriate mode on each 5-minute refresh.

---

## Project Structure

```
home_dashboard/
├── app/
│   ├── main.py              # FastAPI entrypoint
│   ├── config.py            # Settings (loaded from .env)
│   ├── models.py            # Pydantic models: EntityTile, SceneTile, WeatherTile, ForecastChartTile, Layout
│   ├── routers/
│   │   ├── ha_proxy.py      # Proxies requests to Home Assistant (/api/ha/*)
│   │   ├── layout.py        # Saves/loads tile layout (/api/layout)
│   │   └── weather.py       # Weather + chart data via Open-Meteo, Nominatim, Pirate Weather (/api/weather)
│   ├── static/
│   │   ├── css/style.css    # Dark kiosk theme
│   │   └── js/
│   │       ├── app.js       # Grid, edit mode, entity tiles, state polling
│   │       ├── scene.js     # Scene tile module (state matching, builder, toggle)
│   │       ├── weather.js   # Weather tile module (rendering, refresh timer)
│   │       └── chart.js     # Forecast chart tile module (rain bars, temp line chart)
│   └── templates/
│       └── index.html       # Main page (Jinja2 shell)
├── tests/                   # Pytest test suite
├── data/                    # Layout JSON — auto-created, gitignored
├── .env.example             # Config template (commit this)
├── .env                     # Your secrets (never commit)
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## API Overview

The FastAPI backend exposes these routes (all JSON):

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/ha/states` | All HA entity states |
| `GET` | `/api/ha/states/{entity_id}` | Single entity state |
| `POST` | `/api/ha/toggle/{entity_id}` | Toggle an entity on/off |
| `POST` | `/api/ha/services/{domain}/{service}` | Call any HA service (e.g. `light/turn_on`) |
| `POST` | `/api/ha/scene-toggle` | Turn a group of lights on/off with per-light brightness |
| `GET` | `/api/layout` | Fetch the saved tile layout |
| `PUT` | `/api/layout` | Save the tile layout |
| `GET` | `/api/weather` | Current conditions + 5-day forecast for a ZIP code |
| `GET` | `/api/weather/chart` | Rain or 12-hour temperature chart for a ZIP code |

Enable `DEBUG=true` in `.env` to expose Swagger UI at `/docs`.

---

## Security Notes

- The Home Assistant token lives **only on the server** — it is never sent to the browser
- All entity IDs, domains, and service names are validated with strict regex patterns before being forwarded to Home Assistant
- The dashboard itself has **no authentication** — it is designed to run on a trusted local network. Do not expose port 8000 to the internet without adding a reverse proxy with authentication (e.g. Nginx + basic auth, Authelia, etc.)

---

## Troubleshooting

**Red status indicator / tiles not loading**
- Check that `HA_BASE_URL` in `.env` is correct and reachable from the server running the dashboard
- Verify your token is valid: `curl -H "Authorization: Bearer YOUR_TOKEN" http://YOUR_HA_IP:8123/api/`

**`Cannot connect to Home Assistant` error in logs**
- The dashboard server cannot reach HA. Check firewall rules and that HA is running.

**`401 Unauthorized` error**
- Your `HA_TOKEN` is invalid or expired. Generate a new one in the HA UI.

**Tiles missing after restart**
- In Docker, ensure the `dashboard-data` volume exists: `docker volume ls | grep dashboard`
- In local dev, check that `data/layout.json` exists and is valid JSON

**Scene tiles all show as active on load**
- This was a known bug where scenes only checked whether lights were on, not their brightness. It is fixed — if you still see it, do a hard refresh (`Cmd+Shift+R` / `Ctrl+Shift+R`) to clear the browser's JS cache.

**Edit mode — tiles not draggable**
- Make sure you tapped the pencil FAB to enter edit mode first. The grid is locked in normal mode.

**Weather tile shows "Failed to load"**
- Check that your server has internet access (Open-Meteo and Nominatim are external services)
- Verify the ZIP code and country code are valid

**Chart tile shows "Failed to load"**
- If you have a `PIRATE_WEATHER_KEY` set, verify the key is valid at [pirateweather.net](https://pirateweather.net)
- Without a key the chart falls back to temp mode — check server internet access for Open-Meteo
- Check logs: `docker compose logs -f` or the uvicorn console output
