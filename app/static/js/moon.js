/**
 * Home Dashboard — Moon phase tile module.
 *
 * Handles moon tile rendering, the "Moon" tab in the Add Tile modal,
 * data fetching from /api/moon, SVG moon visual, and periodic refresh.
 */

"use strict";

const MoonTiles = (() => {
  const REFRESH_INTERVAL = 60 * 60 * 1000; // 1 hour

  // ── Helpers ──────────────────────────────────────────────────────────

  function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ── Moon SVG rendering ───────────────────────────────────────────────

  /**
   * Build an SVG string rendering the moon with shadow overlay.
   * @param {number} fraction - Illumination fraction 0–1
   * @param {string} phase - Phase name (used to determine shadow direction)
   * @returns {string} SVG markup
   */
  function buildMoonSVG(fraction, phase) {
    const cx = 50, cy = 50, r = 42;
    const phaseLower = (phase || "").toLowerCase();

    // Determine if waxing (shadow on left, lit on right) or waning (shadow on right, lit on left)
    const isWaxing = phaseLower.includes("waxing") ||
                     phaseLower === "new moon" ||
                     phaseLower === "first quarter";

    // Compute the terminator curve using illumination fraction.
    // fraction = 0 → new moon (all shadow), fraction = 1 → full moon (no shadow)
    // The terminator is an ellipse whose x-radius varies with fraction.
    const shadowFraction = 1 - fraction;

    // Build a shadow path over the moon circle
    // We use two arcs: one follows the moon's edge, the other is the terminator
    let shadowPath = "";

    if (shadowFraction < 0.01) {
      // Full moon — no shadow
      shadowPath = "";
    } else if (shadowFraction > 0.99) {
      // New moon — full shadow
      shadowPath = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="rgba(0,0,0,0.85)" />`;
    } else {
      // Partial illumination: draw shadow using two arcs
      // The terminator x-offset from center
      const terminatorX = r * Math.abs(2 * fraction - 1);
      const bulgeRight = fraction > 0.5; // terminator bulges toward lit side

      if (isWaxing) {
        // Shadow on the LEFT side
        // Top of moon to bottom via left edge (large arc), then bottom to top via terminator
        const sweepEdge = 1; // left arc = large sweep
        const sweepTerm = bulgeRight ? 1 : 0;
        shadowPath = `<path d="M ${cx} ${cy - r} A ${r} ${r} 0 1 0 ${cx} ${cy + r} A ${terminatorX} ${r} 0 0 ${sweepTerm} ${cx} ${cy - r}" fill="rgba(0,0,0,0.85)" />`;
      } else {
        // Shadow on the RIGHT side
        const sweepEdge = 1;
        const sweepTerm = bulgeRight ? 1 : 0;
        shadowPath = `<path d="M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx} ${cy + r} A ${terminatorX} ${r} 0 0 ${sweepTerm} ${cx} ${cy - r}" fill="rgba(0,0,0,0.85)" />`;
      }
    }

    return `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%;">
      <defs>
        <radialGradient id="moonGrad" cx="40%" cy="35%">
          <stop offset="0%" stop-color="#f5f3ce" />
          <stop offset="100%" stop-color="#d4d0a0" />
        </radialGradient>
        <clipPath id="moonClip">
          <circle cx="${cx}" cy="${cy}" r="${r}" />
        </clipPath>
      </defs>
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="url(#moonGrad)" />
      <g clip-path="url(#moonClip)">${shadowPath}</g>
    </svg>`;
  }

  // ── Tile construction ────────────────────────────────────────────────

  function buildTileHTML(tile) {
    const safeId = escapeHTML(tile.id);
    return `
      <button class="tile__edit" data-tile-id="${safeId}" title="Edit tile">
        <i class="mdi mdi-pencil"></i>
      </button>
      <button class="tile__remove" data-tile-id="${safeId}" title="Remove tile">
        <i class="mdi mdi-close"></i>
      </button>
      <div class="moon-tile">
        <div class="moon-visual"></div>
        <div class="moon-info">
          <div class="moon-phase-name">Loading…</div>
          <div class="moon-illumination"></div>
          <div class="moon-details">
            <div class="moon-detail-row"><span class="moon-detail-label">Moon Age</span><span class="moon-detail-value moon-age-value"></span></div>
            <div class="moon-detail-row"><span class="moon-detail-label">Moonrise</span><span class="moon-detail-value moon-rise-value"></span><span class="moon-detail-relative moon-rise-rel"></span></div>
            <div class="moon-detail-row"><span class="moon-detail-label">Moonset</span><span class="moon-detail-value moon-set-value"></span><span class="moon-detail-relative moon-set-rel"></span></div>
            <div class="moon-detail-row"><span class="moon-detail-label">Transit</span><span class="moon-detail-value moon-transit-value"></span><span class="moon-detail-relative moon-transit-rel"></span></div>
          </div>
        </div>
      </div>
    `;
  }

  // ── Data rendering ───────────────────────────────────────────────────

  function renderData(contentEl, data) {
    const visual = contentEl.querySelector(".moon-visual");
    if (visual) {
      visual.innerHTML = buildMoonSVG(data.fraction, data.phase);
    }

    const phaseName = contentEl.querySelector(".moon-phase-name");
    if (phaseName) phaseName.textContent = data.phase;

    const illum = contentEl.querySelector(".moon-illumination");
    if (illum) illum.textContent = data.illumination + "% illuminated";

    const ageVal = contentEl.querySelector(".moon-age-value");
    if (ageVal) ageVal.textContent = data.age + " days";

    const riseVal = contentEl.querySelector(".moon-rise-value");
    if (riseVal) riseVal.textContent = data.moonrise || "--:--";
    const riseRel = contentEl.querySelector(".moon-rise-rel");
    if (riseRel) riseRel.textContent = data.moonrise_relative ? "(" + data.moonrise_relative + ")" : "";

    const setVal = contentEl.querySelector(".moon-set-value");
    if (setVal) setVal.textContent = data.moonset || "--:--";
    const setRel = contentEl.querySelector(".moon-set-rel");
    if (setRel) setRel.textContent = data.moonset_relative ? "(" + data.moonset_relative + ")" : "";

    const transitVal = contentEl.querySelector(".moon-transit-value");
    if (transitVal) transitVal.textContent = data.moon_transit || "--:--";
    const transitRel = contentEl.querySelector(".moon-transit-rel");
    if (transitRel) transitRel.textContent = data.moon_transit_relative ? "(" + data.moon_transit_relative + ")" : "";
  }

  // ── Fetch and refresh ────────────────────────────────────────────────

  async function refreshTile(gridItem) {
    const zip = gridItem.dataset.zipCode;
    const country = gridItem.dataset.countryCode;
    const contentEl = gridItem.querySelector(".grid-stack-item-content");

    const params = new URLSearchParams({ zip_code: zip, country_code: country });
    try {
      const res = await fetch(`/api/moon?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      renderData(contentEl, data);
    } catch (err) {
      console.error("Moon fetch failed:", err);
      const phaseName = contentEl.querySelector(".moon-phase-name");
      if (phaseName) phaseName.textContent = "Failed to load";
    }
  }

  function refreshAllTiles() {
    for (const el of document.querySelectorAll(".grid-stack-item[data-tile-type='moon']")) {
      refreshTile(el);
    }
  }

  function startRefreshTimer() {
    setInterval(refreshAllTiles, REFRESH_INTERVAL);
  }

  // ── Tile creation ────────────────────────────────────────────────────

  function addMoonTileToGrid(tile, grid) {
    const el = document.createElement("div");
    el.className = "tile--moon";
    el.dataset.tileType    = "moon";
    el.dataset.tileId      = tile.id;
    el.dataset.label       = tile.label || "Moon";
    el.dataset.zipCode     = tile.zip_code;
    el.dataset.countryCode = tile.country_code || "US";

    const content = document.createElement("div");
    content.className = "grid-stack-item-content";
    content.innerHTML = buildTileHTML(tile);
    el.appendChild(content);

    el.setAttribute("gs-x", tile.x);
    el.setAttribute("gs-y", tile.y);
    el.setAttribute("gs-w", tile.w);
    el.setAttribute("gs-h", tile.h);
    grid.addWidget(el);
    refreshTile(el);
  }

  // ── Modal wiring ─────────────────────────────────────────────────────

  function populateForEdit(tileEl) {
    document.getElementById("moon-label").value   = tileEl.dataset.label || "";
    document.getElementById("moon-zip").value     = tileEl.dataset.zipCode || "";
    document.getElementById("moon-country").value = tileEl.dataset.countryCode || "US";
  }

  function initModal() {
    const moonForm  = document.getElementById("add-moon-form");
    const cancelBtn = document.getElementById("btn-cancel-moon");

    moonForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const label        = document.getElementById("moon-label").value.trim() || "Moon";
      const zip_code     = document.getElementById("moon-zip").value.trim();
      const country_code = (document.getElementById("moon-country").value.trim() || "US").toUpperCase();

      if (!zip_code) return;

      const editEl = DashboardApp.getEditingTile();
      if (editEl) {
        editEl.dataset.label       = label;
        editEl.dataset.zipCode     = zip_code;
        editEl.dataset.countryCode = country_code;
        refreshTile(editEl);
        DashboardApp.closeAddModal();
        return;
      }

      const tile = {
        id:           "tile_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
        tile_type:    "moon",
        label,
        zip_code,
        country_code,
        x: 0, y: 0, w: 2, h: 2,
      };
      addMoonTileToGrid(tile, DashboardApp.getGrid());
      DashboardApp.closeAddModal();
    });

    if (cancelBtn) {
      cancelBtn.addEventListener("click", () => DashboardApp.closeAddModal());
    }
  }

  // ── Public API ───────────────────────────────────────────────────────
  return { addMoonTileToGrid, populateForEdit, initModal, startRefreshTimer, refreshTile };
})();
