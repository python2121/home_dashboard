# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A self-hosted web-based home dashboard designed to display on an Android tablet or iPad browser. It connects to a local Home Assistant instance via its REST API and provides large, touch-friendly controls for lights, fans, and rooms.

The UI consists of resizable, repositionable tiles with rounded corners that snap to a grid. An "edit mode" allows layout customization; outside of edit mode the layout is locked. Tile contents (icons, labels) scale with tile size.

## Tech Stack

- **Backend**: Python (3.9+) with [FastAPI](https://fastapi.tiangolo.com/) — proxies Home Assistant API calls so credentials never reach the browser
- **Templating**: Jinja2 (served by FastAPI) for the initial HTML shell
- **Frontend**: Vanilla JS + CSS — tile drag/resize uses [GridStack.js](https://gridstackjs.com/)
- **Dependency management**: [Poetry](https://python-poetry.org/)
- **Containerization**: Docker + Docker Compose (runtime image uses Python 3.11)
- **CI/CD**: GitHub Actions (to be added)

## Home Assistant Integration

Home Assistant exposes a REST API at `http://<HA_HOST>:8123/api/`. All requests require:

```
Authorization: Bearer <LONG_LIVED_ACCESS_TOKEN>
Content-Type: application/json
```

Key endpoints used:
- `GET  /api/states` — fetch all entity states on startup / for sync
- `GET  /api/states/<entity_id>` — single entity state
- `POST /api/services/<domain>/<service>` — control entities (e.g. `light/turn_on`, `switch/turn_off`, `fan/turn_on`)

The FastAPI backend acts as a thin proxy: the browser calls `/api/ha/...` routes, the server attaches the Bearer token, forwards to Home Assistant, and returns the result. This keeps the token server-side only.

All path parameters (entity_id, domain, service) are validated with strict regex patterns to prevent SSRF/path traversal.

## Credentials & Configuration

All secrets live in a `.env` file at the project root (never committed). Copy `.env.example` to `.env` and fill in values.

```
HA_BASE_URL=http://192.168.x.x:8123
HA_TOKEN=<long-lived access token>
```

The application loads config via Pydantic `BaseSettings`. No credentials are hardcoded anywhere.

## Project Structure

```
home_dashboard/
├── app/
│   ├── main.py            # FastAPI app entrypoint
│   ├── config.py          # Settings loaded from .env
│   ├── models.py          # Pydantic models: EntityTile, WeatherTile (discriminated union), Layout, ServiceCall
│   ├── routers/
│   │   ├── ha_proxy.py    # /api/ha/* proxy routes to Home Assistant
│   │   ├── layout.py      # /api/layout — tile layout persistence
│   │   └── weather.py     # /api/weather — Open-Meteo forecast + Nominatim geocoding, 30-min cache
│   ├── static/
│   │   ├── css/style.css  # Dark kiosk theme
│   │   └── js/
│   │       ├── app.js     # GridStack grid, edit mode, state polling (type-aware)
│   │       └── weather.js # WeatherTiles module — rendering, modal tabs, refresh timer
│   └── templates/
│       └── index.html     # Jinja2 shell, loads GridStack + MDI from CDN
├── tests/
├── data/                  # Layout JSON stored here (gitignored, Docker volume)
├── .env.example           # Committed credential template
├── Dockerfile             # Multi-stage: builder (Poetry) → slim runtime
├── docker-compose.yml
├── pyproject.toml
└── poetry.lock
```

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

The container runs as a non-root user on a local Linux server. The `.env` file is passed via `env_file` in docker-compose.yml. Layout data persists in a named Docker volume.

The Dockerfile uses a multi-stage build: a `builder` stage installs Poetry dependencies into a venv, and the final stage copies only the venv and `app/` directory.

## CI/CD (planned)

GitHub Actions pipeline will:
1. Run linting (`ruff`) and tests (`pytest`) on every push/PR
2. Build the Docker image and push to GitHub Container Registry (GHCR) on merges to `main`
3. Optionally trigger a webhook to pull and restart the container on the home server

## Frontend Architecture

- GridStack.js manages the tile grid — layout is serialized and persisted to the backend via `PUT /api/layout`
- An **edit mode** toggle shows resize handles and drag cursors; in normal mode the grid is locked (`setStatic(true)`)
- Each tile maps to a Home Assistant entity. Tile metadata (entity_id, label, icon, grid position/size) is stored as JSON
- Icons use [Material Design Icons](https://materialdesignicons.com/) (font CDN) so they scale cleanly
- The page is designed for full-screen kiosk display (no scrollbars, viewport-locked layout)
- Entity states are polled every 5 seconds; tile toggles use optimistic UI with rollback on failure
- All user-provided text is HTML-escaped before DOM insertion to prevent XSS
