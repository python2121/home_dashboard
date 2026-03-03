/**
 * Home Dashboard — Main application.
 *
 * Manages the GridStack tile grid, edit mode, Home Assistant entity state
 * polling, layout persistence, and brightness control.
 *
 * Scene tile logic is delegated to SceneTiles (scene.js).
 * Weather tile logic is delegated to WeatherTiles (weather.js).
 */

"use strict";

const DashboardApp = (() => {
  // ── State ──────────────────────────────────────────────────────────
  let grid = null;
  let editing = false;
  let entityStates = {};      // entity_id → {state, attributes, …}
  let pollTimer = null;
  let brightnessTimer = null;
  let editingTileEl = null;   // null = add mode, DOM element = edit mode
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

  function uid() {
    return "tile_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  }

  function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function sanitizeIconClass(icon) {
    return /^mdi-[a-z0-9-]+$/.test(icon) ? icon : "mdi-toggle-switch";
  }

  function defaultIcon(entityId) {
    const domain = entityId.split(".")[0];
    const map = {
      light:        "mdi-lightbulb",
      switch:       "mdi-toggle-switch",
      fan:          "mdi-fan",
      cover:        "mdi-blinds",
      lock:         "mdi-lock",
      climate:      "mdi-thermostat",
      media_player: "mdi-speaker",
    };
    return map[domain] || "mdi-toggle-switch";
  }

  function domainOf(entityId) {
    return entityId.split(".")[0];
  }

  function isOn(entityId) {
    const s = entityStates[entityId];
    return s && s.state === "on";
  }

  // ── Tile HTML builders ─────────────────────────────────────────────

  /** Build inner HTML for an entity tile. Includes a brightness slider for lights. */
  function tileInnerHTML(tile) {
    const safeIcon  = sanitizeIconClass(tile.icon);
    const safeLabel = escapeHTML(tile.label);
    const safeId    = escapeHTML(tile.id);
    const safeEid   = escapeHTML(tile.entity_id);

    const sliderHTML = tile.domain === "light" ? `
      <input type="range" class="tile__brightness"
             min="1" max="255"
             value="${entityStates[tile.entity_id]?.attributes?.brightness ?? 255}"
             data-entity-id="${safeEid}" />
    ` : "";

    return `
      <button class="tile__edit" data-tile-id="${safeId}" title="Edit tile">
        <i class="mdi mdi-pencil"></i>
      </button>
      <button class="tile__remove" data-tile-id="${safeId}" title="Remove tile">
        <i class="mdi mdi-close"></i>
      </button>
      <i class="mdi ${safeIcon} tile__icon"></i>
      <span class="tile__label">${safeLabel}</span>
      ${sliderHTML}
    `;
  }

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

  function serializeLayout() {
    const tiles = [];
    for (const el of document.querySelectorAll(".grid-stack-item")) {
      const d = el.dataset;
      const tileType = d.tileType || "entity";
      const base = {
        id:        d.tileId,
        tile_type: tileType,
        x: parseInt(el.getAttribute("gs-x")) || 0,
        y: parseInt(el.getAttribute("gs-y")) || 0,
        w: parseInt(el.getAttribute("gs-w")) || 2,
        h: parseInt(el.getAttribute("gs-h")) || 2,
      };

      if (tileType === "weather") {
        tiles.push({
          ...base,
          label:        d.label,
          zip_code:     d.zipCode,
          country_code: d.countryCode,
          unit:         d.unit,
        });
      } else if (tileType === "scene") {
        tiles.push({
          ...base,
          label:   d.label,
          icon:    d.icon,
          members: JSON.parse(d.members || "[]"),
        });
      } else {
        tiles.push({
          ...base,
          entity_id: d.entityId,
          label:     d.label,
          icon:      d.icon,
          domain:    d.domain,
        });
      }
    }
    return { columns: 12, tiles };
  }

  function addTileToGrid(tile) {
    if (tile.tile_type === "weather") {
      WeatherTiles.addWeatherTileToGrid(tile, grid);
      return;
    }
    if (tile.tile_type === "scene") {
      SceneTiles.addSceneTileToGrid(tile, grid, entityStates);
      return;
    }

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

  function renderLayout(layout) {
    grid.removeAll(false);
    for (const tile of layout.tiles) {
      addTileToGrid(tile);
    }
    if (!editing) {
      grid.setStatic(true);
    }
  }

  function refreshTileStates() {
    for (const el of document.querySelectorAll(".grid-stack-item")) {
      const type = el.dataset.tileType || "entity";
      if (type === "weather") continue;
      if (type === "scene") {
        SceneTiles.updateSceneState(el, entityStates);
        continue;
      }
      // Entity tile — update on/off class and brightness slider
      applyTileState(el, el.dataset.entityId);
      const slider = el.querySelector(".tile__brightness");
      if (slider) {
        const brightness = entityStates[el.dataset.entityId]?.attributes?.brightness;
        if (brightness !== undefined) slider.value = brightness;
      }
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

    try {
      await saveLayout(serializeLayout());
    } catch (err) {
      console.error("Failed to save layout:", err);
    }
  }

  // ── Tile click / brightness handling ──────────────────────────────

  function handleTileClick(e) {
    // Remove button works in both modes
    const removeBtn = e.target.closest(".tile__remove");
    if (removeBtn) {
      const tileId = removeBtn.dataset.tileId;
      const item = document.querySelector(`.grid-stack-item[data-tile-id="${tileId}"]`);
      if (item) grid.removeWidget(item);
      return;
    }

    // Edit button — opens modal in edit mode
    const editBtn = e.target.closest(".tile__edit");
    if (editBtn) {
      const tileId = editBtn.dataset.tileId;
      const item = document.querySelector(`.grid-stack-item[data-tile-id="${tileId}"]`);
      if (item) openEditModal(item);
      return;
    }

    // Brightness slider — handle separately, don't toggle
    if (e.target.classList.contains("tile__brightness")) return;

    if (editing) return;

    const item = e.target.closest(".grid-stack-item");
    if (!item) return;

    const type = item.dataset.tileType || "entity";

    if (type === "weather") return;   // display-only

    if (type === "scene") {
      SceneTiles.handleSceneToggle(item, entityStates);
      return;
    }

    // Entity tile toggle
    const entityId = item.dataset.entityId;
    if (!entityId) return;

    const wasOn = isOn(entityId);
    if (entityStates[entityId]) entityStates[entityId].state = wasOn ? "off" : "on";
    applyTileState(item, entityId);

    toggleEntity(entityId).catch((err) => {
      console.error("Toggle failed:", err);
      if (entityStates[entityId]) entityStates[entityId].state = wasOn ? "on" : "off";
      applyTileState(item, entityId);
    });
  }

  /** Debounced brightness slider handler — only fires when the light is already on. */
  function handleBrightnessInput(e) {
    if (!e.target.classList.contains("tile__brightness")) return;

    const entityId = e.target.dataset.entityId;

    // Don't touch a light that is off — slider is hidden via CSS but guard here too
    if (!entityStates[entityId] || entityStates[entityId].state !== "on") return;

    const brightness = parseInt(e.target.value, 10);
    clearTimeout(brightnessTimer);
    brightnessTimer = setTimeout(() => {
      api("POST", `/api/ha/services/light/turn_on`, {
        entity_id: entityId,
        extra: { brightness },
      }).catch((err) => console.error("Brightness set failed:", err));
    }, 150);
  }

  // ── Add-tile modal ─────────────────────────────────────────────────

  function activateTab(tabName) {
    const tabs = document.querySelectorAll(".modal__tab");
    tabs.forEach((t) => t.classList.toggle("modal__tab--active", t.dataset.tab === tabName));
    document.getElementById("entity-form-section").classList.toggle("section--hidden", tabName !== "entity");
    document.getElementById("scene-form-section").classList.toggle("section--hidden", tabName !== "scene");
    document.getElementById("weather-form-section").classList.toggle("section--hidden", tabName !== "weather");
  }

  function openAddModal() {
    activateTab("entity");
    modal.classList.remove("modal--hidden");
    populateEntitySelect();
  }

  function openEditModal(tileEl) {
    editingTileEl = tileEl;
    const type = tileEl.dataset.tileType || "entity";

    // Hide tab bar and change heading
    document.querySelector(".modal__tabs").style.display = "none";
    document.querySelector(".modal__content h2").textContent = "Edit Tile";

    if (type === "entity") {
      activateTab("entity");
      populateEntityForEdit(tileEl);
      // Change submit button text
      addForm.querySelector("button[type='submit']").textContent = "Save";
    } else if (type === "scene") {
      activateTab("scene");
      SceneTiles.populateForEdit(tileEl);
      document.getElementById("btn-scene-confirm").textContent = "Save";
    } else if (type === "weather") {
      activateTab("weather");
      populateWeatherForEdit(tileEl);
      document.querySelector("#add-weather-form button[type='submit']").textContent = "Save";
    }

    modal.classList.remove("modal--hidden");
  }

  function populateEntityForEdit(tileEl) {
    populateEntitySelect();
    const select    = $("#tile-entity");
    const labelInput = $("#tile-label");
    const iconInput  = $("#tile-icon");

    select.value = tileEl.dataset.entityId;
    labelInput.value = tileEl.dataset.label;
    labelInput.dataset.autoFilled = "false";
    iconInput.value = tileEl.dataset.icon;
  }

  function populateWeatherForEdit(tileEl) {
    document.getElementById("weather-label").value   = tileEl.dataset.label || "";
    document.getElementById("weather-zip").value     = tileEl.dataset.zipCode || "";
    document.getElementById("weather-country").value = tileEl.dataset.countryCode || "US";
    document.getElementById("weather-unit").value    = tileEl.dataset.unit || "fahrenheit";
  }

  function closeAddModal() {
    modal.classList.add("modal--hidden");
    addForm.reset();
    SceneTiles.resetModal();
    const wForm = document.getElementById("add-weather-form");
    if (wForm) wForm.reset();

    // Restore modal to add mode
    editingTileEl = null;
    document.querySelector(".modal__tabs").style.display = "";
    document.querySelector(".modal__content h2").textContent = "Add Tile";
    addForm.querySelector("button[type='submit']").textContent = "Add";
    document.getElementById("btn-scene-confirm").textContent = "Confirm";
    const weatherSubmit = document.querySelector("#add-weather-form button[type='submit']");
    if (weatherSubmit) weatherSubmit.textContent = "Add";
  }

  function populateEntitySelect() {
    const select = $("#tile-entity");
    select.removeEventListener("change", updateAddFormDefaults);

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

    if (editingTileEl) {
      // Update tile in-place
      editingTileEl.dataset.entityId = entityId;
      editingTileEl.dataset.label    = label;
      editingTileEl.dataset.icon     = icon;
      editingTileEl.dataset.domain   = domainOf(entityId);

      const tile = {
        id:        editingTileEl.dataset.tileId,
        entity_id: entityId,
        label,
        icon,
        domain:    domainOf(entityId),
      };
      const content = editingTileEl.querySelector(".grid-stack-item-content");
      content.innerHTML = tileInnerHTML(tile);
      applyTileState(editingTileEl, entityId);
      closeAddModal();
      return;
    }

    const tile = {
      id:        uid(),
      tile_type: "entity",
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
    grid = GridStack.init({
      column: 12,
      cellHeight: 100,
      margin: 6,
      animate: true,
      float: false,
      disableOneColumnMode: true,
      removable: false,
      staticGrid: true,
    });

    dashboard.addEventListener("click", handleTileClick);
    dashboard.addEventListener("input", handleBrightnessInput);

    btnEdit.addEventListener("click", enterEditMode);
    btnDone.addEventListener("click", exitEditMode);

    btnAddTile.addEventListener("click", openAddModal);
    $("#btn-cancel-tile").addEventListener("click", closeAddModal);
    $(".modal__backdrop").addEventListener("click", closeAddModal);
    addForm.addEventListener("submit", handleAddTileSubmit);

    $("#tile-label").addEventListener("input", function () {
      this.dataset.autoFilled = "false";
    });

    // Wire scene and weather modules; scene needs a live reference to entityStates
    SceneTiles.initModal(() => entityStates);
    WeatherTiles.initModal();

    try {
      setStatus("connecting");
      await fetchStates();
      setStatus("ok");
    } catch (err) {
      console.error("Initial state fetch failed:", err);
      setStatus("error");
    }

    try {
      const layout = await loadLayout();
      if (layout.tiles.length > 0) {
        renderLayout(layout);
      }
    } catch (err) {
      console.error("Failed to load layout:", err);
    }

    startPolling();
    WeatherTiles.startRefreshTimer();
  }

  // ── Public API ──────────────────────────────────────────────────────
  return { init, getGrid: () => grid, closeAddModal, openEditModal, getEditingTile: () => editingTileEl };
})();

document.addEventListener("DOMContentLoaded", DashboardApp.init);
