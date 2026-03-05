/**
 * Home Dashboard — Forecast chart tile module.
 *
 * Handles forecast_chart tiles: either a minute-by-minute rain probability
 * bar chart or a 6-hour temperature line chart with sunrise/sunset markers.
 * Data comes from /api/weather/chart which proxies Pirate Weather (rain)
 * and Open-Meteo (temperature).
 *
 * Designed for a thin horizontal strip (h=1, w=4+).
 * SVG viewBox "0 0 200 40" matches the ~5:1 aspect ratio of a 4-wide 1-tall tile,
 * so preserveAspectRatio="none" produces near-uniform scaling with no text distortion.
 */

"use strict";

const ForecastChartTiles = (() => {
  const REFRESH_INTERVAL = 5 * 60 * 1000; // 5 minutes
  const SVG_NS = "http://www.w3.org/2000/svg";

  // ── Helpers ──────────────────────────────────────────────────────────

  function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  /** Parse an ISO datetime string like "2024-06-01T14:00" to epoch minutes. */
  function isoToMinutes(iso) {
    const [datePart, timePart] = iso.split("T");
    const [y, mo, d] = datePart.split("-").map(Number);
    const [h, m] = (timePart || "0:0").split(":").map(Number);
    return new Date(y, mo - 1, d, h, m || 0).getTime() / 60000;
  }

  /** Format an ISO datetime hour as "2p", "10a", etc. */
  function isoToShortTime(iso) {
    const timePart = iso.split("T")[1] || "0:00";
    const h = parseInt(timePart.split(":")[0], 10);
    return `${h % 12 || 12}${h < 12 ? "a" : "p"}`;
  }

  function svgEl(tag, attrs) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
    return el;
  }

  function svgText(x, y, text, opts = {}) {
    const t = svgEl("text", {
      x, y,
      "font-size":   opts.size    || 4,
      "fill":        opts.fill    || "#8892a4",
      "text-anchor": opts.anchor  || "middle",
      ...(opts.family ? { "font-family": opts.family } : {}),
    });
    t.textContent = text;
    return t;
  }

  // ── Tile construction ────────────────────────────────────────────────

  // Label is stored in data-label for serialisation / edit modal only;
  // it is NOT displayed on the tile so the chart fills the full height.
  function buildTileHTML(tile) {
    const safeId = escapeHTML(tile.id);
    return `
      <button class="tile__edit" data-tile-id="${safeId}" title="Edit tile">
        <i class="mdi mdi-pencil"></i>
      </button>
      <button class="tile__remove" data-tile-id="${safeId}" title="Remove tile">
        <i class="mdi mdi-close"></i>
      </button>
      <div class="chart-tile">
        <div class="chart-canvas"><span class="chart-loading">Loading…</span></div>
      </div>
    `;
  }

  // ── SVG chart renderers ──────────────────────────────────────────────
  //
  // Both charts share viewBox "0 0 200 40".  Layout zones:
  //   y  0–4   : top labels (unit, mode tag)
  //   y  5–31  : data area (bars / line)
  //   y 32–33  : baseline
  //   y 34–40  : bottom time labels

  function makeSVG() {
    const svg = svgEl("svg", { viewBox: "0 0 200 40", preserveAspectRatio: "none" });
    svg.style.display = "block";
    return svg;
  }

  /**
   * 60-bar precipitation probability chart.
   * Bar i: x = i*(200/60), width = 200/60 − 0.4, height = prob*27, baseline y=31.
   */
  function renderRainChart(canvasEl, data) {
    const svg  = makeSVG();
    const barW = 200 / 60;

    for (const bar of data.bars) {
      const prob = bar.prob;
      const h = Math.max(0.5, prob * 27);
      svg.appendChild(svgEl("rect", {
        x:      (bar.min * barW).toFixed(2),
        y:      (31 - h).toFixed(2),
        width:  (barW - 0.4).toFixed(2),
        height: h.toFixed(2),
        fill:   prob > 0.5 ? "#1565c0" : "#4fc3f7",
      }));
    }

    // Baseline
    svg.appendChild(svgEl("line", {
      x1: 0, y1: 31.5, x2: 200, y2: 31.5,
      stroke: "#8892a4", "stroke-width": 0.3,
    }));

    // X-axis labels
    svg.appendChild(svgText(1,   38, "now", { anchor: "start" }));
    svg.appendChild(svgText(100, 38, "30m", { anchor: "middle" }));
    svg.appendChild(svgText(199, 38, "60m", { anchor: "end" }));

    // Mode tag
    svg.appendChild(svgText(199, 5, "RAIN", { anchor: "end", size: 3.5 }));

    canvasEl.innerHTML = "";
    canvasEl.appendChild(svg);
  }

  /**
   * 6-hour temperature line chart with sunrise/sunset markers.
   * Points at x = 8, 45, 82, 118, 155, 192; y range 6–31.
   */
  function renderTempChart(canvasEl, data) {
    const points = data.points;
    if (!points || points.length === 0) {
      canvasEl.innerHTML = '<span class="chart-loading">No data</span>';
      return;
    }

    const svg = makeSVG();
    const n   = points.length;

    // Evenly space x: 8 to 192 (184 unit span, n-1 gaps)
    const xFor = (i) => (n > 1 ? 8 + i * (184 / (n - 1)) : 100);

    const temps  = points.map((p) => p.temp);
    const tMin   = Math.min(...temps);
    const tMax   = Math.max(...temps);
    const tRange = tMax - tMin || 1;
    const yFor   = (temp) => 31 - ((temp - tMin) / tRange) * 25; // 6–31

    // Sunrise / sunset dashed verticals
    if (n >= 2) {
      const startMin = isoToMinutes(points[0].iso);
      const endMin   = isoToMinutes(points[n - 1].iso);
      const xSpan    = xFor(n - 1) - xFor(0);
      for (const { iso, color } of [
        { iso: data.sunrise_iso, color: "#ffd369" },
        { iso: data.sunset_iso,  color: "#ff9800" },
      ]) {
        if (!iso) continue;
        const m = isoToMinutes(iso);
        if (m <= startMin || m >= endMin) continue;
        const x = xFor(0) + ((m - startMin) / (endMin - startMin)) * xSpan;
        svg.appendChild(svgEl("line", {
          x1: x.toFixed(1), y1: 5,
          x2: x.toFixed(1), y2: 31,
          stroke: color, "stroke-width": 0.8, "stroke-dasharray": "2,2", opacity: 0.7,
        }));
      }
    }

    // Baseline
    svg.appendChild(svgEl("line", {
      x1: 0, y1: 31.5, x2: 200, y2: 31.5,
      stroke: "#8892a4", "stroke-width": 0.3,
    }));

    // Polyline
    const ptStr = points.map((p, i) => `${xFor(i).toFixed(1)},${yFor(p.temp).toFixed(1)}`).join(" ");
    svg.appendChild(svgEl("polyline", {
      points: ptStr,
      fill: "none", stroke: "#4fc3f7",
      "stroke-width": 1.5, "stroke-linejoin": "round", "stroke-linecap": "round",
    }));

    // Dots, temp labels, time labels
    for (let i = 0; i < n; i++) {
      const x = xFor(i);
      const y = yFor(points[i].temp);

      svg.appendChild(svgEl("circle", {
        cx: x.toFixed(1), cy: y.toFixed(1), r: 1.5, fill: "#4fc3f7",
      }));
      svg.appendChild(svgText(x.toFixed(1), Math.max(4, y - 3).toFixed(1),
        String(points[i].temp), { size: 4.5, fill: "#eaeaea" }));
      svg.appendChild(svgText(x.toFixed(1), 38,
        isoToShortTime(points[i].iso)));
    }

    // Unit tag (top-left)
    svg.appendChild(svgText(1, 5, data.unit || "", { anchor: "start", size: 3.5 }));

    canvasEl.innerHTML = "";
    canvasEl.appendChild(svg);
  }

  function renderData(gridItem, data) {
    const canvasEl = gridItem.querySelector(".chart-canvas");
    if (!canvasEl) return;
    if (data.mode === "rain") {
      renderRainChart(canvasEl, data);
    } else {
      renderTempChart(canvasEl, data);
    }
  }

  // ── Fetch and refresh ────────────────────────────────────────────────

  async function refreshTile(gridItem) {
    const zip     = gridItem.dataset.zipCode;
    const country = gridItem.dataset.countryCode;
    const unit    = gridItem.dataset.unit;

    const params = new URLSearchParams({ zip_code: zip, country_code: country, unit });
    try {
      const res = await fetch(`/api/weather/chart?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      renderData(gridItem, data);
    } catch (err) {
      console.error("Chart fetch failed:", err);
      const canvasEl = gridItem.querySelector(".chart-canvas");
      if (canvasEl) canvasEl.innerHTML = '<span class="chart-loading">Failed to load</span>';
    }
  }

  function refreshAllTiles() {
    for (const el of document.querySelectorAll('.grid-stack-item[data-tile-type="forecast_chart"]')) {
      refreshTile(el);
    }
  }

  function startRefreshTimer() {
    setInterval(refreshAllTiles, REFRESH_INTERVAL);
  }

  // ── Tile creation ────────────────────────────────────────────────────

  function addForecastChartTileToGrid(tile, grid) {
    const el = document.createElement("div");
    el.className = "tile--chart";
    el.dataset.tileType    = "forecast_chart";
    el.dataset.tileId      = tile.id;
    el.dataset.label       = tile.label || "Weather Chart";
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

  function populateForEdit(tileEl) {
    document.getElementById("chart-label").value   = tileEl.dataset.label || "";
    document.getElementById("chart-zip").value     = tileEl.dataset.zipCode || "";
    document.getElementById("chart-country").value = tileEl.dataset.countryCode || "US";
    document.getElementById("chart-unit").value    = tileEl.dataset.unit || "fahrenheit";
  }

  function initModal() {
    const chartForm = document.getElementById("add-chart-form");
    const cancelBtn = document.getElementById("btn-cancel-chart");

    chartForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const label        = document.getElementById("chart-label").value.trim() || "Weather Chart";
      const zip_code     = document.getElementById("chart-zip").value.trim();
      const country_code = (document.getElementById("chart-country").value.trim() || "US").toUpperCase();
      const unit         = document.getElementById("chart-unit").value;

      if (!zip_code) return;

      const editEl = DashboardApp.getEditingTile();
      if (editEl) {
        editEl.dataset.label       = label;
        editEl.dataset.zipCode     = zip_code;
        editEl.dataset.countryCode = country_code;
        editEl.dataset.unit        = unit;
        refreshTile(editEl);
        DashboardApp.closeAddModal();
        return;
      }

      const tile = {
        id:           "tile_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
        tile_type:    "forecast_chart",
        label,
        zip_code,
        country_code,
        unit,
        x: 0, y: 0, w: 4, h: 1,
      };
      addForecastChartTileToGrid(tile, DashboardApp.getGrid());
      DashboardApp.closeAddModal();
    });

    if (cancelBtn) {
      cancelBtn.addEventListener("click", () => DashboardApp.closeAddModal());
    }
  }

  // ── Public API ───────────────────────────────────────────────────────
  return { addForecastChartTileToGrid, populateForEdit, initModal, startRefreshTimer };
})();
