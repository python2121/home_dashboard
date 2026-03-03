/**
 * Home Dashboard — Main application.
 *
 * Manages the GridStack tile grid, edit mode, Home Assistant entity state
 * polling, and layout persistence.
 */

"use strict";

const DashboardApp = (() => {
  // ── State ──────────────────────────────────────────────────────────
  let grid = null;
  let editing = false;
  let entityStates = {};      // entity_id → {state, attributes, …}
  let pollTimer = null;
  const POLL_INTERVAL = 5000; // ms

  // ── DOM refs ───────────────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const toolbar    = $("#toolbar");
  const dashboard  = $("#dashboard");
  const btnEdit    = $("#btn-edit");
  const btnDone    = $("#btn-done");
  const btnAddTile = $("#btn-add-tile");
  const modal      = $("#add-tile-modal");
  const addForm    = $("#add-tile-form");
  const statusDot  = $("#status-indicator");

  // ── Helpers ────────────────────────────────────────────────────────

  /** Generate a short unique id for new tiles. */
  function uid() {
    return "tile_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  }

  /** Escape HTML to prevent XSS when inserting user-provided text. */
  function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  /** Validate an MDI icon class name (letters, numbers, hyphens only). */
  function sanitizeIconClass(icon) {
    return /^mdi-[a-z0-9-]+$/.test(icon) ? icon : "mdi-toggle-switch";
  }

  /** Map entity_id prefix to a sensible default MDI icon. */
  function defaultIcon(entityId) {
    const domain = entityId.split(".")[0];
    const map = {
      light:  "mdi-lightbulb",
      switch: "mdi-toggle-switch",
      fan:    "mdi-fan",
      cover:  "mdi-blinds",
      lock:   "mdi-lock",
      climate:"mdi-thermostat",
      media_player: "mdi-speaker",
    };
    return map[domain] || "mdi-toggle-switch";
  }

  /** Derive HA domain from entity_id. */
  function domainOf(entityId) {
    return entityId.split(".")[0];
  }

  /** Is the entity currently "on"? */
  function isOn(entityId) {
    const s = entityStates[entityId];
    return s && s.state === "on";
  }

  /** Build the inner HTML for a tile (all user text is escaped). */
  function tileInnerHTML(tile) {
    const safeIcon = sanitizeIconClass(tile.icon);
    const safeLabel = escapeHTML(tile.label);
    const safeId = escapeHTML(tile.id);
    return `
      <button class="tile__remove" data-tile-id="${safeId}" title="Remove tile">
        <i class="mdi mdi-close"></i>
      </button>
      <i class="mdi ${safeIcon} tile__icon"></i>
      <span class="tile__label">${safeLabel}</span>
    `;
  }

  /** Set the on/off class on a grid-stack-item element. */
  function applyTileState(el, entityId) {
    const on = isOn(entityId);
    el.classList.toggle("tile--on", on);
    el.classList.toggle("tile--off", !on);
  }

  // ── API calls ──────────────────────────────────────────────────────

  async function api(method, path, body) {
    const opts = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status}: ${text}`);
    }
    return res.json();
  }

  async function fetchStates() {
    const states = await api("GET", "/api/ha/states");
    entityStates = {};
    for (const s of states) {
      entityStates[s.entity_id] = s;
    }
    return entityStates;
  }

  async function toggleEntity(entityId) {
    return api("POST", `/api/ha/toggle/${encodeURIComponent(entityId)}`);
  }

  async function loadLayout() {
    return api("GET", "/api/layout");
  }

  async function saveLayout(layout) {
    return api("PUT", "/api/layout", layout);
  }

  // ── Status indicator ───────────────────────────────────────────────

  function setStatus(state) {
    statusDot.className = "status-indicator status-indicator--" + state;
  }

  // ── Grid / tile management ─────────────────────────────────────────

  /** Serialize the current grid to a Layout object. */
  function serializeLayout() {
    const tiles = [];
    for (const el of document.querySelectorAll(".grid-stack-item")) {
      const d = el.dataset;
      tiles.push({
        id:        d.tileId,
        entity_id: d.entityId,
        label:     d.label,
        icon:      d.icon,
        domain:    d.domain,
        x: parseInt(el.getAttribute("gs-x")) || 0,
        y: parseInt(el.getAttribute("gs-y")) || 0,
        w: parseInt(el.getAttribute("gs-w")) || 2,
        h: parseInt(el.getAttribute("gs-h")) || 2,
      });
    }
    return { columns: 12, tiles };
  }

  /** Add a single tile to the grid. */
  function addTileToGrid(tile) {
    const on = isOn(tile.entity_id);
    const el = document.createElement("div");
    el.className = on ? "tile--on" : "tile--off";
    el.dataset.tileId   = tile.id;
    el.dataset.entityId = tile.entity_id;
    el.dataset.label    = tile.label;
    el.dataset.icon     = tile.icon;
    el.dataset.domain   = tile.domain;

    const content = document.createElement("div");
    content.className = "grid-stack-item-content";
    content.innerHTML = tileInnerHTML(tile);
    el.appendChild(content);

    grid.addWidget(el, { x: tile.x, y: tile.y, w: tile.w, h: tile.h });
  }

  /** Rebuild the entire grid from a Layout. */
  function renderLayout(layout) {
    grid.removeAll(false);
    for (const tile of layout.tiles) {
      addTileToGrid(tile);
    }
    if (!editing) {
      grid.setStatic(true);
    }
  }

  /** Refresh on/off state on every tile without rebuilding the grid. */
  function refreshTileStates() {
    for (const el of document.querySelectorAll(".grid-stack-item")) {
      applyTileState(el, el.dataset.entityId);
    }
  }

  // ── Edit mode ──────────────────────────────────────────────────────

  function enterEditMode() {
    editing = true;
    toolbar.classList.remove("toolbar--hidden");
    dashboard.classList.add("dashboard--editing");
    btnEdit.classList.add("fab--hidden");
    grid.setStatic(false);
  }

  async function exitEditMode() {
    editing = false;
    toolbar.classList.add("toolbar--hidden");
    dashboard.classList.remove("dashboard--editing");
    btnEdit.classList.remove("fab--hidden");
    grid.setStatic(true);

    // Persist layout
    try {
      await saveLayout(serializeLayout());
    } catch (err) {
      console.error("Failed to save layout:", err);
    }
  }

  // ── Tile click handling ────────────────────────────────────────────

  function handleTileClick(e) {
    // In edit mode, don't toggle — unless they clicked the remove button
    const removeBtn = e.target.closest(".tile__remove");
    if (removeBtn) {
      const tileId = removeBtn.dataset.tileId;
      const item = document.querySelector(`.grid-stack-item[data-tile-id="${tileId}"]`);
      if (item) grid.removeWidget(item);
      return;
    }

    if (editing) return;

    const item = e.target.closest(".grid-stack-item");
    if (!item) return;

    const entityId = item.dataset.entityId;
    if (!entityId) return;

    // Optimistic UI update
    const wasOn = isOn(entityId);
    if (entityStates[entityId]) {
      entityStates[entityId].state = wasOn ? "off" : "on";
    }
    applyTileState(item, entityId);

    // Fire the toggle, revert on failure
    toggleEntity(entityId).catch((err) => {
      console.error("Toggle failed:", err);
      if (entityStates[entityId]) {
        entityStates[entityId].state = wasOn ? "on" : "off";
      }
      applyTileState(item, entityId);
    });
  }

  // ── Add-tile modal ─────────────────────────────────────────────────

  function openAddModal() {
    modal.classList.remove("modal--hidden");
    populateEntitySelect();
  }

  function closeAddModal() {
    modal.classList.add("modal--hidden");
    addForm.reset();
  }

  function populateEntitySelect() {
    const select = $("#tile-entity");
    // Remove old listener before re-adding to prevent duplicates
    select.removeEventListener("change", updateAddFormDefaults);

    // Filter to controllable domains
    const domains = new Set(["light", "switch", "fan", "cover", "lock", "climate", "media_player"]);
    const entities = Object.keys(entityStates)
      .filter((id) => domains.has(id.split(".")[0]))
      .sort();

    select.innerHTML = "";
    if (entities.length === 0) {
      select.innerHTML = '<option value="">No entities found</option>';
      return;
    }
    for (const id of entities) {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = id;
      select.appendChild(opt);
    }

    // Auto-fill label & icon from first selection
    updateAddFormDefaults();
    select.addEventListener("change", updateAddFormDefaults);
  }

  function updateAddFormDefaults() {
    const entityId = $("#tile-entity").value;
    if (!entityId) return;
    const friendly = entityStates[entityId]?.attributes?.friendly_name;
    const labelInput = $("#tile-label");
    const iconInput  = $("#tile-icon");
    if (!labelInput.value || labelInput.dataset.autoFilled === "true") {
      labelInput.value = friendly || entityId.split(".")[1].replace(/_/g, " ");
      labelInput.dataset.autoFilled = "true";
    }
    iconInput.value = defaultIcon(entityId);
  }

  function handleAddTileSubmit(e) {
    e.preventDefault();
    const entityId = $("#tile-entity").value;
    const label    = $("#tile-label").value.trim();
    const icon     = $("#tile-icon").value.trim() || defaultIcon(entityId);

    if (!entityId || !label) return;

    const tile = {
      id:        uid(),
      entity_id: entityId,
      label,
      icon,
      domain:    domainOf(entityId),
      x: 0, y: 0, w: 2, h: 2,
    };

    addTileToGrid(tile);
    closeAddModal();
  }

  // ── Polling ────────────────────────────────────────────────────────

  async function poll() {
    try {
      await fetchStates();
      refreshTileStates();
      setStatus("ok");
    } catch (err) {
      console.error("State poll failed:", err);
      setStatus("error");
    }
  }

  function startPolling() {
    pollTimer = setInterval(poll, POLL_INTERVAL);
  }

  // ── Initialisation ─────────────────────────────────────────────────

  async function init() {
    // Init GridStack
    grid = GridStack.init({
      column: 12,
      cellHeight: 100,
      margin: 6,
      animate: true,
      float: false,
      disableOneColumnMode: true,
      removable: false,
      staticGrid: true, // start locked; edit mode unlocks via setStatic()
    });

    // Event: tile click / remove
    dashboard.addEventListener("click", handleTileClick);

    // Event: edit mode
    btnEdit.addEventListener("click", enterEditMode);
    btnDone.addEventListener("click", exitEditMode);

    // Event: add-tile modal
    btnAddTile.addEventListener("click", openAddModal);
    $("#btn-cancel-tile").addEventListener("click", closeAddModal);
    $(".modal__backdrop").addEventListener("click", closeAddModal);
    addForm.addEventListener("submit", handleAddTileSubmit);

    // Clear auto-fill flag on manual label edit
    $("#tile-label").addEventListener("input", function () {
      this.dataset.autoFilled = "false";
    });

    // Load initial state
    try {
      setStatus("connecting");
      await fetchStates();
      setStatus("ok");
    } catch (err) {
      console.error("Initial state fetch failed:", err);
      setStatus("error");
    }

    // Load layout and render
    try {
      const layout = await loadLayout();
      if (layout.tiles.length > 0) {
        renderLayout(layout);
      }
    } catch (err) {
      console.error("Failed to load layout:", err);
    }

    // Start periodic state refresh (initial fetch already done above)
    startPolling();
  }

  // ── Public API (for debugging in console) ──────────────────────────
  return { init };
})();

// Boot
document.addEventListener("DOMContentLoaded", DashboardApp.init);
