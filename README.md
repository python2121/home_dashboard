# Home Dashboard

A self-hosted, touch-friendly web dashboard for [Home Assistant](https://www.home-assistant.io/). Designed for full-screen display on an Android tablet or iPad — big tiles, dark theme, instant toggles.

**Features:**
- Resizable, repositionable tiles that snap to a 12-column grid
- Edit mode with drag-and-drop layout customization (locked in normal use)
- Tile contents (icon, label) scale with tile size
- Supports lights, switches, fans, covers, locks, climate, and media players
- Tile layout persists across restarts
- 5-second state polling with optimistic UI on toggle
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
# Build the image and start the container in the background
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

- **Tap a tile** to toggle the entity on/off
- The small colored dot in the top-right corner shows Home Assistant connectivity:
  - 🟠 Orange — connecting
  - 🟢 Green — connected and polling
  - 🔴 Red — connection error (check logs)

### Edit mode

- Tap the **pencil FAB** (bottom-right) to enter edit mode
- **Drag tiles** to reposition them on the grid
- **Resize tiles** by dragging the resize handle (bottom-right corner of each tile)
- Tap **Add Tile** to add a new tile — choose an entity from your Home Assistant, set a label and icon
- Tap the **✕** on a tile to remove it
- Tap **Done** to save the layout and exit edit mode

### Icons

Icons use [Material Design Icons](https://pictogrammers.com/library/mdi/). To find an icon name:
1. Visit the MDI icon library and search for what you want
2. Copy the icon name (e.g. `mdi-ceiling-fan`, `mdi-floor-lamp`)
3. Paste it in the icon field when adding a tile

---

## Project Structure

```
home_dashboard/
├── app/
│   ├── main.py              # FastAPI entrypoint
│   ├── config.py            # Settings (loaded from .env)
│   ├── models.py            # Pydantic models
│   ├── routers/
│   │   ├── ha_proxy.py      # Proxies requests to Home Assistant
│   │   └── layout.py        # Saves/loads tile layout
│   ├── static/
│   │   ├── css/style.css    # Dark kiosk theme
│   │   └── js/app.js        # Frontend logic
│   └── templates/
│       └── index.html       # Main page
├── tests/                   # Pytest test suite
├── data/                    # Layout JSON — auto-created, gitignored
├── .env.example             # Config template (commit this)
├── .env                     # Your secrets (never commit)
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

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

**Edit mode — tiles not draggable**
- Make sure you tapped the pencil FAB to enter edit mode first. The grid is locked in normal mode.
