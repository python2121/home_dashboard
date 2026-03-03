/**
 * Home Dashboard — Scene tile module.
 *
 * Handles scene tiles: groups of lights, each with its own target brightness.
 * Also owns the "Scene" tab in the Add Tile modal, including the two-step
 * builder flow with live HA preview on the brightness sliders.
 */

"use strict";

const SceneTiles = (() => {
  // ── Cooldown — suppress poll-driven state refresh briefly after toggle ──

  let _cooldownUntil = 0;
  const COOLDOWN_MS = 3000;

  function startCooldown() {
    _cooldownUntil = Date.now() + COOLDOWN_MS;
  }

  function isInCooldown() {
    return Date.now() < _cooldownUntil;
  }

  // ── Helpers ──────────────────────────────────────────────────────────

  function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function sanitizeIconClass(icon) {
    return /^mdi-[a-z0-9-]+$/.test(icon) ? icon : "mdi-lightbulb-group";
  }

  function brightnessPct(value) {
    return Math.round((value / 255) * 100) + "%";
  }

  function avgBrightnessPct(members) {
    if (!members.length) return "0%";
    const avg = members.reduce((sum, m) => sum + m.brightness, 0) / members.length;
    return brightnessPct(Math.round(avg));
  }

  // ── Tile construction ────────────────────────────────────────────────

  function buildTileHTML(tile) {
    const safeIcon  = sanitizeIconClass(tile.icon || "mdi-lightbulb-group");
    const safeLabel = escapeHTML(tile.label);
    const safeId    = escapeHTML(tile.id);
    const pct       = avgBrightnessPct(tile.members);

    return `
      <button class="tile__edit" data-tile-id="${safeId}" title="Edit tile">
        <i class="mdi mdi-pencil"></i>
      </button>
      <button class="tile__remove" data-tile-id="${safeId}" title="Remove tile">
        <i class="mdi mdi-close"></i>
      </button>
      <i class="mdi ${safeIcon} tile__icon"></i>
      <span class="tile__label">${safeLabel}</span>
      <span class="tile__brightness-badge">${escapeHTML(pct)}</span>
    `;
  }

  // ── State ────────────────────────────────────────────────────────────

  /**
   * A scene is "on" only when ALL members are on AND each member's
   * current brightness is within ±3 of the scene's target brightness.
   */
  function isSceneOn(el, entityStates) {
    const members = JSON.parse(el.dataset.members || "[]");
    if (members.length === 0) return false;
    return members.every((m) => {
      const st = entityStates[m.entity_id];
      if (!st || st.state !== "on") return false;
      const current = st.attributes?.brightness;
      if (current == null) return false;
      return Math.abs(current - m.brightness) <= 3;
    });
  }

  function updateSceneState(el, entityStates) {
    const on = isSceneOn(el, entityStates);
    el.classList.toggle("tile--on", on);
    el.classList.toggle("tile--off", !on);
  }

  // ── Toggle ───────────────────────────────────────────────────────────

  /** Refresh visual state of all scene tiles except the given one. */
  function refreshOtherScenes(excludeEl, entityStates) {
    document.querySelectorAll('[data-tile-type="scene"]').forEach((el) => {
      if (el !== excludeEl) updateSceneState(el, entityStates);
    });
  }

  async function handleSceneToggle(el, entityStates) {
    startCooldown();
    const members = JSON.parse(el.dataset.members || "[]");
    const wasOn   = isSceneOn(el, entityStates);
    const action  = wasOn ? "off" : "on";

    // Save previous state for rollback
    const prev = members.map((m) => {
      const st = entityStates[m.entity_id];
      return { entity_id: m.entity_id, state: st?.state, brightness: st?.attributes?.brightness };
    });

    // Optimistic update — set state AND brightness so cross-scene checks work
    el.classList.toggle("tile--on", !wasOn);
    el.classList.toggle("tile--off", wasOn);
    for (const m of members) {
      if (entityStates[m.entity_id]) {
        entityStates[m.entity_id].state = action;
        if (action === "on") {
          if (!entityStates[m.entity_id].attributes) entityStates[m.entity_id].attributes = {};
          entityStates[m.entity_id].attributes.brightness = m.brightness;
        }
      }
    }
    refreshOtherScenes(el, entityStates);

    try {
      const res = await fetch("/api/ha/scene-toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ members, action }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch (err) {
      console.error("Scene toggle failed:", err);
      // Revert optimistic update
      el.classList.toggle("tile--on", wasOn);
      el.classList.toggle("tile--off", !wasOn);
      for (const p of prev) {
        if (entityStates[p.entity_id]) {
          entityStates[p.entity_id].state = p.state;
          if (p.brightness != null) {
            if (!entityStates[p.entity_id].attributes) entityStates[p.entity_id].attributes = {};
            entityStates[p.entity_id].attributes.brightness = p.brightness;
          }
        }
      }
      refreshOtherScenes(el, entityStates);
    }
  }

  // ── Tile creation ────────────────────────────────────────────────────

  function addSceneTileToGrid(tile, grid, entityStates) {
    // Use brightness-matching logic consistent with isSceneOn
    const on = tile.members.length > 0 && tile.members.every((m) => {
      const st = entityStates[m.entity_id];
      if (!st || st.state !== "on") return false;
      const current = st.attributes?.brightness;
      if (current == null) return false;
      return Math.abs(current - m.brightness) <= 3;
    });

    const el = document.createElement("div");
    el.className = on ? "tile--on" : "tile--off";
    el.dataset.tileType = "scene";
    el.dataset.tileId   = tile.id;
    el.dataset.label    = tile.label;
    el.dataset.icon     = tile.icon || "mdi-lightbulb-group";
    el.dataset.members  = JSON.stringify(tile.members);

    const content = document.createElement("div");
    content.className = "grid-stack-item-content";
    content.innerHTML = buildTileHTML(tile);
    el.appendChild(content);

    grid.addWidget(el, { x: tile.x, y: tile.y, w: tile.w, h: tile.h });
  }

  // ── Modal wiring ─────────────────────────────────────────────────────

  let _getEntityStates = () => ({});
  let _previewTimer = null;
  let _editMembers = null; // null in add mode; map of entity_id→brightness in edit mode

  function populateSceneEntityList() {
    const entityStates = _getEntityStates();
    const select = document.getElementById("scene-entities");
    const lights = Object.keys(entityStates)
      .filter((id) => id.split(".")[0] === "light")
      .sort();

    select.innerHTML = "";
    if (lights.length === 0) {
      select.innerHTML = '<option value="" disabled>No light entities found</option>';
      return;
    }
    for (const id of lights) {
      const opt = document.createElement("option");
      opt.value = id;
      const friendly = entityStates[id]?.attributes?.friendly_name;
      opt.textContent = friendly ? `${friendly} (${id})` : id;
      select.appendChild(opt);
    }
  }

  /** Build slider rows in step 2 for the given entity IDs. */
  function buildMemberSliders(entityIds) {
    const entityStates = _getEntityStates();
    const container = document.getElementById("scene-member-list");
    container.innerHTML = "";

    for (const id of entityIds) {
      const friendly = entityStates[id]?.attributes?.friendly_name || id;
      // In edit mode, use saved brightness; otherwise use current HA state or full
      const initial = (_editMembers && _editMembers[id] !== undefined)
        ? _editMembers[id]
        : (entityStates[id]?.attributes?.brightness ?? 255);

      const row = document.createElement("div");
      row.className = "scene-member-row";
      row.dataset.entityId = id;

      const label = document.createElement("span");
      label.className = "scene-member-label";
      label.textContent = friendly;
      label.title = id;

      const slider = document.createElement("input");
      slider.type = "range";
      slider.min = "1";
      slider.max = "255";
      slider.value = String(initial);
      slider.dataset.entityId = id;

      const pct = document.createElement("span");
      pct.className = "scene-member-pct";
      pct.textContent = brightnessPct(initial);

      row.appendChild(label);
      row.appendChild(slider);
      row.appendChild(pct);
      container.appendChild(row);
    }
  }

  function goToStep2() {
    const label = document.getElementById("scene-label").value.trim();
    if (!label) {
      document.getElementById("scene-label").focus();
      return;
    }
    const selectedOptions = Array.from(
      document.getElementById("scene-entities").selectedOptions
    );
    const entityIds = selectedOptions.map((o) => o.value).filter(Boolean);
    if (entityIds.length === 0) return;

    buildMemberSliders(entityIds);
    document.getElementById("scene-step-1").classList.add("section--hidden");
    document.getElementById("scene-step-2").classList.remove("section--hidden");
  }

  function goToStep1() {
    document.getElementById("scene-step-2").classList.add("section--hidden");
    document.getElementById("scene-step-1").classList.remove("section--hidden");
  }

  function confirmScene() {
    const label = document.getElementById("scene-label").value.trim();
    const icon  = document.getElementById("scene-icon").value.trim() || "mdi-lightbulb-group";

    const members = [];
    for (const row of document.querySelectorAll(".scene-member-row")) {
      const entityId  = row.dataset.entityId;
      const brightness = parseInt(row.querySelector("input[type='range']").value, 10);
      members.push({ entity_id: entityId, brightness });
    }

    if (!label || members.length === 0) return;

    const editEl = DashboardApp.getEditingTile();
    if (editEl) {
      // Update tile in-place
      editEl.dataset.label   = label;
      editEl.dataset.icon    = icon;
      editEl.dataset.members = JSON.stringify(members);

      const tile = { id: editEl.dataset.tileId, label, icon, members };
      const content = editEl.querySelector(".grid-stack-item-content");
      content.innerHTML = buildTileHTML(tile);
      updateSceneState(editEl, _getEntityStates());
      DashboardApp.closeAddModal();
      return;
    }

    const tile = {
      id:        "tile_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      tile_type: "scene",
      label,
      icon,
      members,
      x: 0, y: 0, w: 2, h: 2,
    };

    addSceneTileToGrid(tile, DashboardApp.getGrid(), _getEntityStates());
    DashboardApp.closeAddModal();
  }

  /** Live-preview handler — debounced 150 ms, calls HA turn_on per slider move. */
  function handleMemberSliderInput(e) {
    const slider = e.target;
    if (slider.type !== "range" || !slider.closest(".scene-member-row")) return;

    const entityId  = slider.dataset.entityId;
    const brightness = parseInt(slider.value, 10);

    // Update percentage label
    const pct = slider.closest(".scene-member-row").querySelector(".scene-member-pct");
    if (pct) pct.textContent = brightnessPct(brightness);

    // Debounced HA call
    clearTimeout(_previewTimer);
    _previewTimer = setTimeout(() => {
      fetch("/api/ha/services/light/turn_on", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entity_id: entityId, extra: { brightness } }),
      }).catch((err) => console.error("Live preview failed:", err));
    }, 150);
  }

  function populateForEdit(tileEl) {
    populateSceneEntityList();
    document.getElementById("scene-label").value = tileEl.dataset.label || "";
    document.getElementById("scene-icon").value  = tileEl.dataset.icon || "mdi-lightbulb-group";

    // Pre-select the lights that are in this scene
    const members = JSON.parse(tileEl.dataset.members || "[]");
    const memberIds = new Set(members.map((m) => m.entity_id));
    _editMembers = {};
    for (const m of members) {
      _editMembers[m.entity_id] = m.brightness;
    }

    const select = document.getElementById("scene-entities");
    for (const opt of select.options) {
      opt.selected = memberIds.has(opt.value);
    }
  }

  function resetModal() {
    // Return to step 1, clear member list, reset inputs
    _editMembers = null;
    document.getElementById("scene-step-2").classList.add("section--hidden");
    document.getElementById("scene-step-1").classList.remove("section--hidden");
    document.getElementById("scene-label").value = "";
    document.getElementById("scene-icon").value  = "mdi-lightbulb-group";
    document.getElementById("scene-member-list").innerHTML = "";
    const select = document.getElementById("scene-entities");
    if (select) Array.from(select.options).forEach((o) => (o.selected = false));
  }

  function initModal(getEntityStates) {
    _getEntityStates = getEntityStates;

    const tabs     = document.querySelectorAll(".modal__tab");
    const sections = {
      entity:  document.getElementById("entity-form-section"),
      scene:   document.getElementById("scene-form-section"),
      weather: document.getElementById("weather-form-section"),
    };

    // Tab switching — owns all three tabs
    for (const tab of tabs) {
      tab.addEventListener("click", () => {
        tabs.forEach((t) => t.classList.remove("modal__tab--active"));
        tab.classList.add("modal__tab--active");
        const active = tab.dataset.tab;
        for (const [name, el] of Object.entries(sections)) {
          el.classList.toggle("section--hidden", name !== active);
        }
        if (active === "scene") populateSceneEntityList();
      });
    }

    // Step navigation
    document.getElementById("btn-scene-next").addEventListener("click", goToStep2);
    document.getElementById("btn-scene-back").addEventListener("click", goToStep1);
    document.getElementById("btn-scene-confirm").addEventListener("click", confirmScene);

    // Live preview slider input (delegated to the member list container)
    document.getElementById("scene-member-list").addEventListener("input", handleMemberSliderInput);

    // Cancel
    document.getElementById("btn-cancel-scene").addEventListener("click", () =>
      DashboardApp.closeAddModal()
    );
  }

  // ── Public API ───────────────────────────────────────────────────────
  return { addSceneTileToGrid, updateSceneState, handleSceneToggle, isInCooldown, initModal, resetModal, populateForEdit };
})();
