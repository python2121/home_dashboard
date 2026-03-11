/**
 * Home Dashboard — Clock tile module.
 *
 * Displays current time, date, and optionally day-of-week.
 * Pure frontend — no backend route needed.
 */

"use strict";

const ClockTiles = (() => {
  let clockInterval = null;

  // ── Helpers ──────────────────────────────────────────────────────────

  function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
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
      <div class="clock-tile">
        <div class="clock-time">--:--</div>
        <div class="clock-date"></div>
      </div>
    `;
  }

  // ── Time rendering ───────────────────────────────────────────────────

  function renderTime(gridItem) {
    const is24h = gridItem.dataset.format24h === "true";
    const showSec = gridItem.dataset.showSeconds === "true";

    const now = new Date();

    const timeOpts = {
      hour: "numeric",
      minute: "2-digit",
      hour12: !is24h,
    };
    if (showSec) timeOpts.second = "2-digit";

    const timeStr = now.toLocaleTimeString(undefined, timeOpts);

    const dateOpts = { weekday: "long", month: "long", day: "numeric" };
    const dateStr = now.toLocaleDateString(undefined, dateOpts);

    const timeEl = gridItem.querySelector(".clock-time");
    if (timeEl) timeEl.textContent = timeStr;

    const dateEl = gridItem.querySelector(".clock-date");
    if (dateEl) dateEl.textContent = dateStr;
  }

  function renderAllClocks() {
    for (const el of document.querySelectorAll('.grid-stack-item[data-tile-type="clock"]')) {
      renderTime(el);
    }
  }

  function startClock() {
    if (clockInterval) return;
    clockInterval = setInterval(renderAllClocks, 1000);
  }

  // ── Tile creation ────────────────────────────────────────────────────

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

    el.setAttribute("gs-x", tile.x);
    el.setAttribute("gs-y", tile.y);
    el.setAttribute("gs-w", tile.w);
    el.setAttribute("gs-h", tile.h);
    grid.addWidget(el);
    renderTime(el);
  }

  // ── Modal wiring ─────────────────────────────────────────────────────

  function populateForEdit(tileEl) {
    document.getElementById("clock-label").value     = tileEl.dataset.label || "";
    document.getElementById("clock-24h").value        = tileEl.dataset.format24h === "true" ? "true" : "false";
    document.getElementById("clock-seconds").checked = tileEl.dataset.showSeconds === "true";
  }

  function initModal() {
    const clockForm = document.getElementById("add-clock-form");
    const cancelBtn = document.getElementById("btn-cancel-clock");

    clockForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const label       = document.getElementById("clock-label").value.trim() || "Clock";
      const format_24h  = document.getElementById("clock-24h").value === "true";
      const show_seconds = document.getElementById("clock-seconds").checked;

      const editEl = DashboardApp.getEditingTile();
      if (editEl) {
        editEl.dataset.label       = label;
        editEl.dataset.format24h   = format_24h ? "true" : "false";
        editEl.dataset.showSeconds = show_seconds ? "true" : "false";
        renderTime(editEl);
        DashboardApp.closeAddModal();
        return;
      }

      const tile = {
        id:           "tile_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
        tile_type:    "clock",
        label,
        format_24h,
        show_seconds,
        x: 0, y: 0, w: 2, h: 2,
      };
      addClockTileToGrid(tile, DashboardApp.getGrid());
      DashboardApp.closeAddModal();
    });

    if (cancelBtn) {
      cancelBtn.addEventListener("click", () => DashboardApp.closeAddModal());
    }
  }

  // ── Public API ───────────────────────────────────────────────────────
  return { addClockTileToGrid, populateForEdit, initModal, startClock };
})();
