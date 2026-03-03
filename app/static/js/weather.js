/**
 * Home Dashboard — Weather tile module.
 *
 * Handles weather tile rendering, the "Weather" tab in the Add Tile modal,
 * data fetching from /api/weather, and periodic refresh.
 */

"use strict";

const WeatherTiles = (() => {
  const REFRESH_INTERVAL = 30 * 60 * 1000; // 30 minutes

  // ── Helpers ──────────────────────────────────────────────────────────

  function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ── Tile construction ────────────────────────────────────────────────

  function buildTileHTML(tile) {
    const safeId    = escapeHTML(tile.id);
    const safeLabel = escapeHTML(tile.label || "Weather");
    return `
      <button class="tile__edit" data-tile-id="${safeId}" title="Edit tile">
        <i class="mdi mdi-pencil"></i>
      </button>
      <button class="tile__remove" data-tile-id="${safeId}" title="Remove tile">
        <i class="mdi mdi-close"></i>
      </button>
      <div class="weather-tile">
        <div class="weather-current">
          <i class="mdi mdi-weather-cloudy weather-icon"></i>
          <div class="weather-temp">--</div>
          <div class="weather-hilo"></div>
          <div class="weather-desc">Loading…</div>
        </div>
        <div class="weather-label">${safeLabel}</div>
        <div class="weather-forecast"></div>
      </div>
    `;
  }

  // ── Data rendering ───────────────────────────────────────────────────

  function renderData(contentEl, data) {
    const cur = data.current;

    contentEl.querySelector(".weather-icon").className =
      `mdi ${escapeHTML(cur.icon)} weather-icon`;
    contentEl.querySelector(".weather-temp").textContent =
      `${cur.temp}${cur.unit}`;
    contentEl.querySelector(".weather-hilo").textContent =
      `H: ${cur.high}${cur.unit}  /  L: ${cur.low}${cur.unit}`;
    contentEl.querySelector(".weather-desc").textContent = cur.desc;

    const forecastEl = contentEl.querySelector(".weather-forecast");
    forecastEl.innerHTML = "";
    for (const day of data.forecast) {
      // day.date is YYYY-MM-DD; use noon local time to avoid timezone rollback
      const date = new Date(`${day.date}T12:00:00`);
      const dayName = date.toLocaleDateString("en-US", { weekday: "short" });
      const dayEl = document.createElement("div");
      dayEl.className = "weather-day";
      dayEl.innerHTML = `
        <div class="weather-day-date">${escapeHTML(dayName)}</div>
        <i class="mdi ${escapeHTML(day.icon)} weather-day-icon"></i>
        <div class="weather-day-hilo">H:${day.high}° L:${day.low}°</div>
      `;
      forecastEl.appendChild(dayEl);
    }
  }

  // ── Fetch and refresh ────────────────────────────────────────────────

  async function refreshTile(gridItem) {
    const zip     = gridItem.dataset.zipCode;
    const country = gridItem.dataset.countryCode;
    const unit    = gridItem.dataset.unit;
    const contentEl = gridItem.querySelector(".grid-stack-item-content");

    const params = new URLSearchParams({ zip_code: zip, country_code: country, unit });
    try {
      const res = await fetch(`/api/weather?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      renderData(contentEl, data);
    } catch (err) {
      console.error("Weather fetch failed:", err);
      const descEl = contentEl.querySelector(".weather-desc");
      if (descEl) descEl.textContent = "Failed to load";
    }
  }

  function refreshAllTiles() {
    for (const el of document.querySelectorAll(".grid-stack-item[data-tile-type='weather']")) {
      refreshTile(el);
    }
  }

  function startRefreshTimer() {
    setInterval(refreshAllTiles, REFRESH_INTERVAL);
  }

  // ── Tile creation ────────────────────────────────────────────────────

  function addWeatherTileToGrid(tile, grid) {
    const el = document.createElement("div");
    el.className = "tile--weather";
    el.dataset.tileType    = "weather";
    el.dataset.tileId      = tile.id;
    el.dataset.label       = tile.label || "Weather";
    el.dataset.zipCode     = tile.zip_code;
    el.dataset.countryCode = tile.country_code || "US";
    el.dataset.unit        = tile.unit || "fahrenheit";

    const content = document.createElement("div");
    content.className = "grid-stack-item-content";
    content.innerHTML = buildTileHTML(tile);
    el.appendChild(content);

    grid.addWidget(el, { x: tile.x, y: tile.y, w: tile.w, h: tile.h });
    refreshTile(el);
  }

  // ── Modal wiring ─────────────────────────────────────────────────────

  /** Wire up only the weather form — tab switching is owned by scene.js. */
  function initModal() {
    const weatherForm = document.getElementById("add-weather-form");
    const cancelBtn   = document.getElementById("btn-cancel-weather");

    weatherForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const label       = document.getElementById("weather-label").value.trim() || "Weather";
      const zip_code    = document.getElementById("weather-zip").value.trim();
      const country_code = (document.getElementById("weather-country").value.trim() || "US").toUpperCase();
      const unit        = document.getElementById("weather-unit").value;

      if (!zip_code) return;

      const editEl = DashboardApp.getEditingTile();
      if (editEl) {
        // Update tile in-place
        editEl.dataset.label       = label;
        editEl.dataset.zipCode     = zip_code;
        editEl.dataset.countryCode = country_code;
        editEl.dataset.unit        = unit;

        // Update visible label
        const labelEl = editEl.querySelector(".weather-label");
        if (labelEl) labelEl.textContent = label;

        // Re-fetch weather data for possibly new location
        refreshTile(editEl);
        DashboardApp.closeAddModal();
        return;
      }

      const tile = {
        id:           "tile_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
        tile_type:    "weather",
        label,
        zip_code,
        country_code,
        unit,
        x: 0, y: 0, w: 4, h: 4,
      };
      addWeatherTileToGrid(tile, DashboardApp.getGrid());
      DashboardApp.closeAddModal();
    });

    if (cancelBtn) {
      cancelBtn.addEventListener("click", () => DashboardApp.closeAddModal());
    }
  }

  // ── Public API ───────────────────────────────────────────────────────
  return { addWeatherTileToGrid, refreshTile, startRefreshTimer, initModal };
})();
