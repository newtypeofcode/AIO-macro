/* ==========================================================================
   Macro Studio -- front end
   Plain top-level script: every `function foo()` here is window.foo, which is
   how the Python side pushes events in (addLog, hotkeyStart, ...).
   Do not wrap this file in an IIFE or turn it into a module.
   ========================================================================== */

/* ==========================================================================
   1. STATE
   ========================================================================== */
var state = {
  booted: false,
  version: "0.0.0",
  catalog: [],
  byType: {},
  phases: [{ key: "setup", label: "Setup" }, { key: "loop", label: "Loop" }],
  settings: {},
  macros: [],
  recordings: [],
  templates: [],
  windows: [],

  macro: { name: "", phases: { setup: [], loop: [] } },
  currentName: "",
  idCounter: 1,
  collapsed: {},

  status: {},
  recording: false,
  picking: false,

  preview: [],
  previewChecked: [],
  previewSource: { kind: "pending" },

  focusedCoord: null,
  keyCapture: null,
  dragPayload: null,

  /* While a nested block editor (the recording actions modal) owns the screen,
     markDirty() must not autosave the macro -- the rows being edited are not
     part of it. Set to a function for the lifetime of that editor. */
  dirtySink: null,

  saveTimer: null,
  recTimer: null,
  statusTimer: null,
  previewTimer: null
};

var GROUP_ORDER = ["Mouse", "Keyboard", "Timing", "Vision", "Flow", "Notify"];
var COLORS = {
  rose: "var(--rose)", blue: "var(--blue)", amber: "var(--amber)",
  teal: "var(--teal)", violet: "var(--violet)"
};
var MODIFIERS = ["shift", "ctrl", "alt", "win"];

/* The real colours live in style.css under html[data-theme=...]; these are
   only what the swatch card paints, so a card always previews the theme it
   applies. Keep the two in step when a theme is edited. */
var THEMES = [
  { key: "midnight", label: "Midnight", bg: "#0d0f18", panel: "#191d2e", accent: "#7c6cf6",
    text: "#e7eaf3", groups: ["#f2557a", "#4f8ef7", "#eda43a", "#2fbfa8", "#9b7cf8"] },
  { key: "obsidian", label: "Obsidian", bg: "#000000", panel: "#121215", accent: "#8b7bff",
    text: "#f2f2f5", groups: ["#ff6b8e", "#5c9dff", "#f5b544", "#34d3b8", "#a98bff"] },
  { key: "ember", label: "Ember", bg: "#16110f", panel: "#241d19", accent: "#f08a3c",
    text: "#f6ece4", groups: ["#f4667f", "#6ba8f2", "#f0b43c", "#3fc7a4", "#b98ef5"] },
  { key: "nord", label: "Nord", bg: "#1f242e", panel: "#2c3442", accent: "#7cb8e8",
    text: "#eceff4", groups: ["#e08596", "#6fa8dc", "#ebcb8b", "#67cfae", "#c0a0e0"] },
  { key: "daylight", label: "Daylight", bg: "#eef1f6", panel: "#f5f7fb", accent: "#5b46d9",
    text: "#131722", groups: ["#cc2e56", "#1f63c9", "#8f5b04", "#0d7d6b", "#6c40c9"] },
  { key: "sandstone", label: "Sandstone", bg: "#f4efe6", panel: "#f8f3ea", accent: "#a1541a",
    text: "#201a12", groups: ["#b52d4f", "#1f5eb8", "#855a08", "#0e7a63", "#6b3fb5"] }
];
var DEFAULT_THEME = "midnight";

/* Every failure core/webhook.py can report, in words a user can act on. */
var WEBHOOK_REASONS = {
  empty: "Paste a webhook URL first.",
  not_https: "The URL has to start with https://",
  not_discord: "That host is not Discord — the URL must be on discord.com.",
  bad_format: "That does not look like a Discord webhook URL. In Discord: Channel settings → Integrations → Webhooks → Copy Webhook URL.",
  requests_missing: "The 'requests' package is not installed, so nothing can be sent.",
  nothing_to_send: "There was nothing to send — add a message or an attachment.",
  attachment_too_large: "The attachment is too large for Discord (8 MB limit).",
  capture_failed: "The screen could not be captured.",
  no_such_image: "There is no saved image by that name."
};

function webhookReason(reason) {
  var key = String(reason || "unknown");
  if (WEBHOOK_REASONS[key]) return WEBHOOK_REASONS[key];
  if (key.indexOf("rejected_") === 0) {
    return "Discord rejected the webhook (" + key.slice(9) + ") — it was probably deleted.";
  }
  if (key.indexOf("http_") === 0) return "Discord answered with HTTP " + key.slice(5) + ".";
  return "Could not reach Discord (" + key + ").";
}
var HOTKEYS = [
  { key: "hotkey_start", label: "Start macro" },
  { key: "hotkey_stop", label: "Stop macro" },
  { key: "hotkey_pause", label: "Pause / resume" },
  { key: "hotkey_record", label: "Toggle recording" },
  { key: "hotkey_pick", label: "Pick coordinate" }
];

/* ==========================================================================
   2. SMALL HELPERS
   ========================================================================== */
function $(sel, root) { return (root || document).querySelector(sel); }
function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

function el(tag, attrs, children) {
  var node = document.createElement(tag);
  if (attrs) {
    Object.keys(attrs).forEach(function (k) {
      if (k === "class") node.className = attrs[k];
      else if (k === "text") node.textContent = attrs[k];
      else if (k === "html") node.innerHTML = attrs[k];
      else if (k === "style") node.setAttribute("style", attrs[k]);
      else if (k.slice(0, 2) === "on") node.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== null && attrs[k] !== undefined) node.setAttribute(k, attrs[k]);
    });
  }
  (children || []).forEach(function (c) {
    if (c === null || c === undefined) return;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  });
  return node;
}

function icon(id, cls) {
  var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "ic " + (cls || ""));
  var use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", "#" + id);
  svg.appendChild(use);
  return svg;
}

function colorOf(name) { return COLORS[name] || "var(--accent)"; }
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function toInt(v, d) { var n = parseInt(v, 10); return isNaN(n) ? (d || 0) : n; }
function toNum(v, d) { var n = parseFloat(v); return isNaN(n) ? (d || 0) : n; }
function nextId() { return "b" + (state.idCounter++); }

function adoptIds(blocks) {
  (blocks || []).forEach(function (b) {
    var m = /^b(\d+)$/.exec(String(b && b.id || ""));
    if (m) state.idCounter = Math.max(state.idCounter, parseInt(m[1], 10) + 1);
  });
}

function debounce(fnKey, ms, fn) {
  clearTimeout(state[fnKey]);
  state[fnKey] = setTimeout(fn, ms);
}

/* ==========================================================================
   3. PYTHON BRIDGE
   ========================================================================== */
function bridgeReady() {
  return !!(window.pywebview && window.pywebview.api);
}

async function callApi(name, args, quiet) {
  try {
    if (!bridgeReady()) throw new Error("bridge not ready");
    var fn = window.pywebview.api[name];
    if (typeof fn !== "function") throw new Error("api." + name + " is unavailable");
    return await fn.apply(window.pywebview.api, args || []);
  } catch (err) {
    var msg = (err && err.message) ? err.message : String(err);
    console.error("[api] " + name, err);
    if (!quiet) toast(name + ": " + msg, "err");
    return null;
  }
}
function api(name) { return callApi(name, Array.prototype.slice.call(arguments, 1), false); }
function apiQ(name) { return callApi(name, Array.prototype.slice.call(arguments, 1), true); }

/* ==========================================================================
   4. TOASTS / MODALS
   ========================================================================== */
function toast(message, kind) {
  var wrap = $("#toastWrap");
  if (!wrap) return;
  var node = el("div", { class: "toast " + (kind || ""), text: String(message) });
  wrap.appendChild(node);
  setTimeout(function () {
    node.style.opacity = "0";
    node.style.transition = "opacity 180ms";
    setTimeout(function () { if (node.parentNode) node.parentNode.removeChild(node); }, 200);
  }, kind === "err" ? 4200 : 2600);
}

function askText(title, value, hint) {
  return new Promise(function (resolve) {
    var overlay = $("#textModal");
    var input = $("#textModalInput");
    $("#textModalTitle").textContent = title || "Name";
    $("#textModalHint").textContent = hint || "";
    input.value = value || "";
    overlay.classList.remove("hidden");
    setTimeout(function () { input.focus(); input.select(); }, 20);

    function done(result) {
      overlay.classList.add("hidden");
      $("#btnTextOk").removeEventListener("click", ok);
      $("#btnTextCancel").removeEventListener("click", cancel);
      input.removeEventListener("keydown", key);
      resolve(result);
    }
    function ok() { done(input.value.trim() || null); }
    function cancel() { done(null); }
    function key(e) {
      if (e.key === "Enter") { e.preventDefault(); ok(); }
      if (e.key === "Escape") { e.preventDefault(); cancel(); }
    }
    $("#btnTextOk").addEventListener("click", ok);
    $("#btnTextCancel").addEventListener("click", cancel);
    input.addEventListener("keydown", key);
  });
}

function askConfirm(title, text) {
  return new Promise(function (resolve) {
    var overlay = $("#confirmModal");
    $("#confirmTitle").textContent = title || "Are you sure?";
    $("#confirmText").textContent = text || "";
    overlay.classList.remove("hidden");

    function done(result) {
      overlay.classList.add("hidden");
      $("#btnConfirmOk").removeEventListener("click", ok);
      $("#btnConfirmCancel").removeEventListener("click", cancel);
      document.removeEventListener("keydown", key, true);
      resolve(result);
    }
    function ok() { done(true); }
    function cancel() { done(false); }
    /* Capture phase, so this answers Escape before the global handler sees it
       -- the confirm is always the topmost thing on screen while it is up.
       Without its own handler, Escape fell through and closed whatever modal
       was underneath while leaving the question itself unanswered. */
    function key(e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancel(); }
      else if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); ok(); }
    }
    $("#btnConfirmOk").addEventListener("click", ok);
    $("#btnConfirmCancel").addEventListener("click", cancel);
    document.addEventListener("keydown", key, true);
    setTimeout(function () {
      var okBtn = $("#btnConfirmOk");
      if (okBtn) okBtn.focus();
    }, 20);
  });
}

/* ==========================================================================
   5. LOG PANEL  (addLog / clearLogs are called from Python)
   ========================================================================== */
function logClass(msg) {
  var m = String(msg);
  if (/fail|error|could not|unavailable|missing|not available|discarded/i.test(m)) return "err";
  if (/warn|drift|not found|recommended/i.test(m)) return "warn";
  if (/\bok\b|saved|ready|started|picked/i.test(m)) return "ok";
  return "";
}

function appendLogEntry(entry) {
  var body = $("#logBody");
  if (!body || !entry) return;
  var line = el("div", { class: "log-line " + logClass(entry.msg) }, [
    el("span", { class: "log-t", text: entry.t || "" }),
    el("span", { class: "log-m", text: String(entry.msg == null ? "" : entry.msg) })
  ]);
  body.appendChild(line);
  while (body.childElementCount > 400) body.removeChild(body.firstElementChild);
  body.scrollTop = body.scrollHeight;
  var last = $("#logLast");
  if (last) last.textContent = String(entry.msg == null ? "" : entry.msg);
}

/* Python -> JS push */
function addLog(entry) {
  try {
    if (typeof entry === "string") entry = JSON.parse(entry);
  } catch (e) { entry = { t: "", msg: String(entry) }; }
  appendLogEntry(entry);
}

/* Python -> JS push */
function clearLogs() {
  var body = $("#logBody");
  if (body) body.innerHTML = "";
  var last = $("#logLast");
  if (last) last.textContent = "";
}

/* ==========================================================================
   6. NAVIGATION
   ========================================================================== */
function showScreen(name) {
  $$(".screen").forEach(function (s) { s.classList.toggle("active", s.id === "screen-" + name); });
  $$(".railbtn").forEach(function (b) { b.classList.toggle("active", b.dataset.screen === name); });
  if (name === "settings") { refreshWindows(); refreshWebhook(); }
  if (name === "images") { refreshTemplates(); }
  if (name === "record") { refreshRecordings(); }
}

/* ==========================================================================
   7. BLOCK MODEL
   ========================================================================== */
function specFor(type) { return state.byType[type] || null; }

function defaultParams(type) {
  var spec = specFor(type);
  var out = {};
  if (!spec) return out;
  (spec.fields || []).forEach(function (f) {
    out[f.key] = (f.default === undefined) ? null : f.default;
  });
  return out;
}

/* --------------------------------------------------------------------------
   "Test confidence" (settings key default_threshold) is the confidence a NEW
   Vision block starts life with -- which is what makes the name honest; it
   used to drive nothing but the Test button on the Images screen.

   Only blocks created from here are seeded. Loading, importing, duplicating
   and normalising all go through defaultParams/normalizeBlock instead, so a
   macro built last week keeps every value it was tuned with.
   -------------------------------------------------------------------------- */
var SEEDED_CONFIDENCE = {
  wait_image: "threshold", click_image: "threshold", wait_image_gone: "threshold",
  wait_text: "confidence", click_text: "confidence",
  wait_color: "confidence", click_color: "confidence"
};

function seedConfidence(type, params) {
  var key = SEEDED_CONFIDENCE[type];
  if (!key || !(key in params)) return;
  var seed = parseFloat(state.settings ? state.settings.default_threshold : NaN);
  if (isNaN(seed)) return;
  params[key] = clamp(seed, 0, 1);
}

function makeBlock(type, params) {
  var merged = defaultParams(type);
  seedConfidence(type, merged);
  if (params) Object.keys(params).forEach(function (k) { merged[k] = params[k]; });
  return { id: nextId(), type: type, enabled: true, once: false, params: merged };
}

/* Fill in anything a saved / recorded / imported block is missing. */
function normalizeBlock(raw, reid) {
  if (!raw || !specFor(raw.type)) return null;
  var params = defaultParams(raw.type);
  var given = raw.params || {};
  Object.keys(given).forEach(function (k) { params[k] = given[k]; });
  return {
    id: (reid || !raw.id) ? nextId() : String(raw.id),
    type: raw.type,
    enabled: raw.enabled === undefined ? true : !!raw.enabled,
    once: !!raw.once,
    params: params
  };
}

function normalizeList(list, reid) {
  var out = [];
  (list || []).forEach(function (b) {
    var n = normalizeBlock(b, reid);
    if (n) out.push(n);
  });
  return out;
}

function isPhaseKey(phase) {
  if (!phase) return false;
  return state.phases.some(function (p) { return p.key === phase; });
}

function phaseArray(phase) {
  // Guarded: a null/undefined phase used to create state.macro.phases[null],
  // a bogus phase that then rode along into every save. The recording-actions
  // modal renders rows with ctx.phase === null, so this is reachable.
  if (!isPhaseKey(phase)) return [];
  if (!state.macro.phases[phase]) state.macro.phases[phase] = [];
  return state.macro.phases[phase];
}

function findBlock(phase, id) {
  var arr = phaseArray(phase);
  for (var i = 0; i < arr.length; i++) if (arr[i].id === id) return arr[i];
  return null;
}

function currentMacro() {
  return {
    name: state.currentName || ($("#macroName") ? $("#macroName").value.trim() : "") || "Untitled",
    phases: { setup: phaseArray("setup"), loop: phaseArray("loop") }
  };
}

/* ==========================================================================
   8. BUILDER -- palette
   ========================================================================== */
function renderPalette() {
  buildPalette($("#paletteGroups"), {
    scope: "phase",
    hint: "Перетащи в фазу или кликни, чтобы добавить в Loop.",
    onPick: function (spec) {
      phaseArray("loop").push(makeBlock(spec.type));
      renderPhases();
      markDirty();
    }
  });
}

/* One palette renderer, two hosts: the builder's rail and the nested blocks
   editor's own copy (a modal covers the builder, so it cannot borrow it).
   `scope` rides along on the drag payload so a chip from one palette can only
   ever be dropped into the list it belongs to. */
function buildPalette(host, opts) {
  if (!host) return;
  host.innerHTML = "";

  var groups = {};
  state.catalog.forEach(function (spec) {
    var g = spec.group || "Other";
    (groups[g] = groups[g] || []).push(spec);
  });
  var names = Object.keys(groups).sort(function (a, b) {
    var ia = GROUP_ORDER.indexOf(a), ib = GROUP_ORDER.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });

  names.forEach(function (g) {
    var items = el("div", { class: "pgroup-items" });
    groups[g].forEach(function (spec) {
      var chip = el("div", {
        class: "chip",
        draggable: "true",
        style: "--chip-color:" + colorOf(spec.color)
      }, [el("span", { class: "chip-dot" }), el("span", { text: spec.label || spec.type })]);
      attachTip(chip, spec.label || spec.type,
                (spec.desc ? spec.desc + "\n\n" : "") + opts.hint);

      chip.addEventListener("dragstart", function (e) {
        state.dragPayload = { kind: "new", type: spec.type, scope: opts.scope };
        chip.classList.add("dragging");
        try {
          e.dataTransfer.effectAllowed = "copy";
          e.dataTransfer.setData("text/plain", spec.type);
        } catch (err) { /* ignore */ }
      });
      chip.addEventListener("dragend", function () {
        chip.classList.remove("dragging");
        state.dragPayload = null;
        removeIndicator();
      });
      chip.addEventListener("click", function () { opts.onPick(spec); });
      items.appendChild(chip);
    });
    host.appendChild(el("div", {}, [el("div", { class: "pgroup-title", text: g }), items]));
  });
}

/* ==========================================================================
   9. BUILDER -- phases and rows
   ========================================================================== */
function renderPhases() {
  var host = $("#phases");
  if (!host) return;
  host.innerHTML = "";

  state.phases.forEach(function (ph) {
    var blocks = phaseArray(ph.key);
    var badgeText = ph.key === "setup" ? "RUNS ONCE" : "REPEATS";
    var badgeClass = ph.key === "setup" ? "badge badge-once" : "badge badge-repeat";

    var collapseBtn = el("button", { class: "phase-collapse", title: "Collapse" }, [icon("i-chev", "ic-xs")]);
    var head = el("div", { class: "phase-head" }, [
      collapseBtn,
      el("span", { class: "phase-title", text: ph.label }),
      el("span", { class: badgeClass, text: badgeText }),
      el("span", { class: "phase-count", text: blocks.length + (blocks.length === 1 ? " block" : " blocks") }),
      el("span", { class: "flex-spacer" })
    ]);
    /* How often the repeating phase repeats is a property OF that phase, so it
       belongs next to it -- the same two settings the Setup screen owns, kept
       in step by syncLoopControls(). */
    if (ph.key === "loop") head.appendChild(loopRepeatControls());
    head.appendChild(el("button", {
      class: "btn btn-sm btn-ghost-danger", text: "Clear",
      onclick: function () { clearPhase(ph.key, ph.label); }
    }));

    var list = el("div", { class: "blocklist" });
    list.dataset.phase = ph.key;
    var ctx = phaseCtx(ph.key);

    if (!blocks.length) {
      list.appendChild(el("div", { class: "dropzone", text: "drag blocks here" }));
    } else {
      blocks.forEach(function (block, index) { list.appendChild(renderBlockRow(block, index, ctx)); });
    }
    wireDropTarget(list, ctx);

    var panel = el("div", { class: "phase" + (state.collapsed[ph.key] ? " collapsed" : "") }, [
      head, el("div", { class: "phase-body" }, [list])
    ]);
    collapseBtn.addEventListener("click", function () {
      state.collapsed[ph.key] = !state.collapsed[ph.key];
      panel.classList.toggle("collapsed", !!state.collapsed[ph.key]);
    });
    host.appendChild(panel);
  });
}

/* --------------------------------------------------------------------------
   loop_forever / loop_count, rendered into the Loop phase header.

   Both are plain settings, and the Setup screen edits the very same two keys,
   so whichever side changes writes the setting and then re-reads BOTH sides
   from state.settings -- there is no second copy of the truth.
   -------------------------------------------------------------------------- */
function loopRepeatControls() {
  var forever = el("input", { type: "checkbox", id: "loopForever" });
  var count = el("input", {
    class: "inp inp-loop", type: "number", min: "1", step: "1", id: "loopCount"
  });

  forever.addEventListener("change", async function () {
    await setSetting("loop_forever", forever.checked);
    syncLoopControls();
  });
  count.addEventListener("change", async function () {
    var n = Math.max(1, toInt(count.value, 1));
    count.value = n;
    await setSetting("loop_count", n);
    syncLoopControls();
  });

  var node = el("div", { class: "loop-ctl" }, [
    el("label", { class: "switch-row", title: "Repeat the Loop phase until you press Stop" }, [
      el("span", { class: "switch" }, [forever, el("span", { class: "slider" })]),
      el("span", { text: "forever" })
    ]),
    el("span", { class: "loop-x", text: "×" }),
    count
  ]);
  attachTip(node, "Repeats",
            "Сколько раз выполнить фазу Loop.\n\n"
            + "«forever» — повторять, пока не нажмёшь Stop. Если выключить, "
            + "макрос остановится сам после указанного числа проходов.\n\n"
            + "Это те же настройки, что и на экране Setup.");
  syncLoopControlsIn(node);
  return node;
}

function syncLoopControlsIn(root) {
  var s = state.settings || {};
  var forever = !!s.loop_forever;
  var count = Math.max(1, toInt(s.loop_count, 1));

  var fnode = $("#loopForever", root);
  var cnode = $("#loopCount", root);
  if (fnode) fnode.checked = forever;
  if (cnode) { cnode.value = count; cnode.disabled = forever; }

  var sForever = $("#setLoopForever");
  var sCount = $("#setLoopCount");
  if (sForever) sForever.checked = forever;
  if (sCount) { sCount.value = count; sCount.disabled = forever; }
}

function syncLoopControls() { syncLoopControlsIn(document); }

/* --------------------------------------------------------------------------
   A row is rendered against a CONTEXT rather than against a phase name, so the
   very same renderer (and therefore every field editor) also drives the
   recording-actions modal, which edits a list that is not part of the macro.
   -------------------------------------------------------------------------- */
function phaseCtx(phase) {
  return {
    scope: "phase",
    phase: phase,
    allowNew: true,
    full: true,
    list: function () { return phaseArray(phase); },
    rerender: renderPhases,
    changed: markDirty
  };
}

/* Kept so anything (or anyone) still calling the old signature works. */
function renderRow(phase, block, index) {
  return renderBlockRow(block, index, phaseCtx(phase));
}

function renderBlockRow(block, index, ctx) {
  var phase = ctx.phase;
  var spec = specFor(block.type);
  var accent = colorOf(spec ? spec.color : "");
  var row = el("div", {
    class: "block-row" + (block.enabled ? "" : " disabled"),
    style: "--row-color:" + accent
  });
  row.dataset.id = block.id;
  if (phase) row.dataset.phase = phase;

  /* drag handle -- the row only becomes draggable while the grip is held */
  var grip = el("div", { class: "grip", title: "Drag to reorder" }, [icon("i-grip")]);
  grip.addEventListener("mousedown", function () { row.draggable = true; });
  row.addEventListener("dragstart", function (e) {
    state.dragPayload = { kind: "move", scope: ctx.scope, from: ctx, id: block.id };
    row.classList.add("dragging");
    try {
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", block.id);
    } catch (err) { /* ignore */ }
  });
  row.addEventListener("dragend", function () {
    row.classList.remove("dragging");
    row.draggable = false;
    state.dragPayload = null;
    removeIndicator();
  });

  var typeLabel = el("div", {
    class: "row-type",
    text: spec ? spec.label : block.type
  });
  attachTip(typeLabel, spec ? spec.label : block.type,
            ((spec && spec.desc) ? spec.desc + "\n\n" : "")
            + "Клик по названию включает и выключает блок.");
  typeLabel.addEventListener("click", function () {
    block.enabled = !block.enabled;
    row.classList.toggle("disabled", !block.enabled);
    ctx.changed();
  });

  var fields = el("div", { class: "row-fields" });
  var conditional = [];
  (spec ? spec.fields : []).forEach(function (f) {
    var node = renderField(block, f, phase);
    if (!node) return;
    fields.appendChild(node);
    conditional.push({ f: f, node: node });
  });
  if (hasXY(spec)) fields.appendChild(coordPickButton(block, ctx));

  /* A `change` from any control in this row (the custom dropdowns dispatch a
     bubbling one) can flip which of the remaining fields still apply. */
  function syncFields() {
    conditional.forEach(function (entry) {
      entry.node.classList.toggle("hidden", !fieldApplies(block, entry.f));
      if (entry.node._syncField) entry.node._syncField();
    });
  }
  syncFields();
  row.addEventListener("change", syncFields);
  row._syncFields = syncFields;

  /* --------------------------------------------------------- row actions */
  var extra = [];

  /* Play Recording carries its actions somewhere else entirely; this is the
     only door into them. */
  if (block.type === "playback") {
    var editBtn = el("button", {
      class: "btn btn-xs rowbtn-edit", text: "Edit actions",
      title: "Open the recorded actions and edit them in place"
    });
    var syncEditBtn = function () {
      editBtn.disabled = !String(block.params.recording || "").trim();
    };
    syncEditBtn();
    /* the recording <select> lives in this row, so its change bubbles here */
    row.addEventListener("change", syncEditBtn);
    editBtn.addEventListener("click", function () {
      var name = String(block.params.recording || "").trim();
      if (!name) return;
      openRecordingEditor(name);
    });
    extra.push(editBtn);
  }

  /* Shows exactly what would be attached, without sending anything. */
  if (block.type === "send_webhook") {
    var previewBtn = el("button", {
      class: "btn btn-xs rowbtn-edit", text: "Preview",
      title: "Show the image this block would attach — nothing is sent"
    });
    previewBtn.addEventListener("click", function () { previewWebhookSource(block); });
    extra.push(previewBtn);
  }

  var actions = [];
  if (ctx.full) {
    var onceBtn = el("button", {
      class: "once-toggle" + (block.once ? " on" : ""), text: "ONCE",
      title: "Run this block only on the first pass"
    });
    onceBtn.addEventListener("click", function () {
      block.once = !block.once;
      onceBtn.classList.toggle("on", block.once);
      ctx.changed();
    });

    var runBtn = el("button", { class: "iconbtn go", title: "Run just this block" }, [icon("i-play", "ic-xs")]);
    runBtn.addEventListener("click", function () { runSingle(block, row); });

    var dupBtn = el("button", { class: "iconbtn", title: "Duplicate" }, [icon("i-copy", "ic-xs")]);
    dupBtn.addEventListener("click", function () {
      var copy = normalizeBlock(JSON.parse(JSON.stringify(block)), true);
      ctx.list().splice(index + 1, 0, copy);
      ctx.rerender();
      ctx.changed();
    });
    actions.push(onceBtn, runBtn, dupBtn);
  } else {
    /* drag reordering works here too, but arrows are keyboard/precision
       friendly and never fight the field editors for the mouse */
    var upBtn = el("button", { class: "iconbtn", title: "Move up", text: "↑" });
    upBtn.disabled = index === 0;
    upBtn.addEventListener("click", function () { moveInList(ctx, block, -1); });
    var downBtn = el("button", { class: "iconbtn", title: "Move down", text: "↓" });
    downBtn.disabled = index >= ctx.list().length - 1;
    downBtn.addEventListener("click", function () { moveInList(ctx, block, 1); });
    actions.push(upBtn, downBtn);
  }

  var delBtn = el("button", { class: "iconbtn danger", title: "Delete" }, [icon("i-trash", "ic-xs")]);
  delBtn.addEventListener("click", function () {
    var arr = ctx.list();
    var at = arr.indexOf(block);
    if (at >= 0) arr.splice(at, 1);
    ctx.rerender();
    ctx.changed();
  });
  actions.push(delBtn);

  row.appendChild(grip);
  row.appendChild(typeLabel);
  row.appendChild(el("div", { class: "row-ord", text: "#" + (index + 1) }));
  row.appendChild(fields);
  extra.forEach(function (node) { row.appendChild(node); });
  row.appendChild(el("div", { class: "row-actions" }, actions));
  return row;
}

function moveInList(ctx, block, delta) {
  var arr = ctx.list();
  var at = arr.indexOf(block);
  var to = at + delta;
  if (at < 0 || to < 0 || to >= arr.length) return;
  arr.splice(to, 0, arr.splice(at, 1)[0]);
  ctx.rerender();
  ctx.changed();
}

function hasXY(spec) {
  if (!spec) return false;
  var hasX = false, hasY = false;
  (spec.fields || []).forEach(function (f) {
    if (f.kind === "int" && f.key === "x") hasX = true;
    if (f.kind === "int" && f.key === "y") hasY = true;
  });
  return hasX && hasY;
}

function clearPhase(phase, label) {
  askConfirm("Clear " + label + "?", "Every block in this phase is removed. This cannot be undone.")
    .then(function (yes) {
      if (!yes) return;
      state.macro.phases[phase] = [];
      renderPhases();
      markDirty();
    });
}

async function runSingle(block, row) {
  var result = await api("run_single_block", JSON.parse(JSON.stringify(block)));
  if (result && result.ok === false) {
    toast("Could not run block: " + (result.reason || "unknown"), "err");
    return;
  }
  if (row) {
    row.classList.remove("flash");
    void row.offsetWidth;
    row.classList.add("flash");
  }
}

/* ==========================================================================
   10. BUILDER -- field renderers (driven entirely by catalog `kind`)
   ========================================================================== */
function wrapField(label, control, help) {
  var lab = el("span", { class: "flab", text: label });
  if (help) {
    lab.classList.add("has-tip");
    attachTip(lab, label, help);
  }
  return el("label", { class: "field" }, [lab, control]);
}

/* --------------------------------------------------------------------------
   Hover tooltips. A styled popup rather than the native `title` attribute:
   native tooltips take ~1s to appear, cannot be styled, and truncate the
   multi-line explanations the block help carries.
   -------------------------------------------------------------------------- */
var tipEl = null;
var tipTimer = null;

function ensureTipEl() {
  if (!tipEl) {
    tipEl = el("div", { class: "tip" });
    document.body.appendChild(tipEl);
  }
  return tipEl;
}

function hideTip() {
  if (tipTimer) { clearTimeout(tipTimer); tipTimer = null; }
  if (tipEl) tipEl.classList.remove("show");
}

function showTip(anchor, title, body) {
  var node = ensureTipEl();
  node.innerHTML = "";
  if (title) node.appendChild(el("div", { class: "tip-title", text: title }));
  node.appendChild(el("div", { class: "tip-body", text: body }));

  // Measured while visible-but-transparent so the size is real, then flipped
  // to whichever side actually has room.
  node.style.left = "-9999px";
  node.style.top = "0px";
  node.classList.add("show");

  var rect = anchor.getBoundingClientRect();
  var box = node.getBoundingClientRect();
  var margin = 8;
  var left = rect.left;
  if (left + box.width + margin > window.innerWidth) {
    left = window.innerWidth - box.width - margin;
  }
  left = Math.max(margin, left);

  var top = rect.bottom + 6;
  if (top + box.height + margin > window.innerHeight) {
    top = rect.top - box.height - 6;          // flip above
  }
  top = Math.max(margin, top);

  node.style.left = Math.round(left) + "px";
  node.style.top = Math.round(top) + "px";
}

function attachTip(node, title, body) {
  if (!body) return node;
  node.addEventListener("mouseenter", function () {
    if (tipTimer) clearTimeout(tipTimer);
    tipTimer = setTimeout(function () { showTip(node, title, body); }, 220);
  });
  node.addEventListener("mouseleave", hideTip);
  // A tooltip left hanging over a modal or a moved row reads as a glitch.
  node.addEventListener("mousedown", hideTip);
  return node;
}

/* --------------------------------------------------------------------------
   Custom dropdown.

   The closed box of a native <select> can be styled; the popup the OS draws
   for it cannot, so every dropdown in the app used to break the theme the
   moment it was opened. This replaces the popup with a themed listbox and
   KEEPS the real <select> in the DOM as the value holder -- `select.value`
   still reads back, and picking an option dispatches a bubbling `change`, so
   every existing handler (including the row-level ones) works untouched.
   -------------------------------------------------------------------------- */
var openSelect = null;

function closeOpenSelect(refocus) {
  if (openSelect) openSelect.close(refocus);
}

function enhanceSelect(select, opts) {
  opts = opts || {};

  var wrap = el("div", { class: "sel " + String(select.className || "").replace(/\binp\b/g, "").trim() });
  var txt = el("span", { class: "sel-txt" });
  var btn = el("button", { class: "sel-btn", type: "button" }, [txt, icon("i-chev", "ic-xs sel-chev")]);
  btn.setAttribute("role", "combobox");
  btn.setAttribute("aria-haspopup", "listbox");
  btn.setAttribute("aria-expanded", "false");

  select.classList.add("sel-native");
  select.setAttribute("tabindex", "-1");
  select.setAttribute("aria-hidden", "true");

  if (select.parentNode) select.parentNode.insertBefore(wrap, select);
  wrap.appendChild(select);
  wrap.appendChild(btn);

  var panel = null;
  var optionNodes = [];
  var active = -1;

  function syncText() {
    var option = select.options[select.selectedIndex];
    var label = option ? option.textContent : "";
    txt.textContent = label || (opts.placeholder || "");
    txt.classList.toggle("placeholder", !label);
    btn.title = label;
    btn.disabled = !!select.disabled;
  }

  function setActive(index) {
    active = index;
    optionNodes.forEach(function (node, i) { node.classList.toggle("active", i === index); });
    if (optionNodes[index]) {
      var node = optionNodes[index];
      var top = node.offsetTop, bottom = top + node.offsetHeight;
      if (top < panel.scrollTop) panel.scrollTop = top;
      else if (bottom > panel.scrollTop + panel.clientHeight) panel.scrollTop = bottom - panel.clientHeight;
    }
  }

  function position() {
    var r = btn.getBoundingClientRect();
    panel.style.minWidth = Math.round(r.width) + "px";
    panel.style.left = "-9999px";
    panel.style.top = "0px";
    var box = panel.getBoundingClientRect();
    var left = Math.max(8, Math.min(r.left, window.innerWidth - box.width - 8));
    var top = r.bottom + 4;
    if (top + box.height + 8 > window.innerHeight) {
      top = r.top - box.height - 4;                       /* flip above */
      if (top < 8) top = Math.max(8, window.innerHeight - box.height - 8);
    }
    panel.style.left = Math.round(left) + "px";
    panel.style.top = Math.round(top) + "px";
  }

  function pick(index) {
    if (index < 0 || index >= select.options.length) return;
    if (select.selectedIndex !== index) {
      select.selectedIndex = index;
      syncText();
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    close(true);
  }

  function onDocDown(e) {
    if (panel && panel.contains(e.target)) return;
    if (wrap.contains(e.target)) return;
    close(false);
  }
  function onScroll(e) {
    if (panel && e && e.target && panel.contains(e.target)) return;
    close(false);
  }

  function open() {
    if (panel || select.disabled) return;
    closeOpenSelect(false);
    if (opts.beforeOpen) opts.beforeOpen();
    syncText();

    panel = el("div", { class: "sel-panel" });
    panel.setAttribute("role", "listbox");
    optionNodes = [];
    Array.prototype.forEach.call(select.options, function (option, i) {
      var node = el("div", { class: "sel-opt", text: option.textContent });
      node.setAttribute("role", "option");
      node.setAttribute("aria-selected", i === select.selectedIndex ? "true" : "false");
      /* mousedown default would blur the button and close us before the click */
      node.addEventListener("mousedown", function (e) { e.preventDefault(); });
      node.addEventListener("click", function () { pick(i); });
      node.addEventListener("mousemove", function () { setActive(i); });
      optionNodes.push(node);
      panel.appendChild(node);
    });
    document.body.appendChild(panel);
    position();

    wrap.classList.add("open");
    btn.setAttribute("aria-expanded", "true");
    openSelect = handle;
    setActive(select.selectedIndex);

    document.addEventListener("mousedown", onDocDown, true);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll, true);
  }

  function close(refocus) {
    if (!panel) return;
    if (panel.parentNode) panel.parentNode.removeChild(panel);
    panel = null;
    optionNodes = [];
    active = -1;
    wrap.classList.remove("open");
    btn.setAttribute("aria-expanded", "false");
    if (openSelect === handle) openSelect = null;
    document.removeEventListener("mousedown", onDocDown, true);
    window.removeEventListener("scroll", onScroll, true);
    window.removeEventListener("resize", onScroll, true);
    if (refocus) btn.focus();
  }

  var handle = { open: open, close: close, sync: syncText, el: wrap, button: btn };

  btn.addEventListener("click", function (e) {
    /* The control usually sits inside <label class="field">, whose default
       action would forward the click to the hidden native select. */
    e.preventDefault();
    e.stopPropagation();
    if (panel) close(true); else open();
  });

  btn.addEventListener("keydown", function (e) {
    if (!panel) {
      if (e.key === "Enter" || e.key === " " || e.key === "Spacebar"
          || e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        open();
      }
      return;
    }
    if (e.key === "ArrowDown") { e.preventDefault(); setActive(clamp(active + 1, 0, optionNodes.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(clamp(active - 1, 0, optionNodes.length - 1)); }
    else if (e.key === "Home") { e.preventDefault(); setActive(0); }
    else if (e.key === "End") { e.preventDefault(); setActive(optionNodes.length - 1); }
    else if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") { e.preventDefault(); pick(active); }
    else if (e.key === "Escape") {
      /* Must not reach the global handler: that would close the modal this
         dropdown is sitting in. */
      e.preventDefault();
      e.stopPropagation();
      close(true);
    } else if (e.key === "Tab") {
      close(false);
    }
  });

  select.addEventListener("change", syncText);
  syncText();
  select._sel = handle;
  return wrap;
}

/* --------------------------------------------------------------------------
   Conditional fields. A choice higher up the row decides whether a field
   below it means anything at all; showing an inert "Region" next to
   "Attach: none" is worse than showing nothing.
   -------------------------------------------------------------------------- */
function fieldApplies(block, f) {
  var params = block.params || {};
  /* "Fallback" is the list that runs, "Then" is what happens once it has run:
     both are answers to a question only "run blocks" asks. */
  if (f.key === "on_fail_blocks" || f.key === "on_fail_after") {
    return String(params.on_fail || "") === "run blocks";
  }
  if (block.type === "send_webhook" && f.key === "region") {
    return String(params.source || "") === "region";
  }
  if (block.type === "send_webhook" && f.key === "template") {
    return String(params.source || "") === "saved image";
  }
  return true;
}

function renderField(block, f, phase) {
  switch (f.kind) {
    case "blocks": return fieldBlocks(block, f);
    case "int": return fieldNumber(block, f, phase, true);
    case "float": return fieldNumber(block, f, phase, false);
    case "text": return fieldText(block, f);
    case "key": return fieldKey(block, f);
    case "bool": return fieldBool(block, f);
    case "choice": return fieldChoice(block, f);
    case "modifiers": return fieldModifiers(block, f);
    case "region": return fieldRegion(block, f);
    case "color": return fieldColor(block, f);
    case "template": return fieldTemplate(block, f);
    case "recording": return fieldRecording(block, f);
    case "coord": return null;             /* not used by the catalog */
    default: return fieldText(block, f);
  }
}

function fieldNumber(block, f, phase, isInt) {
  var input = el("input", {
    class: "inp " + (isInt ? "f-int" : "f-float"),
    type: "number",
    step: isInt ? "1" : "0.01"
  });
  var value = block.params[f.key];
  input.value = (value === null || value === undefined) ? "" : value;

  input.addEventListener("input", function () {
    var fallback = (f.default === undefined || f.default === null) ? 0 : f.default;
    block.params[f.key] = input.value === "" ? fallback
      : (isInt ? toInt(input.value, fallback) : toNum(input.value, fallback));
    markDirty();
  });
  input.addEventListener("blur", function () {
    if (input.value === "") input.value = block.params[f.key];
  });
  if (isInt && (f.key === "x" || f.key === "y")) {
    input.addEventListener("focus", function () {
      // Only for rows that belong to a real phase. Rows in the
      // recording-actions modal render with phase === null, and recording a
      // null phase here made the pick hotkey look up a block in a phase that
      // does not exist.
      state.focusedCoord = isPhaseKey(phase) ? { phase: phase, id: block.id } : null;
    });
  }
  return wrapField(f.label || f.key, input, f.help);
}

function fieldText(block, f) {
  var input = el("input", { class: "inp f-text", type: "text", spellcheck: "false" });
  input.value = block.params[f.key] == null ? "" : String(block.params[f.key]);
  input.addEventListener("input", function () {
    block.params[f.key] = input.value;
    markDirty();
  });
  return wrapField(f.label || f.key, input, f.help);
}

function fieldKey(block, f) {
  var value = block.params[f.key] || "";
  var btn = el("button", { class: "keybtn" + (value ? "" : " empty"), text: value || "click, then press" });
  btn.addEventListener("click", function () {
    beginKeyCapture(btn, function (name) {
      block.params[f.key] = name;
      btn.textContent = name;
      btn.classList.remove("empty");
      markDirty();
    });
  });
  return wrapField(f.label || f.key, btn, f.help);
}

function fieldBool(block, f) {
  var input = el("input", { type: "checkbox" });
  input.checked = !!block.params[f.key];
  input.addEventListener("change", function () {
    block.params[f.key] = input.checked;
    markDirty();
  });
  var sw = el("span", { class: "switch" }, [input, el("span", { class: "slider" })]);
  return wrapField(f.label || f.key, sw, f.help);
}

function fieldChoice(block, f) {
  var select = el("select", { class: "inp f-choice" });
  (f.options || []).forEach(function (opt) {
    select.appendChild(el("option", { value: opt, text: opt }));
  });
  select.value = block.params[f.key] == null ? "" : String(block.params[f.key]);
  if (select.selectedIndex < 0 && select.options.length) select.selectedIndex = 0;
  select.addEventListener("change", function () {
    block.params[f.key] = select.value;
    markDirty();
  });
  return wrapField(f.label || f.key, enhanceSelect(select), f.help);
}

/* --------------------------------------------------------------------------
   kind: "blocks" -- a nested block list living inside one param.

   The row only carries a counter; the list itself is edited in its own modal,
   built on the same row renderer as the builder (see openBlocksEditor).
   -------------------------------------------------------------------------- */
function fieldBlocks(block, f) {
  if (!Array.isArray(block.params[f.key])) block.params[f.key] = [];

  var btn = el("button", { class: "blocksbtn", type: "button" });
  function label() {
    var list = block.params[f.key] || [];
    btn.textContent = (f.label || "Blocks") + " (" + list.length + ")";
    btn.classList.toggle("filled", list.length > 0);
    btn.title = list.length
      ? "Edit the " + list.length + " block(s) that run when this one fails"
      : "No fallback blocks yet — click to add some";
  }
  label();
  btn.addEventListener("click", function (e) {
    e.preventDefault();
    openBlocksEditor(block, f, label);
  });

  var node = wrapField(f.label || f.key, btn, f.help);
  node._syncField = label;
  return node;
}

function fieldModifiers(block, f) {
  var current = Array.isArray(block.params[f.key]) ? block.params[f.key].slice() : [];
  var wrap = el("div", { class: "mods" });
  MODIFIERS.forEach(function (mod) {
    var on = current.indexOf(mod) >= 0;
    var btn = el("button", { class: "mod" + (on ? " on" : ""), text: mod });
    btn.addEventListener("click", function () {
      var list = Array.isArray(block.params[f.key]) ? block.params[f.key].slice() : [];
      var at = list.indexOf(mod);
      if (at >= 0) list.splice(at, 1); else list.push(mod);
      block.params[f.key] = list;
      btn.classList.toggle("on", at < 0);
      markDirty();
    });
    wrap.appendChild(btn);
  });
  return wrapField(f.label || f.key, wrap, f.help);
}

function fieldRegion(block, f) {
  var value = Array.isArray(block.params[f.key]) ? block.params[f.key].slice() : null;
  var group = el("div", { class: "inline-group" });
  var inputs = [];
  var empty = el("span", { class: "region-null", text: "full target" });

  ["x", "y", "w", "h"].forEach(function (axis, i) {
    var input = el("input", { class: "inp f-region-num", type: "number", placeholder: axis });
    input.value = value ? value[i] : "";
    input.addEventListener("input", function () {
      var next = [0, 0, 0, 0];
      var anySet = false;
      inputs.forEach(function (inp, j) {
        next[j] = toInt(inp.value, 0);
        if (inp.value !== "") anySet = true;
      });
      block.params[f.key] = anySet ? next : null;
      empty.classList.toggle("hidden", anySet);
      markDirty();
    });
    inputs.push(input);
    group.appendChild(input);
  });
  empty.classList.toggle("hidden", !!value);
  group.appendChild(empty);

  var pick = el("button", { class: "pickbtn", title: "Drag a rectangle on a capture of the target" },
    [icon("i-target", "ic-xs"), el("span", { text: "Pick" })]);
  pick.addEventListener("click", function () {
    openRegionPicker(block.params[f.key]).then(function (rect) {
      if (rect === undefined) return;                  /* cancelled */
      block.params[f.key] = rect;
      inputs.forEach(function (inp, j) { inp.value = rect ? rect[j] : ""; });
      empty.classList.toggle("hidden", !!rect);
      markDirty();
    });
  });
  group.appendChild(pick);
  return wrapField(f.label || f.key, group, f.help);
}

function fieldColor(block, f) {
  var value = block.params[f.key] || "#ffffff";
  var swatch = el("span", { class: "swatch", style: "background:" + value });
  var hex = el("input", { class: "inp f-color-hex", type: "text", spellcheck: "false" });
  hex.value = value;

  function apply(next) {
    block.params[f.key] = next;
    hex.value = next;
    swatch.style.background = next;
    markDirty();
  }
  hex.addEventListener("input", function () {
    var v = hex.value.trim();
    block.params[f.key] = v;
    if (/^#[0-9a-fA-F]{6}$/.test(v)) swatch.style.background = v;
    markDirty();
  });

  var pick = el("button", { class: "pickbtn", title: "Pick a colour from the screen" },
    [icon("i-target", "ic-xs"), el("span", { text: "Pick" })]);
  pick.addEventListener("click", function () {
    pickColor().then(function (result) {
      if (result && result.color) apply(result.color);
    });
  });
  return wrapField(f.label || f.key, el("div", { class: "inline-group" }, [swatch, hex, pick]), f.help);
}

/* --------------------------------------------------------------------------
   kind: "template" -- one of the saved images.

   A button that says which image is picked, opening a thumbnail grid. Typing
   the name into a bare text box (what this used to be) meant the only way to
   know whether "play_btn" was the right one was to go and look at it on the
   Images screen -- and a typo silently produced a block that could never
   match anything.
   -------------------------------------------------------------------------- */
function fieldTemplate(block, f) {
  var btn = el("button", { class: "tplbtn", type: "button" });
  var thumb = el("span", { class: "tplbtn-thumb" });
  var name = el("span", { class: "tplbtn-name" });
  btn.appendChild(thumb);
  btn.appendChild(name);

  function label() {
    var value = String(block.params[f.key] == null ? "" : block.params[f.key]).trim();
    name.textContent = value || "choose image…";
    btn.classList.toggle("empty", !value);
    btn.title = value ? "Image: " + value + " — click to change" : "No image chosen — click to pick one";
    thumb.innerHTML = "";
    if (!value) return;
    templateThumb(value).then(function (uri) {
      /* A slow thumb must not repaint a button that has moved on since. */
      if (String(block.params[f.key] || "").trim() !== value) return;
      thumb.innerHTML = "";
      if (uri) thumb.appendChild(el("img", { src: uri, alt: value }));
    });
  }
  label();

  btn.addEventListener("click", function (e) {
    e.preventDefault();
    openTemplatePicker(block.params[f.key]).then(function (chosen) {
      if (chosen === undefined) return;                     /* cancelled */
      block.params[f.key] = chosen || "";
      label();
      markDirty();
    });
  });

  var node = wrapField(f.label || f.key, btn, f.help);
  node._syncField = label;
  return node;
}

function fieldRecording(block, f) {
  var select = el("select", { class: "inp f-recording" });
  function fill() {
    var value = block.params[f.key] == null ? "" : String(block.params[f.key]);
    select.innerHTML = "";
    select.appendChild(el("option", { value: "", text: "— none —" }));
    state.recordings.forEach(function (name) {
      select.appendChild(el("option", { value: name, text: name }));
    });
    if (value && state.recordings.indexOf(value) < 0) {
      select.appendChild(el("option", { value: value, text: value + " (missing)" }));
    }
    select.value = value;
  }
  fill();
  select.addEventListener("change", function () {
    block.params[f.key] = select.value;
    markDirty();
  });
  /* The list of recordings changes behind the app's back (Record screen,
     deletions); rebuilding it as the dropdown opens is what keeps this row
     from offering a recording that is no longer there. */
  return wrapField(f.label || f.key, enhanceSelect(select, { beforeOpen: fill }), f.help);
}

function coordPickButton(block, ctx) {
  var btn = el("button", { class: "pickbtn", title: "Click anywhere on screen to set X and Y" },
    [icon("i-target", "ic-xs"), el("span", { text: "Pick" })]);
  btn.addEventListener("click", function () {
    if (ctx && ctx.phase) state.focusedCoord = { phase: ctx.phase, id: block.id };
    pickPointInto(block, ctx);
  });
  return wrapField("Coords", btn);
}

async function pickPointInto(block, ctx) {
  var point = await pickPoint();
  if (!point || !point.ok) return;
  block.params.x = point.x;
  block.params.y = point.y;
  if (ctx) { ctx.rerender(); ctx.changed(); }
  else { renderPhases(); markDirty(); }
}

/* ==========================================================================
   11. KEY CAPTURE
   ========================================================================== */
function keyNameFrom(event) {
  var k = event.key;
  if (!k) return "";
  if (k === "Escape") return "escape";
  if (k === "Enter") return "enter";
  if (k === " " || k === "Spacebar") return "space";
  if (k === "Tab") return "tab";
  if (k === "Shift") return "shift";
  if (k === "Control") return "ctrl";
  if (k === "Alt") return "alt";
  if (k === "Meta" || k === "OS") return "win";
  if (k === "Backspace") return "backspace";
  if (k === "Delete") return "delete";
  if (k.indexOf("Arrow") === 0) return k.slice(5).toLowerCase();
  if (/^F\d{1,2}$/.test(k)) return k.toLowerCase();
  return k.toLowerCase();
}

function beginKeyCapture(btn, onCaptured) {
  if (state.keyCapture) state.keyCapture.cancel();
  var previous = btn.textContent;
  btn.classList.add("capturing");
  btn.textContent = "press a key...";

  function finish(name) {
    window.removeEventListener("keydown", onKey, true);
    window.removeEventListener("mousedown", onMouse, true);
    btn.classList.remove("capturing");
    state.keyCapture = null;
    if (name) onCaptured(name);
    else btn.textContent = previous;
  }
  function onKey(e) {
    e.preventDefault();
    e.stopPropagation();
    finish(keyNameFrom(e));
  }
  function onMouse(e) {
    if (e.target === btn) return;
    finish(null);
  }
  state.keyCapture = { cancel: function () { finish(null); } };
  window.addEventListener("keydown", onKey, true);
  window.addEventListener("mousedown", onMouse, true);
}

/* ==========================================================================
   12. DRAG AND DROP (palette -> phase, row -> row)
   ========================================================================== */
var dropIndicator = null;

function getIndicator() {
  if (!dropIndicator) dropIndicator = el("div", { class: "drop-line" });
  return dropIndicator;
}
function removeIndicator() {
  if (dropIndicator && dropIndicator.parentNode) dropIndicator.parentNode.removeChild(dropIndicator);
  $$(".blocklist").forEach(function (l) { l.classList.remove("drag-over"); });
}

function positionIndicator(list, clientY) {
  var line = getIndicator();
  var rows = $$(".block-row", list);
  var before = null;
  for (var i = 0; i < rows.length; i++) {
    var box = rows[i].getBoundingClientRect();
    if (clientY < box.top + box.height / 2) { before = rows[i]; break; }
  }
  if (before) list.insertBefore(line, before);
  else list.appendChild(line);
}

function indicatorIndex(list) {
  var index = 0;
  var kids = list.children;
  for (var i = 0; i < kids.length; i++) {
    if (kids[i] === dropIndicator) return index;
    if (kids[i].classList.contains("block-row")) index++;
  }
  return index;
}

function acceptsDrop(ctx, payload) {
  if (!payload) return false;
  /* Neither a new chip nor an existing row ever jumps between a phase and a
     nested editor: both carry the scope of the list they came from. */
  if (payload.kind === "new") {
    return !!ctx.allowNew && (!payload.scope || payload.scope === ctx.scope);
  }
  return payload.scope === ctx.scope;
}

function wireDropTarget(list, ctx) {
  list.addEventListener("dragover", function (e) {
    if (!acceptsDrop(ctx, state.dragPayload)) return;
    e.preventDefault();
    try { e.dataTransfer.dropEffect = state.dragPayload.kind === "new" ? "copy" : "move"; } catch (err) { /* ignore */ }
    list.classList.add("drag-over");
    positionIndicator(list, e.clientY);
  });
  list.addEventListener("dragleave", function (e) {
    if (e.relatedTarget && list.contains(e.relatedTarget)) return;
    list.classList.remove("drag-over");
  });
  list.addEventListener("drop", function (e) {
    e.preventDefault();
    var payload = state.dragPayload;
    var index = indicatorIndex(list);
    removeIndicator();
    state.dragPayload = null;
    if (!acceptsDrop(ctx, payload)) return;
    performDrop(payload, ctx, index);
  });
}

function performDrop(payload, ctx, index) {
  var target = ctx.list();
  if (payload.kind === "new") {
    var block = makeBlock(payload.type);
    if (!block.type) return;
    target.splice(clamp(index, 0, target.length), 0, block);
  } else {
    var source = payload.from.list();
    var from = -1;
    for (var i = 0; i < source.length; i++) if (source[i].id === payload.id) { from = i; break; }
    if (from < 0) return;
    var moved = source.splice(from, 1)[0];
    if (source === target && from < index) index--;
    target.splice(clamp(index, 0, target.length), 0, moved);
    if (payload.from.rerender !== ctx.rerender) payload.from.rerender();
  }
  ctx.rerender();
  ctx.changed();
}

/* ==========================================================================
   13. MACRO IO + DEBOUNCED AUTOSAVE
   ========================================================================== */
function setSaveHint(text, saved) {
  var hint = $("#saveHint");
  if (!hint) return;
  hint.textContent = text || "";
  hint.classList.toggle("saved", !!saved);
}

function markDirty() {
  if (state.dirtySink) { state.dirtySink(); return; }
  setSaveHint(state.currentName ? "unsaved" : "not saved yet", false);
  debounce("saveTimer", 800, function () {
    if (!state.currentName) return;
    autosave();
  });
}

async function autosave() {
  var result = await apiQ("save_macro", state.currentName, currentMacro());
  if (result && result.macros) state.macros = result.macros;
  setSaveHint(result ? "saved" : "save failed", !!result);
}

async function saveMacroClicked() {
  var name = ($("#macroName").value || "").trim();
  if (!name) {
    name = await askText("Save macro as", "", "Letters, numbers, spaces, - and _ only.");
    if (!name) return;
    $("#macroName").value = name;
  }
  var result = await api("save_macro", name, currentMacro());
  if (!result) return;
  state.currentName = result.name || name;
  $("#macroName").value = state.currentName;
  state.macro.name = state.currentName;
  if (result.macros) state.macros = result.macros;
  setSaveHint("saved", true);
  toast("Macro '" + state.currentName + "' saved", "ok");
}

function setMacro(macro, name) {
  var phases = (macro && macro.phases) || {};
  adoptIds(phases.setup);
  adoptIds(phases.loop);
  state.macro = {
    name: name || (macro && macro.name) || "",
    phases: {
      setup: normalizeList(phases.setup, false),
      loop: normalizeList(phases.loop, false)
    }
  };
  state.currentName = state.macro.name || "";
  var nameInput = $("#macroName");
  if (nameInput) nameInput.value = state.currentName;
  renderPhases();
}

async function loadMacroNamed(name) {
  var macro = await api("load_macro", name);
  if (!macro) return;
  setMacro(macro, macro.name || name);
  setSaveHint("loaded", true);
  toast("Loaded '" + (macro.name || name) + "'");
}

async function refreshMacroList() {
  var list = await apiQ("list_macros");
  if (Array.isArray(list)) state.macros = list;
  renderMacroMenu();
}

function renderMacroMenu() {
  var menu = $("#macroMenu");
  if (!menu) return;
  menu.innerHTML = "";
  if (!state.macros.length) {
    menu.appendChild(el("div", { class: "menu-empty", text: "No saved macros yet" }));
    return;
  }
  state.macros.forEach(function (name) {
    var item = el("button", { class: "menu-item", text: name });
    item.addEventListener("click", function () {
      menu.classList.add("hidden");
      loadMacroNamed(name);
    });
    menu.appendChild(item);
  });
}

async function newMacro() {
  var yes = await askConfirm("Start a new macro?", "Unsaved changes to the current macro are lost.");
  if (!yes) return;
  state.macro = { name: "", phases: { setup: [], loop: [] } };
  state.currentName = "";
  $("#macroName").value = "";
  renderPhases();
  setSaveHint("");
}

async function deleteMacro() {
  var name = state.currentName || ($("#macroName").value || "").trim();
  if (!name) { toast("Nothing to delete", "err"); return; }
  var yes = await askConfirm("Delete '" + name + "'?", "The saved file is removed from the Templates folder.");
  if (!yes) return;
  var result = await api("delete_macro", name);
  if (!result) return;
  if (result.macros) state.macros = result.macros;
  renderMacroMenu();
  if (result.ok) {
    toast("Deleted '" + name + "'", "ok");
    state.currentName = "";
    $("#macroName").value = "";
  } else {
    toast("Could not delete '" + name + "'", "err");
  }
}

async function importMacro() {
  var result = await api("import_macro_file");
  if (!result) return;
  if (!result.ok) {
    if (result.reason !== "cancelled") toast("Import failed: " + result.reason, "err");
    return;
  }
  var macro = result.macro || {};
  setMacro(macro, macro.name || "");
  setSaveHint("imported — press Save to keep it");
  toast("Macro imported", "ok");
}

async function exportMacro() {
  var name = state.currentName || ($("#macroName").value || "").trim() || "macro";
  var result = await api("export_macro_file", currentMacro(), name);
  if (!result) return;
  if (result.ok) toast("Exported to " + result.path, "ok");
  else if (result.reason !== "cancelled") toast("Export failed: " + result.reason, "err");
}

/* ==========================================================================
   14. RECORD SCREEN
   ========================================================================== */
function recOptions() {
  return {
    keepMoves: !!($("#optRecordMove") && $("#optRecordMove").checked),
    minGap: toInt($("#optMinGap") ? $("#optMinGap").value : 60, 60)
  };
}

function setRecordingUI(active) {
  state.recording = active;
  var btn = $("#btnRecToggle");
  if (btn) btn.classList.toggle("recording", active);
  var label = $("#recBtnLabel");
  if (label) label.textContent = active ? "Stop Recording" : "Start Recording";
  var pill = $("#recPill");
  if (pill) pill.classList.toggle("hidden", !active);

  clearInterval(state.recTimer);
  if (active) {
    state.recTimer = setInterval(async function () {
      var count = await apiQ("recording_event_count");
      if (typeof count === "number") setRecCount(count);
    }, 400);
  }
}

function setRecCount(n) {
  var node = $("#recCount");
  if (node) node.textContent = String(n);
}

async function toggleRecording() {
  if (state.recording) {
    var stopped = await api("stop_recording");
    if (!stopped) return;
    if (!stopped.ok) { toast("Not recording", "err"); return; }
    setRecCount(stopped.count || 0);
    state.previewSource = { kind: "pending" };
    setPreview(stopped.preview || []);
    showScreen("record");
  } else {
    var started = await api("start_recording");
    if (!started) return;
    if (!started.ok) { toast("Cannot record: " + started.reason, "err"); return; }
    setRecCount(0);
    setPreview([]);
    showScreen("record");
  }
}

function setPreview(blocks) {
  state.preview = Array.isArray(blocks) ? blocks : [];
  state.previewChecked = state.preview.map(function () { return true; });
  renderPreview();
}

function paramSummary(block) {
  var params = block.params || {};
  return Object.keys(params).map(function (k) {
    var v = params[k];
    if (v === null || v === undefined || v === "") return null;
    if (Array.isArray(v)) { if (!v.length) return null; v = "[" + v.join(",") + "]"; }
    return k + "=" + v;
  }).filter(Boolean).join("  ");
}

function renderPreview() {
  var host = $("#previewList");
  if (!host) return;
  host.innerHTML = "";
  if (!state.preview.length) {
    host.appendChild(el("div", {
      class: "empty",
      text: "Nothing recorded yet. Press Start Recording, do the actions, then stop."
    }));
    return;
  }
  state.preview.forEach(function (block, index) {
    var spec = specFor(block.type);
    var check = el("input", { type: "checkbox" });
    check.checked = !!state.previewChecked[index];
    check.addEventListener("change", function () { state.previewChecked[index] = check.checked; });
    host.appendChild(el("label", {
      class: "prow", style: "--row-color:" + colorOf(spec ? spec.color : "")
    }, [
      check,
      el("span", { class: "prow-ord", text: "#" + (index + 1) }),
      el("span", { class: "prow-type", text: spec ? spec.label : block.type }),
      el("span", { class: "prow-params", text: paramSummary(block) })
    ]));
  });
}

async function refreshPreview() {
  var opts = recOptions();
  var blocks;
  if (state.previewSource.kind === "recording") {
    blocks = await apiQ("load_recording_blocks", state.previewSource.name, opts.keepMoves, opts.minGap);
  } else {
    blocks = await apiQ("preview_pending_blocks", opts.keepMoves, opts.minGap);
  }
  if (Array.isArray(blocks)) setPreview(blocks);
}

function selectedPreviewBlocks() {
  return state.preview.filter(function (_, i) { return state.previewChecked[i]; });
}

/* The escape hatch: the ticked rows go in one by one, as they always did. */
function insertPreviewInto(phase) {
  var picked = selectedPreviewBlocks();
  if (!picked.length) { toast("Select at least one block first", "err"); return; }
  var blocks = normalizeList(JSON.parse(JSON.stringify(picked)), true);
  phaseArray(phase).push.apply(phaseArray(phase), blocks);
  renderPhases();
  markDirty();
  showScreen("builder");
  toast(blocks.length + " block" + (blocks.length === 1 ? "" : "s") + " added to " + phase, "ok");
}

/* --------------------------------------------------------------------------
   The default insert: ONE Play Recording block. A recording is a single thing
   the user did, so it belongs in the macro as a single row -- and its actions
   stay editable through that row rather than being scattered across the phase.
   An unsaved take has to be named first: a playback block can only point at a
   recording that exists on disk.
   -------------------------------------------------------------------------- */
async function insertRecordingInto(phase) {
  var name = "";

  if (state.previewSource.kind === "recording" && state.previewSource.name) {
    name = state.previewSource.name;
  } else {
    if (!state.preview.length) {
      toast("Nothing to insert — record something first", "err");
      return;
    }
    var wanted = await askText("Name this recording",
                               "", "Saved in the Recordings folder, then inserted as one block.");
    if (!wanted) return;
    var saved = await api("save_pending_recording", wanted);
    if (!saved) return;
    if (!saved.ok) {
      toast("Could not save the recording: " + (saved.reason || "unknown"), "err");
      return;
    }
    name = saved.name;
    if (Array.isArray(saved.recordings)) state.recordings = saved.recordings;
    renderRecordings();
    state.previewSource = { kind: "recording", name: name };
  }

  addPlaybackBlock(name, phase);
}

async function saveRecordingClicked() {
  var name = await askText("Save recording as", "", "Stored in the Recordings folder.");
  if (!name) return;
  var result = await api("save_pending_recording", name);
  if (!result) return;
  if (!result.ok) { toast("Could not save: " + result.reason, "err"); return; }
  if (result.recordings) state.recordings = result.recordings;
  renderRecordings();
  toast("Recording saved as '" + result.name + "'", "ok");
}

async function refreshRecordings() {
  var list = await apiQ("list_recordings");
  if (Array.isArray(list)) state.recordings = list;
  renderRecordings();
}

function renderRecordings() {
  var host = $("#recordingsList");
  if (!host) return;
  host.innerHTML = "";
  if (!state.recordings.length) {
    host.appendChild(el("div", { class: "empty", text: "No saved recordings." }));
    return;
  }
  state.recordings.forEach(function (name) {
    // "Edit" opens it as editable blocks; "Use" drops in a single Play
    // Recording block that replays it verbatim, timing included. Two
    // genuinely different ways to reuse a recording, so both are one click.
    var load = el("button", { class: "btn btn-sm", text: "Edit" });
    attachTip(load, "Edit",
              "Разбирает запись на отдельные блоки и показывает их в "
              + "предпросмотре ниже. Оттуда можно снять лишние галочки и "
              + "вставить в Setup или Loop.");
    load.addEventListener("click", async function () {
      var opts = recOptions();
      var blocks = await api("load_recording_blocks", name, opts.keepMoves, opts.minGap);
      if (!Array.isArray(blocks)) return;
      state.previewSource = { kind: "recording", name: name };
      setPreview(blocks);
      toast("Loaded '" + name + "' — pick rows, then insert");
    });

    var use = el("button", { class: "btn btn-sm primary", text: "Use" });
    attachTip(use, "Use",
              "Добавляет в Loop один блок «Play Recording», который "
              + "проигрывает эту запись целиком с её собственным таймингом.");
    use.addEventListener("click", function () {
      addPlaybackBlock(name, "loop");
    });

    var play = el("button", { class: "iconbtn", text: "▶" });
    attachTip(play, "Run now",
              "Проигрывает запись прямо сейчас, ничего не добавляя в макрос. "
              + "Остановить — Stop внизу или горячей клавишей.");
    play.addEventListener("click", async function () {
      var block = makeBlock("playback");
      block.params.recording = name;
      var result = await api("run_single_block", block);
      if (result && result.ok) toast("Playing '" + name + "'");
      else if (result) toast("Could not play: " + (result.reason || "?"), "err");
    });

    var del = el("button", { class: "iconbtn danger", title: "Delete" }, [icon("i-trash", "ic-xs")]);
    del.addEventListener("click", async function () {
      var yes = await askConfirm("Delete recording '" + name + "'?", "The .json file is removed.");
      if (!yes) return;
      var result = await api("delete_recording", name);
      if (!result) return;
      if (result.recordings) state.recordings = result.recordings;
      renderRecordings();
    });

    host.appendChild(el("div", { class: "rec-item" }, [
      el("span", { class: "rec-item-name", text: name, title: name }),
      load, use, play, del
    ]));
  });
}

function addPlaybackBlock(name, phase) {
  var block = makeBlock("playback");
  block.params.recording = name;
  phaseArray(phase).push(block);
  renderPhases();
  markDirty();
  showScreen("builder");
  toast("Added a Play Recording block for '" + name + "'", "ok");
}

async function discardPending() {
  var result = await api("discard_pending_recording");
  if (!result) return;
  state.previewSource = { kind: "pending" };
  setPreview([]);
  setRecCount(0);
  toast("Pending recording discarded");
}

/* ==========================================================================
   14b. RECORDING ACTIONS EDITOR  (the modal behind "Edit actions")
   ========================================================================== */
var recEdit = { name: "", blocks: [], dirty: false, open: false };

var recEditCtx = {
  scope: "recedit",
  phase: null,
  allowNew: false,          /* the palette stays out: this list is a recording */
  full: false,
  list: function () { return recEdit.blocks; },
  rerender: function () { renderRecEditList(); },
  changed: function () { recEdit.dirty = true; }
};

function renderRecEditList() {
  var host = $("#recEditList");
  if (!host) return;
  host.innerHTML = "";
  if (!recEdit.blocks.length) {
    host.appendChild(el("div", {
      class: "empty",
      text: "No actions left. “Reset to original” brings back what was recorded."
    }));
    return;
  }
  recEdit.blocks.forEach(function (block, index) {
    host.appendChild(renderBlockRow(block, index, recEditCtx));
  });
}

function applyRecEditData(fallbackName, data) {
  recEdit.name = data.name || fallbackName;
  /* re-ided: the modal shares the drag machinery with the builder, which
     matches rows by id, and a recording's ids are its own namespace. */
  recEdit.blocks = normalizeList(data.blocks, true);
  recEdit.dirty = false;
  var sub = $("#recEditSub");
  if (sub) {
    sub.textContent = data.edited
      ? "edited"
      : "derived from " + (data.event_count || 0) + " recorded events";
  }
  renderRecEditList();
}

function setRecEditEnabled(on) {
  /* Save and Reset stay disabled until the action list has actually loaded.
     Otherwise a failed load left an EMPTY list under an armed Save button,
     and one click wrote that empty list over the recording's real actions. */
  ["#btnRecEditSave", "#btnRecEditReset"].forEach(function (sel) {
    var btn = $(sel);
    if (btn) btn.disabled = !on;
  });
}

async function openRecordingEditor(name) {
  var overlay = $("#recEditModal");
  if (!overlay) return;
  recEdit.open = true;
  recEdit.loaded = false;
  recEdit.name = name;
  recEdit.blocks = [];
  recEdit.dirty = false;
  recEdit.token = (recEdit.token || 0) + 1;
  var token = recEdit.token;
  $("#recEditTitle").textContent = 'Actions in "' + name + '"';
  $("#recEditSub").textContent = "loading…";
  $("#recEditList").innerHTML = "";
  setRecEditEnabled(false);
  overlay.classList.remove("hidden");
  /* field editors call markDirty(); while this modal owns the screen those
     edits are the recording's, not the macro's. */
  state.dirtySink = recEditCtx.changed;

  var data = await api("get_recording_actions", name);
  /* A late response must not rebind a modal that was closed or reopened on a
     different recording in the meantime. */
  if (token !== recEdit.token || !recEdit.open) return;
  if (!data || !data.ok) {
    $("#recEditSub").textContent = data && data.reason === "missing"
      ? "this recording no longer exists"
      : "could not load this recording";
    toast(data && data.reason === "missing"
      ? "Recording '" + name + "' no longer exists"
      : "Could not load '" + name + "'", "err");
    return;
  }
  recEdit.loaded = true;
  setRecEditEnabled(true);
  applyRecEditData(name, data);
}

function closeRecordingEditor() {
  var overlay = $("#recEditModal");
  if (overlay) overlay.classList.add("hidden");
  recEdit.open = false;
  recEdit.loaded = false;
  recEdit.blocks = [];
  recEdit.dirty = false;
  recEdit.token = (recEdit.token || 0) + 1;   /* invalidate any in-flight load */
  state.dirtySink = null;
}

async function saveRecordingActions() {
  if (!recEdit.name || !recEdit.loaded) return;
  var payload = JSON.parse(JSON.stringify(recEdit.blocks));
  if (!payload.length) {
    var sure = await askConfirm("Remove every action from '" + recEdit.name + "'?",
      "The recording will still exist, but playing it will do nothing. "
      + "“Reset to original” can bring the recorded actions back.");
    if (!sure || !recEdit.open) return;
  }
  var result = await api("save_recording_actions", recEdit.name, payload);
  if (!result) return;
  if (!result.ok) {
    toast("Could not save actions: " + (result.reason || "unknown"), "err");
    return;
  }
  toast(payload.length + " action" + (payload.length === 1 ? "" : "s")
        + " saved in '" + (result.name || recEdit.name) + "'", "ok");
  closeRecordingEditor();
}

async function resetRecordingActions() {
  if (!recEdit.name || !recEdit.loaded) return;
  var name = recEdit.name;
  var token = recEdit.token;
  var yes = await askConfirm("Reset '" + name + "' to the original?",
    "The edited action list is dropped and the actions are re-derived from the events that were actually recorded.");
  /* The editor can be closed (Escape) while the confirmation is up. Acting
     afterwards would reset a recording whose editor is no longer on screen. */
  if (!yes || !recEdit.open || recEdit.token !== token) return;
  var data = await api("reset_recording_actions", name);
  if (!data || !data.ok || !recEdit.open || recEdit.token !== token) {
    if (data && !data.ok) toast("Could not reset: " + (data.reason || "unknown"), "err");
    return;
  }
  applyRecEditData(name, data);
  toast("Back to the original actions", "ok");
}

/* ==========================================================================
   14c. NESTED BLOCK LIST EDITOR  (the modal behind a "blocks" field)

   Modelled on the recording editor above, with two deliberate differences:
   the list being edited lives inside a macro block (so "saving" is nothing
   more than having mutated it, plus markDirty), and adding blocks IS allowed
   -- which is why this modal carries its own palette.

   A fallback list can itself hold a Vision block with its own fallback list,
   so the open lists are a stack and the modal shows the top of it.
   ========================================================================== */
var blocksEdit = { stack: [], open: false, onLabel: null };

var blocksEditCtx = {
  scope: "blocksedit",
  phase: null,
  allowNew: true,
  full: false,
  list: function () {
    var top = blocksEdit.stack[blocksEdit.stack.length - 1];
    return top ? top.list : [];
  },
  rerender: function () { renderBlocksEditList(); },
  changed: function () {
    renderBlocksEditHead();
    markDirty();
  }
};

function renderBlocksEditHead() {
  var top = blocksEdit.stack[blocksEdit.stack.length - 1];
  var title = $("#blocksEditTitle");
  var sub = $("#blocksEditSub");
  if (!top) return;
  if (title) title.textContent = top.title;
  if (sub) {
    var count = top.list.length;
    sub.textContent = (blocksEdit.stack.length > 1 ? blocksEdit.stack.length + " levels deep · " : "")
      + count + (count === 1 ? " block" : " blocks");
  }
}

function renderBlocksEditList() {
  var host = $("#blocksEditList");
  if (!host) return;
  var list = blocksEditCtx.list();
  host.innerHTML = "";
  if (!list.length) {
    host.appendChild(el("div", { class: "dropzone", text: "drag blocks here" }));
  } else {
    list.forEach(function (block, index) {
      host.appendChild(renderBlockRow(block, index, blocksEditCtx));
    });
  }
  renderBlocksEditHead();
}

/* `f` is the catalog field; `onLabel` refreshes the counter on the row that
   opened this. The array is edited IN PLACE, so there is nothing to save. */
function openBlocksEditor(block, f, onLabel) {
  var overlay = $("#blocksEditModal");
  if (!overlay) return;
  if (!Array.isArray(block.params[f.key])) block.params[f.key] = [];

  var spec = specFor(block.type);
  blocksEdit.stack.push({
    list: block.params[f.key],
    title: (f.label || "Blocks") + " — " + (spec ? spec.label : block.type)
  });
  if (blocksEdit.stack.length === 1) {
    blocksEdit.onLabel = onLabel || null;
    blocksEdit.open = true;
    overlay.classList.remove("hidden");
    buildPalette($("#blocksEditPalette"), {
      scope: "blocksedit",
      hint: "Перетащи в список или кликни, чтобы добавить в конец.",
      onPick: function (chosen) {
        blocksEditCtx.list().push(makeBlock(chosen.type));
        renderBlocksEditList();
        blocksEditCtx.changed();
      }
    });
  }
  renderBlocksEditList();
}

/* Closes one level; the modal itself only goes away with the last one. */
function closeBlocksEditor() {
  if (!blocksEdit.open) return;
  blocksEdit.stack.pop();
  if (blocksEdit.stack.length) {
    renderBlocksEditList();
    return;
  }
  var overlay = $("#blocksEditModal");
  if (overlay) overlay.classList.add("hidden");
  blocksEdit.open = false;
  if (blocksEdit.onLabel) blocksEdit.onLabel();
  blocksEdit.onLabel = null;
  /* The counters on every row are derived from these lists, so a rebuild is
     the cheapest way to make all of them right again. */
  renderPhases();
}

async function clearBlocksEditor() {
  var list = blocksEditCtx.list();
  if (!list.length) return;
  var yes = await askConfirm("Remove all " + list.length + " block(s)?",
    "The fallback list is emptied. The block will then simply carry on when it fails.");
  if (!yes || !blocksEdit.open) return;
  list.length = 0;
  renderBlocksEditList();
  blocksEditCtx.changed();
}

/* ==========================================================================
   14d. WEBHOOK -- per-row attachment preview
   ========================================================================== */
async function previewWebhookSource(block) {
  var overlay = $("#hookPreviewModal");
  var body = $("#hookPreviewBody");
  var detail = $("#hookPreviewDetail");
  if (!overlay) return;

  var params = block.params || {};
  body.innerHTML = "";
  body.appendChild(el("div", { class: "empty", text: "Rendering…" }));
  detail.textContent = "—";
  overlay.classList.remove("hidden");

  var result = await api("preview_webhook_source",
                         params.source || "none",
                         params.region || null,
                         params.template || "");
  /* A late answer must not repaint a modal the user already dismissed. */
  if (overlay.classList.contains("hidden")) return;
  body.innerHTML = "";
  if (!result || !result.ok) {
    detail.textContent = "failed";
    body.appendChild(el("div", { class: "empty", text: webhookReason(result && result.reason) }));
    return;
  }
  detail.textContent = result.detail || "";
  if (result.image) {
    body.appendChild(el("img", { src: result.image, alt: "attachment preview" }));
  } else {
    body.appendChild(el("div", { class: "empty", text: "No image — this block would send text only." }));
  }
}

/* ==========================================================================
   15. IMAGES SCREEN
   ========================================================================== */
var imgSel = null;
var regionSel = null;

var ZOOM_MIN = 0.25;
var ZOOM_MAX = 8;
var ZOOM_STEP = 1.25;

/* --------------------------------------------------------------------------
   Capture viewer: pan/zoom plus the crop rectangle.

   Everything the caller ever sees is in SOURCE-image pixels. The zoom lives
   entirely in the canvas' CSS size, and every screen<->source conversion goes
   through getBoundingClientRect(), which already folds in the zoom and the
   scroll position -- so a crop dragged at 400% and scrolled halfway down
   lands on exactly the same pixels as one dragged at "Fit".
   -------------------------------------------------------------------------- */
function createRectSelector(holder, stage, canvas, box, onChange, onZoom) {
  var natural = { w: 1, h: 1 };
  var rect = null;
  var dragging = null;
  var scale = 1;

  function applyScale() {
    canvas.style.width = Math.max(1, natural.w * scale) + "px";
    canvas.style.height = Math.max(1, natural.h * scale) + "px";
    if (onZoom) onZoom(scale);
  }
  function metrics() {
    var cr = canvas.getBoundingClientRect();
    return {
      cr: cr,
      sx: natural.w / (cr.width || 1),
      sy: natural.h / (cr.height || 1)
    };
  }
  function draw() {
    if (!rect || rect[2] < 1 || rect[3] < 1) {
      box.classList.add("hidden");
      if (onChange) onChange(null);
      return;
    }
    var m = metrics();
    /* the box is a child of the stage, which is exactly the canvas box, so
       these are plain canvas-local offsets -- scrolling cannot shift them */
    box.classList.remove("hidden");
    box.style.left = (rect[0] / m.sx) + "px";
    box.style.top = (rect[1] / m.sy) + "px";
    box.style.width = (rect[2] / m.sx) + "px";
    box.style.height = (rect[3] / m.sy) + "px";
    if (onChange) onChange(rect.slice());
  }
  function toSource(clientX, clientY) {
    var m = metrics();
    return [
      clamp(Math.round((clientX - m.cr.left) * m.sx), 0, natural.w),
      clamp(Math.round((clientY - m.cr.top) * m.sy), 0, natural.h)
    ];
  }
  function fitScale() {
    var maxW = Math.max(40, holder.clientWidth - 2);
    var maxH = Math.max(40, holder.clientHeight - 2);
    return clamp(Math.min(1, maxW / natural.w, maxH / natural.h), ZOOM_MIN, ZOOM_MAX);
  }
  /* clientX/clientY optional: when given, that screen point stays put */
  function setScale(next, clientX, clientY) {
    next = clamp(next, ZOOM_MIN, ZOOM_MAX);
    if (Math.abs(next - scale) < 1e-9) { applyScale(); draw(); return; }
    var anchor = null;
    if (clientX !== undefined && clientY !== undefined) {
      var cr = canvas.getBoundingClientRect();
      anchor = {
        u: (clientX - cr.left) / scale,     /* source px under the cursor */
        v: (clientY - cr.top) / scale,
        x: clientX, y: clientY
      };
    }
    scale = next;
    applyScale();
    if (anchor) {
      var after = canvas.getBoundingClientRect();
      holder.scrollLeft += (after.left + anchor.u * scale) - anchor.x;
      holder.scrollTop += (after.top + anchor.v * scale) - anchor.y;
    }
    draw();
  }
  function onMove(e) {
    if (!dragging) return;
    /* Released outside the window (or over a native menu) never delivers the
       mouseup, and the selection then followed the cursor for ever. */
    if (!(e.buttons & 1)) { onUp(); return; }
    var p = toSource(e.clientX, e.clientY);
    rect = [
      Math.min(dragging[0], p[0]), Math.min(dragging[1], p[1]),
      Math.abs(p[0] - dragging[0]), Math.abs(p[1] - dragging[1])
    ];
    draw();
  }
  function onUp() {
    if (!dragging) return;
    dragging = null;
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
    draw();
  }

  /* --------------------------------------------------------------------
     Middle button = hand tool.

     It used to start a crop selection like any other button, so the only
     way to reach the far side of a zoomed capture was the scrollbars. The
     pan never touches `rect`: it moves the viewport, and the selection box
     is positioned in canvas-local coordinates, so it stays exactly where it
     was drawn at any zoom.
     -------------------------------------------------------------------- */
  var panning = null;

  function endPan() {
    if (!panning) return;
    panning = null;
    holder.classList.remove("panning");
    window.removeEventListener("mousemove", onPanMove, true);
    window.removeEventListener("mouseup", onPanUp, true);
    window.removeEventListener("blur", endPan);
    document.removeEventListener("mouseleave", endPan);
  }
  function onPanMove(e) {
    if (!panning) return;
    /* bit 2 is the middle button; it is gone when the release happened
       somewhere this document never hears about. */
    if (!(e.buttons & 4)) { endPan(); return; }
    holder.scrollLeft -= e.clientX - panning.x;
    holder.scrollTop -= e.clientY - panning.y;
    panning.x = e.clientX;
    panning.y = e.clientY;
  }
  function onPanUp(e) {
    if (e.button !== undefined && e.button !== 1 && (e.buttons & 4)) return;
    endPan();
  }
  function beginPan(e) {
    if (panning) return;
    panning = { x: e.clientX, y: e.clientY };
    holder.classList.add("panning");
    window.addEventListener("mousemove", onPanMove, true);
    window.addEventListener("mouseup", onPanUp, true);
    window.addEventListener("blur", endPan);
    document.addEventListener("mouseleave", endPan);
  }

  /* On the holder, not the canvas: panning has to work from the empty gutter
     around a small capture too. */
  holder.addEventListener("mousedown", function (e) {
    if (e.button !== 1) return;
    e.preventDefault();          /* also kills Chromium's autoscroll cursor */
    beginPan(e);
  });
  holder.addEventListener("auxclick", function (e) {
    if (e.button === 1) e.preventDefault();
  });

  canvas.addEventListener("mousedown", function (e) {
    if (e.button !== 0) return;                 /* middle pans, right is free */
    e.preventDefault();
    dragging = toSource(e.clientX, e.clientY);
    rect = [dragging[0], dragging[1], 0, 0];
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  });
  /* --------------------------------------------------------------------
     Wheel: plain scrolls the image, shift scrolls it sideways, ctrl zooms.

     Zooming on a bare wheel was the wrong default -- the whole point of
     zooming in is to then move around, and every scroll gesture fought the
     zoom instead. The scroll is applied by hand rather than left to the
     browser so shift+wheel behaves the same everywhere; when the image has
     nothing to scroll in that direction the event is left alone so the
     screen behind can still scroll.
     -------------------------------------------------------------------- */
  holder.addEventListener("wheel", function (e) {
    if (natural.w <= 1) return;

    if (e.ctrlKey) {
      if (!e.deltaY) return;
      e.preventDefault();
      setScale(scale * (e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP), e.clientX, e.clientY);
      return;
    }

    var horizontal = e.shiftKey || (Math.abs(e.deltaX) > Math.abs(e.deltaY));
    var amount = horizontal ? (e.deltaX || e.deltaY) : e.deltaY;
    if (!amount) return;
    var room = horizontal
      ? holder.scrollWidth - holder.clientWidth
      : holder.scrollHeight - holder.clientHeight;
    if (room <= 1) return;                       /* nothing to scroll here */
    e.preventDefault();
    if (horizontal) holder.scrollLeft += amount;
    else holder.scrollTop += amount;
  }, { passive: false });
  window.addEventListener("resize", function () {
    // Skipped while the canvas is not laid out (its screen is hidden, or the
    // region modal is closed): getBoundingClientRect is all zeros then, and
    // redrawing collapsed the selection box to a sub-pixel speck that stayed
    // wrong until the next drag.
    if (!rect || !canvas.offsetParent) return;
    draw();
  });

  return {
    setNatural: function (w, h) {
      natural = { w: w || 1, h: h || 1 };
      scale = fitScale();
      applyScale();
      holder.scrollLeft = 0;
      holder.scrollTop = 0;
    },
    /* A bare click (no drag) leaves a zero-size rect. Reporting it as a real
       selection stored region [x,y,0,0], which the readout meanwhile
       described as "full target" -- two different answers to the same
       question. Degenerate selections are simply no selection. */
    get: function () {
      if (!rect || rect[2] < 1 || rect[3] < 1) return null;
      return rect.slice();
    },
    set: function (r) { rect = r ? r.slice() : null; draw(); },
    clear: function () { rect = null; draw(); },
    redraw: draw,
    zoomIn: function () { setScale(scale * ZOOM_STEP); },
    zoomOut: function () { setScale(scale / ZOOM_STEP); },
    zoomAt: function (next, clientX, clientY) { setScale(next, clientX, clientY); },
    fit: function () { setScale(fitScale()); },
    getScale: function () { return scale; }
  };
}

function zoomReadoutBinder(id) {
  return function (scale) {
    var node = $(id);
    if (node) node.textContent = Math.round(scale * 100) + "%";
  };
}

/* Sizing is the selector's job now (it owns the zoom); this just paints. */
function drawCapture(canvas, dataUri, width, height) {
  return new Promise(function (resolve) {
    var img = new Image();
    img.onload = function () {
      canvas.width = width || img.naturalWidth;
      canvas.height = height || img.naturalHeight;
      var ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      resolve(true);
    };
    img.onerror = function () { resolve(false); };
    img.src = dataUri;
  });
}

async function captureForImages() {
  var canvas = $("#imgCanvas");
  $("#imgCanvasEmpty").classList.remove("hidden");
  $("#imgCanvasEmpty").textContent = "Capturing...";
  var result = await api("capture_target_preview");
  if (!result || !result.ok) {
    $("#imgCanvasEmpty").textContent = "Capture failed" + (result && result.reason ? " (" + result.reason + ")" : "");
    return false;
  }
  var ok = await drawCapture(canvas, result.image, result.width, result.height);
  if (!ok) { $("#imgCanvasEmpty").textContent = "Could not decode the capture"; return false; }
  $("#imgCanvasEmpty").classList.add("hidden");
  imgSel.setNatural(result.width, result.height);
  imgSel.clear();
  $("#captureHint").textContent = result.width + " x " + result.height
    + " — drag a rectangle to crop. The large view is where the cropping happens.";
  return true;
}

/* The Capture button's whole job: take the shot, then hand it straight to the
   large view. Cropping in the inline strip is a few hundred pixels of image
   and a mouse that has to be steady to a source pixel; the panel stays as the
   preview of what is loaded, but it is no longer where the work is done. */
async function captureAndCrop() {
  var ok = await captureForImages();
  if (!ok) return false;
  if (!bigView.open) openImgLargeView();
  return true;
}

/* Re-shoot: same capture, but the crop is already spoken for -- it goes back
   to the template the card belongs to, either over the primary image or
   alongside it as another variant. */
async function reshootTemplate(name) {
  if (bigView.open) closeImgLargeView();
  var nameInput = $("#imgName");
  if (nameInput) nameInput.value = name;
  bigView.reshoot = name;
  var ok = await captureForImages();
  if (!ok) { bigView.reshoot = ""; return; }
  openImgLargeView();
}

async function recaptureInBigView() {
  if (!bigView.open) return;
  await captureForImages();
}

/* --------------------------------------------------------------------------
   Large crop view.

   The capture column is MOVED into the modal rather than mirrored into a
   second canvas: one canvas, one selector, one set of source-pixel maths.
   Nothing about the crop coordinates changes -- only how much room the same
   selector gets to work in.
   -------------------------------------------------------------------------- */
var bigView = { open: false, reshoot: "", pick: null };

/* Re-shooting is the same modal with a different promise attached to it, so
   the head, the hint and the two save buttons say which of the two it is. */
function applyBigViewMode() {
  var reshoot = bigView.reshoot;
  var tag = $("#bigViewTag");
  var save = $("#btnBigViewSave");
  var variant = $("#btnBigViewVariant");
  var nameInput = $("#bigViewName");
  var hint = $("#bigViewHint");

  if (tag) {
    tag.classList.toggle("hidden", !reshoot);
    tag.textContent = reshoot ? "re-shooting “" + reshoot + "”" : "";
  }
  if (save) save.textContent = reshoot ? "Replace main image" : "Save as new";
  if (variant) variant.textContent = reshoot ? "Add as variant" : "Save as variant";
  if (nameInput) {
    nameInput.value = ($("#imgName") && $("#imgName").value) || "";
    nameInput.readOnly = !!reshoot;
    nameInput.classList.toggle("locked", !!reshoot);
  }
  if (hint) {
    hint.textContent = reshoot
      ? "“Replace main image” overwrites the image itself; “Add as variant” keeps it and adds another look."
      : "Left-drag crops · middle-drag pans · ctrl+wheel zooms.";
  }
}

function openImgLargeView() {
  var overlay = $("#bigViewModal");
  var col = $("#imgCanvasCol");
  var slot = $("#bigViewSlot");
  if (!overlay || !col || !slot || bigView.open) return false;
  if (!$("#imgCanvasEmpty").classList.contains("hidden")) {
    toast("Capture the target first", "err");
    return false;
  }
  bigView.open = true;
  slot.appendChild(col);
  overlay.classList.remove("hidden");
  applyBigViewMode();
  /* Laid out only now, so the fit has to wait until this change has landed.
     A timer rather than requestAnimationFrame, for the same reason applyTheme
     uses one: rAF never runs while the window is hidden or unpainted, and the
     capture would then sit at the small panel's zoom the next time it shows. */
  setTimeout(function () { imgSel.fit(); }, 0);
  return true;
}

function closeImgLargeView() {
  var overlay = $("#bigViewModal");
  var col = $("#imgCanvasCol");
  var wrap = $("#imgCaptureWrap");
  if (!bigView.open) return;
  bigView.open = false;
  bigView.reshoot = "";
  if (overlay) overlay.classList.add("hidden");
  if (col && wrap) wrap.insertBefore(col, wrap.firstChild);
  /* Re-fitting an off-screen column measures a zero-size holder and collapses
     the zoom to the minimum, so only do it when the panel is really visible. */
  setTimeout(function () { if (col && col.offsetParent) imgSel.fit(); }, 0);
  /* A picker waiting on "capture new" gets its answer even when the user
     closes the view without saving anything. */
  var pending = bigView.pick;
  bigView.pick = null;
  if (pending) pending(undefined);
  applyBigViewMode();
}

async function saveCrop(asVariant) {
  /* While re-shooting the name is not the user's to change -- that is the
     whole point of the button they pressed. */
  var name = (bigView.reshoot || ($("#imgName").value || "")).trim();
  if (!name) {
    toast("Give the image a name first", "err");
    var field = bigView.open ? $("#bigViewName") : $("#imgName");
    if (field) field.focus();
    return null;
  }
  var rect = imgSel.get();
  if (!rect || rect[2] < 2 || rect[3] < 2) { toast("Drag a rectangle on the capture first", "err"); return null; }

  var reshot = !!bigView.reshoot;
  var result = await api("save_template_crop", name, rect[0], rect[1], rect[2], rect[3], !!asVariant);
  if (!result) return null;
  if (!result.ok) { toast("Save failed: " + result.reason, "err"); return null; }

  /* The bytes behind this name just changed, so every cached thumbnail of it
     is now a picture of the old look. */
  invalidateThumbs();
  var nameInput = $("#imgName");
  if (nameInput) nameInput.value = name;
  if (Array.isArray(result.templates)) {
    state.templates = result.templates;
    renderTemplates();
  } else {
    refreshTemplates();
  }
  toast(reshot
    ? (asVariant ? "Variant added to '" + name + "'" : "Replaced the image for '" + name + "'")
    : (asVariant ? "Variant" : "Image") + " '" + name + "' saved", "ok");

  /* Cleared BEFORE the close, which would otherwise resolve it as cancelled. */
  var pending = bigView.pick;
  bigView.pick = null;
  if (bigView.open) closeImgLargeView();
  if (pending) pending(name);
  return name;
}

/* --------------------------------------------------------------------------
   Thumbnails are a bridge round-trip each, and the rows that show them are
   re-rendered on every drag, duplicate and delete -- so they are fetched once
   per name and kept until something rewrites the Assets folder.
   -------------------------------------------------------------------------- */
var thumbCache = {};

function invalidateThumbs() { thumbCache = {}; }

function templateThumb(name, filename) {
  var key = String(name) + "|" + String(filename || "");
  if (!thumbCache[key]) thumbCache[key] = apiQ("get_template_thumb", String(name), String(filename || ""));
  return thumbCache[key];
}

async function refreshTemplates() {
  var list = await apiQ("list_templates");
  if (Array.isArray(list)) state.templates = list;
  invalidateThumbs();
  renderTemplates();
}

function templateNamed(name) {
  var wanted = String(name || "").trim();
  for (var i = 0; i < state.templates.length; i++) {
    if (state.templates[i].name === wanted) return state.templates[i];
  }
  return null;
}

function renderTemplates() {
  var host = $("#templateGrid");
  if (!host) return;
  host.innerHTML = "";
  if (!state.templates.length) {
    host.appendChild(el("div", { class: "empty", text: "No images yet. Capture the target and crop one." }));
    return;
  }
  state.templates.forEach(function (tpl) {
    var thumb = el("div", { class: "tpl-thumb" }, [el("span", { class: "hint", text: "…" })]);
    templateThumb(tpl.name, (tpl.files && tpl.files[0]) || "").then(function (uri) {
      thumb.innerHTML = "";
      if (uri) thumb.appendChild(el("img", { src: uri, alt: tpl.name }));
      else thumb.appendChild(el("span", { class: "hint", text: "no preview" }));
    });

    var result = el("span", { class: "tpl-result" });
    var testBtn = el("button", { class: "btn btn-sm", text: "Test" });
    attachTip(testBtn, "Test",
              "Look for this image on the target right now, at the "
              + "“Test confidence” set above this grid.");
    testBtn.addEventListener("click", async function () {
      result.textContent = "…";
      result.className = "tpl-result";
      var threshold = toNum(state.settings.default_threshold, 0.88);
      var found = await api("test_template", tpl.name, threshold);
      if (!found) { result.textContent = "error"; result.className = "tpl-result bad"; return; }
      if (found.ok) {
        result.textContent = "found " + found.cx + "," + found.cy + " (" + Number(found.score).toFixed(3) + ")";
        result.className = "tpl-result ok";
      } else {
        result.textContent = "not found";
        result.className = "tpl-result bad";
      }
    });

    /* The one repair for "the button I saved looks different now": shoot the
       target again and drop the new crop onto this same name. */
    var shootBtn = el("button", { class: "btn btn-sm" }, [icon("i-camera", "ic-xs"), el("span", { text: "Re-shoot" })]);
    attachTip(shootBtn, "Re-shoot",
              "Capture the target again and crop it in the large view.\n\n"
              + "Saving then writes back to '" + tpl.name + "': either over the "
              + "main image, or as one more variant — the large view offers both.");
    shootBtn.addEventListener("click", function () { reshootTemplate(tpl.name); });

    var delBtn = el("button", { class: "iconbtn danger", title: "Delete image and variants" }, [icon("i-trash", "ic-xs")]);
    delBtn.addEventListener("click", async function () {
      var yes = await askConfirm("Delete '" + tpl.name + "'?",
        "Removes " + tpl.count + " file" + (tpl.count === 1 ? "" : "s") + " from the Assets folder.");
      if (!yes) return;
      var res = await api("delete_template", tpl.name, "");
      if (!res) return;
      if (Array.isArray(res.templates)) state.templates = res.templates;
      invalidateThumbs();
      renderTemplates();
    });

    host.appendChild(el("div", { class: "tpl-card" }, [
      thumb,
      el("div", { class: "tpl-name", text: tpl.name, title: tpl.name }),
      el("div", { class: "tpl-meta" }, [
        el("span", { text: tpl.count + " variant" + (tpl.count === 1 ? "" : "s") }),
        el("span", { class: "flex-spacer" }), result
      ]),
      el("div", { class: "tpl-actions" }, [testBtn, shootBtn, el("span", { class: "flex-spacer" }), delBtn])
    ]));
  });
}

/* ==========================================================================
   15b. IMAGE PICKER  (the modal behind every "template" field)

   Resolves with a name, "" for "no image", or undefined when cancelled -- the
   same three-way answer the region picker gives, so a cancel never writes.
   ========================================================================== */
var tplPick = { resolve: null, current: "", filter: "" };

function renderTplPickGrid() {
  var host = $("#tplPickGrid");
  if (!host) return;
  var query = tplPick.filter.toLowerCase();
  var rows = state.templates.filter(function (t) {
    return !query || String(t.name).toLowerCase().indexOf(query) >= 0;
  });

  host.innerHTML = "";
  if (!rows.length) {
    host.appendChild(el("div", {
      class: "empty",
      text: state.templates.length
        ? "No saved image matches “" + tplPick.filter + "”."
        : "No saved images yet — press “＋ Capture new”."
    }));
    return;
  }

  rows.forEach(function (tpl) {
    var thumb = el("div", { class: "tpl-thumb" }, [el("span", { class: "hint", text: "…" })]);
    templateThumb(tpl.name, (tpl.files && tpl.files[0]) || "").then(function (uri) {
      thumb.innerHTML = "";
      if (uri) thumb.appendChild(el("img", { src: uri, alt: tpl.name }));
      else thumb.appendChild(el("span", { class: "hint", text: "no preview" }));
    });

    var card = el("button", {
      class: "tplpick-card" + (tpl.name === tplPick.current ? " on" : ""),
      type: "button", title: tpl.name
    }, [
      thumb,
      el("div", { class: "tpl-name", text: tpl.name }),
      el("div", { class: "tpl-meta" }, [
        el("span", { text: tpl.count + " variant" + (tpl.count === 1 ? "" : "s") })
      ])
    ]);
    card.addEventListener("click", function () { closeTemplatePicker(tpl.name); });
    host.appendChild(card);
  });
}

function closeTemplatePicker(value) {
  var overlay = $("#tplPickModal");
  if (overlay) overlay.classList.add("hidden");
  var resolve = tplPick.resolve;
  tplPick.resolve = null;
  if (resolve) resolve(value);
}

function openTemplatePicker(current) {
  return new Promise(function (resolve) {
    var overlay = $("#tplPickModal");
    if (!overlay) { resolve(undefined); return; }
    /* Opening a second one over the first would strand the first promise. */
    closeTemplatePicker(undefined);

    tplPick.resolve = resolve;
    tplPick.current = String(current == null ? "" : current).trim();
    tplPick.filter = "";

    var filter = $("#tplPickFilter");
    if (filter) filter.value = "";
    var readout = $("#tplPickCurrent");
    if (readout) readout.textContent = tplPick.current || "none";

    overlay.classList.remove("hidden");
    renderTplPickGrid();
    if (filter) filter.focus();

    /* The Assets folder changes behind the app's back, so the grid is what is
       on disk right now, not what the last visit to the Images screen saw. */
    apiQ("list_templates").then(function (list) {
      if (!Array.isArray(list)) return;
      state.templates = list;
      if (tplPick.resolve === resolve) renderTplPickGrid();
    });
  });
}

/* "＋ Capture new" leaves the picker and lands in the capture flow; whatever
   gets saved there is handed back as the answer, so one gesture goes from an
   empty field to a cropped image. */
async function templatePickerCaptureNew() {
  var resolve = tplPick.resolve;
  tplPick.resolve = null;
  closeTemplatePicker(undefined);
  if (!resolve) return;

  var ok = await captureForImages();
  if (!ok) { resolve(undefined); return; }
  bigView.pick = resolve;
  if (!openImgLargeView()) { bigView.pick = null; resolve(undefined); }
}

/* ==========================================================================
   16. PICKING -- point, colour, region
   ========================================================================== */
function showPickOverlay(title) {
  var overlay = $("#pickOverlay");
  $("#pickTitle").textContent = title || "Click anywhere to capture a coordinate";
  overlay.classList.remove("hidden");
  var left = 30;
  $("#pickTimer").textContent = String(left);
  clearInterval(showPickOverlay.timer);
  showPickOverlay.timer = setInterval(function () {
    left = Math.max(0, left - 1);
    $("#pickTimer").textContent = String(left);
  }, 1000);
}
function hidePickOverlay() {
  clearInterval(showPickOverlay.timer);
  $("#pickOverlay").classList.add("hidden");
}

async function pickPoint() {
  if (state.picking) { toast("Already waiting for a click", "err"); return null; }
  state.picking = true;
  showPickOverlay("Click anywhere to capture a coordinate");
  var result = await api("pick_point");
  hidePickOverlay();
  state.picking = false;
  if (!result) return null;
  if (!result.ok) {
    toast(result.reason === "timeout" ? "Pick timed out" : "Pick failed: " + result.reason, "err");
    return null;
  }
  return result;
}

async function pickColor() {
  if (state.picking) { toast("Already waiting for a click", "err"); return null; }
  state.picking = true;
  showPickOverlay("Click anywhere to sample a colour");
  var result = await api("pick_color");
  hidePickOverlay();
  state.picking = false;
  if (!result) return null;
  if (!result.ok) {
    toast(result.reason === "timeout" ? "Pick timed out" : "Pick failed: " + result.reason, "err");
    return null;
  }
  return result;
}

/* Resolves with [x,y,w,h], null (cleared) or undefined (cancelled). */
function openRegionPicker(current) {
  return new Promise(async function (resolve) {
    var overlay = $("#regionModal");
    var canvas = $("#regionCanvas");
    var empty = $("#regionCanvasEmpty");

    empty.classList.remove("hidden");
    empty.textContent = "Capturing target...";
    overlay.classList.remove("hidden");
    /* Wiped up front, and Apply disabled until a capture arrives: the
       selector is reused between opens, so a failed capture used to leave
       the PREVIOUS block's rectangle sitting there for Apply to return. */
    if (regionSel) regionSel.clear();
    var applyBtn = $("#btnRegionApply");
    if (applyBtn) applyBtn.disabled = true;

    function done(value) {
      if (applyBtn) applyBtn.disabled = false;
      overlay.classList.add("hidden");
      $("#btnRegionApply").removeEventListener("click", apply);
      $("#btnRegionClear").removeEventListener("click", clear);
      $("#btnRegionCancel").removeEventListener("click", cancel);
      $("#btnRegionClose").removeEventListener("click", cancel);
      resolve(value);
    }
    function apply() { done(regionSel.get()); }
    function clear() { done(null); }
    function cancel() { done(undefined); }

    $("#btnRegionApply").addEventListener("click", apply);
    $("#btnRegionClear").addEventListener("click", clear);
    $("#btnRegionCancel").addEventListener("click", cancel);
    $("#btnRegionClose").addEventListener("click", cancel);

    var result = await api("capture_target_preview");
    if (!result || !result.ok) {
      empty.textContent = "Capture failed" + (result && result.reason ? " (" + result.reason + ")" : "");
      return;
    }
    var ok = await drawCapture(canvas, result.image, result.width, result.height);
    if (!ok) { empty.textContent = "Could not decode the capture"; return; }
    empty.classList.add("hidden");
    regionSel.setNatural(result.width, result.height);
    regionSel.set(Array.isArray(current) && current.length === 4 ? current : null);
    if (applyBtn) applyBtn.disabled = false;
  });
}

/* ==========================================================================
   17. SETTINGS SCREEN
   ========================================================================== */
async function refreshWindows() {
  var list = await apiQ("list_windows");
  if (Array.isArray(list)) state.windows = list;
  renderWindows();
}

function renderWindows() {
  var host = $("#winList");
  if (!host) return;
  var query = (($("#winSearch") && $("#winSearch").value) || "").toLowerCase().trim();
  var currentHwnd = state.status.hwnd;
  host.innerHTML = "";

  var rows = state.windows.filter(function (w) {
    if (!query) return true;
    return (String(w.title) + " " + String(w.process)).toLowerCase().indexOf(query) >= 0;
  });
  if (!rows.length) {
    host.appendChild(el("div", { class: "empty", text: query ? "No window matches that filter." : "No windows found. Press Refresh." }));
    return;
  }
  rows.forEach(function (w) {
    // A minimized window reports no client area at all; showing "0x0" reads
    // as broken. Attaching to it restores it, so say what it actually is.
    var sizeText = w.minimized ? "minimized" : (w.width + "x" + w.height);
    var item = el("div", {
      class: "win-item" + (currentHwnd && Number(currentHwnd) === Number(w.hwnd) ? " selected" : "")
        + (w.minimized ? " win-min" : ""),
      title: w.minimized ? w.title + " (minimized — attaching will restore it)" : w.title
    }, [
      el("span", { class: "win-proc", text: w.process || "?" }),
      el("span", { class: "win-title", text: w.title }),
      el("span", { class: "win-size", text: sizeText })
    ]);
    item.addEventListener("click", async function () {
      var result = await api("set_target", w.hwnd, w.title);
      if (!result) return;
      if (!result.ok) { toast("That window is gone — press Refresh", "err"); refreshWindows(); return; }
      state.status.hwnd = w.hwnd;
      renderWindows();
      applyTargetInfo(result);
      pollStatus();
    });
    host.appendChild(item);
  });
}

function applyTargetInfo(info) {
  if (!info) return;
  var dot = $("#targetDot");
  var title = $("#targetTitle");
  var alive = !!info.alive;
  if (dot) dot.className = "dot " + (alive ? "dot-on" : "dot-off");
  if (title) title.textContent = info.title || (info.mode === "screen" ? "Whole screen" : "No target selected");

  var ind = $("#attachInd");
  if (ind) {
    ind.innerHTML = "";
    ind.appendChild(el("span", { class: "dot " + (alive ? "dot-on" : "dot-off") }));
    ind.appendChild(el("span", {
      text: !alive ? "window gone"
        : info.minimized ? "attached · minimized"
        : "attached · " + (info.width || 0) + "x" + (info.height || 0)
    }));
  }
}

async function refreshTargetInfo() {
  var info = await apiQ("get_target_info");
  if (!info) return;
  state.status.hwnd = info.hwnd;
  applyTargetInfo(info);
  renderWindows();
}

function renderHotkeys() {
  var host = $("#hotkeyGrid");
  if (!host) return;
  host.innerHTML = "";
  HOTKEYS.forEach(function (hk) {
    var value = state.settings[hk.key] || "";
    var btn = el("button", { class: "keybtn" + (value ? "" : " empty"), text: value || "unbound" });
    btn.addEventListener("click", function () {
      beginKeyCapture(btn, async function (name) {
        btn.textContent = name;
        btn.classList.remove("empty");
        var merged = await api("set_setting", hk.key, name);
        if (merged) { state.settings = merged; toast(hk.label + " → " + name, "ok"); }
      });
    });
    host.appendChild(el("div", { class: "hotkey-cell" }, [
      el("span", { class: "flab", text: hk.label }), btn
    ]));
  });
}

/* ==========================================================================
   17b. THEMES
   Applying one is a single attribute: every colour in style.css is a token,
   and a theme is nothing but a block of token overrides.
   ========================================================================== */
function themeExists(name) {
  return THEMES.some(function (t) { return t.key === name; });
}

/* --------------------------------------------------------------------------
   Swapping the theme is one attribute -- with one catch worth the ceremony.

   Chromium does not re-resolve a property that is BOTH derived from a custom
   property and covered by a `transition`: change --on-ok under a rule reading
   `color: var(--on-ok)` on an element whose `transition` includes colour, and
   it keeps painting the OLD colour until something else invalidates it.
   Nearly every interactive control here transitions its colour, so switching
   theme left the buttons, the rail and the control bar in the previous
   palette while the panels around them had already changed.

   Turning transitions off for the single frame the swap happens in sidesteps
   it entirely -- and an instant repaint is what a theme switch should look
   like anyway, rather than every control on screen cross-fading at once.
   -------------------------------------------------------------------------- */
function applyTheme(name) {
  var key = themeExists(name) ? name : DEFAULT_THEME;
  var root = document.documentElement;
  if (root.getAttribute("data-theme") === key) return key;

  root.classList.add("theme-swap");
  root.setAttribute("data-theme", key);
  void root.offsetWidth;              /* force the restyle while transitions are off */
  /* A timer, not requestAnimationFrame: rAF does not run while the window is
     hidden or unpainted, and the class MUST come back off -- leaving it on
     would kill every hover transition in the app. Re-armed on each swap so
     clicking through the swatches quickly cannot strand it either. */
  clearTimeout(applyTheme.timer);
  applyTheme.timer = setTimeout(function () {
    root.classList.remove("theme-swap");
  }, 40);
  return key;
}

function renderThemes() {
  var host = $("#themeGrid");
  if (!host) return;
  var current = applyTheme(state.settings.theme);
  host.innerHTML = "";

  THEMES.forEach(function (theme) {
    var bars = el("div", { class: "theme-swatch-bar" },
      theme.groups.map(function (c) { return el("span", { style: "background:" + c }); }));
    var swatch = el("div", {
      class: "theme-swatch",
      style: "background:" + theme.bg
    }, [
      el("div", { class: "theme-swatch-top" }, [
        el("span", { class: "theme-dot", style: "background:" + theme.accent }),
        el("span", { class: "theme-line", style: "background:" + theme.panel }),
        el("span", { class: "theme-line", style: "background:" + theme.text + ";opacity:.55;max-width:26px" })
      ]),
      bars
    ]);

    var card = el("button", {
      class: "theme-card" + (theme.key === current ? " on" : ""), type: "button"
    }, [
      swatch,
      el("div", { class: "theme-name" }, [
        el("span", { text: theme.label }),
        el("span", { class: "theme-tick", text: theme.key === current ? "✓" : "" })
      ])
    ]);
    card.addEventListener("click", async function () {
      applyTheme(theme.key);
      state.settings.theme = theme.key;
      renderThemes();
      var merged = await api("set_setting", "theme", theme.key);
      if (merged) state.settings = merged;
      toast("Theme: " + theme.label, "ok");
    });
    host.appendChild(card);
  });
}

/* ==========================================================================
   17c. DISCORD WEBHOOK SETTINGS
   The real URL never crosses the bridge in this direction -- get_webhook_
   settings only ever hands back a masked form, and this screen only ever
   shows that.
   ========================================================================== */
var hookState = { enabled: false, configured: false, masked: "", username: "" };

function renderWebhook() {
  var card = $("#webhookCard");
  if (!card) return;
  var enabled = !!hookState.enabled;
  var configured = !!hookState.configured;

  card.classList.toggle("off", !enabled);
  $("#hookEnabled").checked = enabled;
  $("#hookMasked").textContent = hookState.masked || "no URL saved";
  var user = $("#hookUser");
  if (user && document.activeElement !== user) user.value = hookState.username || "";

  var state_ = $("#hookState");
  var text = $("#hookStateText");
  state_.className = "hook-state" + (enabled && configured ? " armed" : (enabled ? " warn" : ""));
  text.textContent = !enabled
    ? "Sending is OFF — nothing is ever sent to Discord, not even by a Send Webhook block."
    : configured
      ? "Sending is ON — Send Webhook blocks and the test button will post to Discord."
      : "Sending is on, but no valid URL is saved yet, so nothing can be sent.";

  var ind = $("#hookInd");
  ind.innerHTML = "";
  ind.appendChild(el("span", { class: "dot " + (configured ? (enabled ? "dot-on" : "dot-idle") : "dot-off") }));
  ind.appendChild(el("span", {
    text: !configured ? "not configured" : (enabled ? "armed" : "configured · off")
  }));

  $("#btnHookTest").disabled = !(enabled && configured);
  $("#btnHookClear").disabled = !configured;
}

function applyWebhookResult(result) {
  if (!result) return false;
  if (result.ok === false) return false;
  hookState = {
    enabled: !!result.enabled,
    configured: !!result.configured,
    masked: result.masked || "",
    username: result.username || ""
  };
  renderWebhook();
  return true;
}

async function refreshWebhook() {
  applyWebhookResult(await apiQ("get_webhook_settings"));
}

async function saveWebhookUrl() {
  var input = $("#hookUrl");
  var url = (input.value || "").trim();
  var username = ($("#hookUser").value || "").trim() || "Macro Studio";
  if (!url) { toast(WEBHOOK_REASONS.empty, "err"); input.focus(); return; }

  var result = await api("save_webhook_settings", url, null, username);
  if (!result) return;
  if (result.ok === false) {
    $("#hookHint").textContent = webhookReason(result.reason);
    toast(webhookReason(result.reason), "err");
    return;
  }
  input.value = "";
  $("#hookHint").textContent = "Saved. Only the masked form is ever shown again.";
  applyWebhookResult(result);
  toast("Webhook URL saved", "ok");
}

async function toggleWebhookEnabled() {
  var on = $("#hookEnabled").checked;
  /* null for url and username: they are not being changed, and the URL is a
     secret the frontend does not hold in the first place. */
  var result = await api("save_webhook_settings", null, on, null);
  if (!result || result.ok === false) { await refreshWebhook(); return; }
  applyWebhookResult(result);
  toast(on ? "Webhook sending enabled" : "Webhook sending disabled", on ? "ok" : "");
}

async function clearWebhookUrl() {
  var yes = await askConfirm("Remove the saved webhook URL?",
    "The URL is deleted and sending is switched off. You will have to paste it again to use it.");
  if (!yes) return;
  var result = await api("clear_webhook_url");
  if (!result) return;
  applyWebhookResult(result);
  $("#hookHint").textContent = "URL removed. Nothing can be sent until a new one is saved.";
  toast("Webhook URL removed", "ok");
}

async function testWebhook() {
  var btn = $("#btnHookTest");
  btn.disabled = true;
  btn.textContent = "Sending…";
  var result = await api("test_webhook");
  btn.textContent = "Send test message";
  renderWebhook();
  if (!result) return;
  if (result.ok) toast("Test message delivered", "ok");
  else toast("Test failed: " + webhookReason(result.reason), "err");
}

function applySettingsToUI() {
  var s = state.settings || {};
  var delay = toInt(s.action_delay_ms, 0);
  $("#setActionDelay").value = delay;
  $("#valActionDelay").textContent = delay + " ms";

  var threshold = toNum(s.default_threshold, 0.88);
  $("#setThreshold").value = threshold;
  $("#valThreshold").textContent = threshold.toFixed(2);

  $("#setRecordMove").checked = !!s.record_mouse_move;
  $("#optRecordMove").checked = !!s.record_mouse_move;
  syncLoopControls();
  renderHotkeys();
  renderThemes();
}

async function setSetting(key, value) {
  var merged = await api("set_setting", key, value);
  if (merged) state.settings = merged;
  return merged;
}

async function runHealthCheck() {
  var host = $("#healthList");
  host.innerHTML = "";
  host.appendChild(el("div", { class: "empty", text: "Running..." }));
  var rows = await api("run_health_check");
  host.innerHTML = "";
  if (!Array.isArray(rows)) {
    host.appendChild(el("div", { class: "empty", text: "Health check failed to run." }));
    return;
  }
  rows.forEach(function (row) {
    host.appendChild(el("div", { class: "health-row" }, [
      el("span", { class: "dot " + (row.ok ? "dot-on" : "dot-off") }),
      el("span", { class: "health-name", text: row.name }),
      el("span", { class: "health-detail", text: row.detail, title: row.detail })
    ]));
  });
}

function renderEnvRow(bootstrap) {
  var host = $("#envRow");
  if (!host) return;
  host.innerHTML = "";
  var tags = [
    ["version", bootstrap.version || state.version],
    ["OCR", bootstrap.ocr_engine || "unknown"],
    ["display scale", (bootstrap.display_scale || 100) + "%"]
  ];
  tags.forEach(function (t) {
    host.appendChild(el("span", { class: "env-tag", html: t[0] + " <b>" + String(t[1]) + "</b>" }));
  });
}

async function resetSettings() {
  var yes = await askConfirm("Reset all settings?", "Hotkeys, delays, thresholds and the target selection go back to defaults.");
  if (!yes) return;
  var merged = await api("reset_settings");
  if (!merged) return;
  state.settings = merged;
  applySettingsToUI();          /* re-applies the theme and the loop controls */
  renderPhases();               /* the Loop header carries two of them */
  refreshTargetInfo();
  refreshWebhook();             /* a reset also drops the saved webhook URL */
  toast("Settings reset", "ok");
}

/* ==========================================================================
   18. CONTROL BAR + STATUS POLLING
   ========================================================================== */
async function startMacro() {
  if (state.status.running) { toast("Already running"); return; }
  var macro = currentMacro();
  if (!macro.phases.setup.length && !macro.phases.loop.length) {
    toast("Add at least one block first", "err");
    return;
  }
  var result = await api("start_macro", macro);
  if (result && result.ok === false) {
    var why = result.reason === "no_target" ? "no target window attached"
      : result.reason === "recording" ? "stop the recorder first"
        : result.reason;
    toast("Could not start: " + why, "err");
    return;
  }
  pollStatus();
}

async function stopMacro() { await api("stop_macro"); pollStatus(); }
async function togglePause() { await api("toggle_pause"); pollStatus(); }

function applyStatus(status) {
  if (!status) return;
  state.status.running = !!status.running;
  state.status.paused = !!status.paused;

  var start = $("#btnStart");
  var pause = $("#btnPause");
  var stop = $("#btnStop");
  start.disabled = !!status.running;
  pause.disabled = !status.running;
  stop.disabled = !status.running;
  pause.classList.toggle("paused", !!status.paused);
  $$("span", pause)[0].textContent = status.paused ? "Resume" : "Pause";

  var dot = $("#runDot");
  dot.className = "run-dot" + (status.running ? (status.paused ? " pause" : " on") : "");
  $("#statusAction").textContent = status.action || "Idle";
  $("#statusLoop").textContent = "loop " + (status.loop || 0);
  $("#statusMeta").textContent = status.recording
    ? "recording · " + (status.rec_count || 0) + " events"
    : (status.target ? "target: " + status.target : "no target");

  var tdot = $("#targetDot");
  var ttitle = $("#targetTitle");
  if (tdot) tdot.className = "dot " + (status.target_alive ? "dot-on" : "dot-off");
  if (ttitle) ttitle.textContent = status.target || "No target selected";

  if (!!status.recording !== state.recording) setRecordingUI(!!status.recording);
  if (status.recording) setRecCount(status.rec_count || 0);
}

async function pollStatus() {
  var status = await apiQ("get_status");
  applyStatus(status);
}

/* ==========================================================================
   19. PYTHON -> JS PUSH HANDLERS
   ========================================================================== */
function onRecordingStarted() {
  setRecordingUI(true);
  setRecCount(0);
  setPreview([]);
  state.previewSource = { kind: "pending" };
}

function onRecordingStopped() {
  setRecordingUI(false);
  refreshPreview();
}

function hotkeyStart() {
  startMacro();
}

function hotkeyRecord() {
  toggleRecording();
}

function hotkeyPick() {
  // Refused while a nested editor owns the screen: the hotkey is global (it
  // comes from Python, so the overlay cannot swallow it), and it would
  // otherwise edit a MACRO block from behind the modal -- where markDirty is
  // routed into the editor's sink, so the change is applied but never
  // autosaved and never shown as unsaved.
  if (recEdit.open) {
    toast("Close the actions editor first", "err");
    return;
  }
  var focus = state.focusedCoord;
  if (!focus) { toast("Focus an X or Y field first", "err"); return; }
  var block = findBlock(focus.phase, focus.id);
  if (!block) { toast("That block no longer exists", "err"); return; }
  pickPointInto(block, phaseCtx(focus.phase));
}

/* ==========================================================================
   19b. WINDOW CHROME

   The window is frameless, so the OS draws no buttons at all -- minimise,
   maximise and close are ours, and so is the double-click-to-maximise the
   title bar of every other window has.
   ========================================================================== */
var winMaximized = false;

function setMaximizedUI(on) {
  winMaximized = !!on;
  var btn = $("#btnMax");
  var use = $("#btnMaxIcon");
  if (use) use.setAttribute("href", winMaximized ? "#i-restore" : "#i-max");
  if (btn) btn.title = winMaximized ? "Restore down" : "Maximize";
}

async function toggleMaximize() {
  var result = await apiQ("toggle_maximize");
  /* No answer means the bridge is not there (or the call failed); flipping the
     icon anyway would show "restore" on a window that never maximised. */
  if (!result || result.ok === false) return;
  setMaximizedUI(!!result.maximized);
}

/* ==========================================================================
   20. STATIC WIRING (runs as soon as the document is parsed)
   ========================================================================== */
function wireStatic() {
  /* --- chrome ------------------------------------------------------- */
  $("#btnMin").addEventListener("click", function () { apiQ("minimize_window"); });
  $("#btnMax").addEventListener("click", toggleMaximize);
  $("#btnClose").addEventListener("click", function () { apiQ("close_window"); });
  $("#targetChip").addEventListener("click", function () { showScreen("settings"); });
  /* Double-clicking the drag region maximises, exactly like a native bar --
     but not when the double-click landed on one of the controls sitting in
     it, which have their own jobs. */
  $(".titlebar").addEventListener("dblclick", function (e) {
    if (e.target.closest("button, .target-chip")) return;
    toggleMaximize();
  });

  $$(".railbtn").forEach(function (btn) {
    btn.addEventListener("click", function () { showScreen(btn.dataset.screen); });
  });

  /* --- log panel ---------------------------------------------------- */
  var panel = $("#logPanel");
  function toggleLog() { panel.classList.toggle("collapsed"); }
  $("#btnLogToggle").addEventListener("click", function (e) { e.stopPropagation(); toggleLog(); });
  $("#logHead").addEventListener("click", function (e) {
    if (e.target.closest("button")) return;
    toggleLog();
  });
  $("#btnClearLogs").addEventListener("click", function (e) {
    e.stopPropagation();
    clearLogs();
    apiQ("clear_logs");
  });

  /* --- control bar -------------------------------------------------- */
  $("#btnStart").addEventListener("click", startMacro);
  $("#btnPause").addEventListener("click", togglePause);
  $("#btnStop").addEventListener("click", stopMacro);

  /* --- builder toolbar ---------------------------------------------- */
  $("#btnSaveMacro").addEventListener("click", saveMacroClicked);
  $("#btnNewMacro").addEventListener("click", newMacro);
  $("#btnDeleteMacro").addEventListener("click", deleteMacro);
  $("#btnImportMacro").addEventListener("click", importMacro);
  $("#btnExportMacro").addEventListener("click", exportMacro);
  $("#macroName").addEventListener("input", function () {
    state.currentName = $("#macroName").value.trim();
    markDirty();
  });

  var menu = $("#macroMenu");
  $("#btnLoadMacro").addEventListener("click", function (e) {
    e.stopPropagation();
    if (menu.classList.contains("hidden")) refreshMacroList();
    menu.classList.toggle("hidden");
  });
  document.addEventListener("click", function () { menu.classList.add("hidden"); });
  menu.addEventListener("click", function (e) { e.stopPropagation(); });

  /* a row is only draggable while its grip is held down */
  document.addEventListener("mouseup", function () {
    $$(".block-row[draggable=true]").forEach(function (row) { row.draggable = false; });
  });
  /* dropping anywhere else must not leave a stray indicator behind */
  document.addEventListener("dragend", removeIndicator);
  document.addEventListener("drop", function (e) { e.preventDefault(); removeIndicator(); });
  document.addEventListener("dragover", function (e) { e.preventDefault(); });

  /* --- record screen ------------------------------------------------ */
  $("#btnRecToggle").addEventListener("click", toggleRecording);
  $("#btnRecCancel").addEventListener("click", discardPending);
  $("#optRecordMove").addEventListener("change", function () {
    setSetting("record_mouse_move", $("#optRecordMove").checked);
    $("#setRecordMove").checked = $("#optRecordMove").checked;
    refreshPreview();
  });
  $("#optMinGap").addEventListener("input", function () {
    debounce("previewTimer", 350, refreshPreview);
  });
  $("#btnPreviewAll").addEventListener("click", function () {
    state.previewChecked = state.preview.map(function () { return true; });
    renderPreview();
  });
  $("#btnPreviewNone").addEventListener("click", function () {
    state.previewChecked = state.preview.map(function () { return false; });
    renderPreview();
  });
  /* one block for the whole take (default) vs the old row-by-row insert */
  $("#btnInsertSetup").addEventListener("click", function () { insertRecordingInto("setup"); });
  $("#btnInsertLoop").addEventListener("click", function () { insertRecordingInto("loop"); });
  $("#btnInsertSeparate").addEventListener("click", function () { insertPreviewInto("loop"); });
  $("#btnSaveRecording").addEventListener("click", saveRecordingClicked);

  /* --- recording actions editor ------------------------------------- */
  wireDropTarget($("#recEditList"), recEditCtx);
  $("#btnRecEditSave").addEventListener("click", saveRecordingActions);
  $("#btnRecEditReset").addEventListener("click", resetRecordingActions);
  $("#btnRecEditCancel").addEventListener("click", closeRecordingEditor);
  $("#btnRecEditClose").addEventListener("click", closeRecordingEditor);

  /* --- nested blocks editor ----------------------------------------- */
  wireDropTarget($("#blocksEditList"), blocksEditCtx);
  $("#btnBlocksEditDone").addEventListener("click", closeBlocksEditor);
  $("#btnBlocksEditClose").addEventListener("click", closeBlocksEditor);
  $("#btnBlocksEditClear").addEventListener("click", clearBlocksEditor);

  /* --- webhook attachment preview ----------------------------------- */
  $("#btnHookPreviewClose").addEventListener("click", function () {
    $("#hookPreviewModal").classList.add("hidden");
  });
  $("#btnHookPreviewDone").addEventListener("click", function () {
    $("#hookPreviewModal").classList.add("hidden");
  });

  /* --- images screen ------------------------------------------------ */
  imgSel = createRectSelector(
    $("#imgCanvasHolder"), $("#imgCanvasStage"), $("#imgCanvas"), $("#imgSelBox"),
    function (rect) {
      /* Two readouts, one selection: the side panel on the Images screen and
         the head of the large view, whichever the user is looking at. */
      var text = rect
        ? "x " + rect[0] + " · y " + rect[1] + " · " + rect[2] + " × " + rect[3]
        : "x 0 · y 0 · 0 × 0";
      $("#imgSelReadout").textContent = text;
      var big = $("#bigViewReadout");
      if (big) big.textContent = text;
    },
    zoomReadoutBinder("#imgZoomReadout"));
  regionSel = createRectSelector(
    $("#regionCanvasHolder"), $("#regionCanvasStage"), $("#regionCanvas"), $("#regionSelBox"),
    function (rect) {
      $("#regionReadout").textContent = rect
        ? "x " + rect[0] + " · y " + rect[1] + " · " + rect[2] + " × " + rect[3]
        : "no region — full target";
    },
    zoomReadoutBinder("#regionZoomReadout"));

  $("#btnImgZoomIn").addEventListener("click", function () { imgSel.zoomIn(); });
  $("#btnImgZoomOut").addEventListener("click", function () { imgSel.zoomOut(); });
  $("#btnImgZoomFit").addEventListener("click", function () { imgSel.fit(); });
  $("#btnRegionZoomIn").addEventListener("click", function () { regionSel.zoomIn(); });
  $("#btnRegionZoomOut").addEventListener("click", function () { regionSel.zoomOut(); });
  $("#btnRegionZoomFit").addEventListener("click", function () { regionSel.fit(); });

  $("#btnImgExpand").addEventListener("click", function () { openImgLargeView(); });
  $("#btnBigViewDone").addEventListener("click", closeImgLargeView);
  $("#btnBigViewClose").addEventListener("click", closeImgLargeView);
  $("#btnBigViewClear").addEventListener("click", function () { imgSel.clear(); });
  $("#btnBigViewReshoot").addEventListener("click", recaptureInBigView);
  $("#btnBigViewSave").addEventListener("click", function () { saveCrop(false); });
  $("#btnBigViewVariant").addEventListener("click", function () { saveCrop(true); });
  /* Two boxes, one name: the large view covers the side panel, so it carries
     its own copy of the field and mirrors it rather than owning a second
     truth. saveCrop only ever reads #imgName. */
  $("#bigViewName").addEventListener("input", function () {
    $("#imgName").value = $("#bigViewName").value;
  });
  $("#imgName").addEventListener("input", function () {
    var mirror = $("#bigViewName");
    if (mirror && !bigView.reshoot) mirror.value = $("#imgName").value;
  });

  $("#btnCaptureTarget").addEventListener("click", captureAndCrop);
  $("#btnSaveNew").addEventListener("click", function () { saveCrop(false); });
  $("#btnSaveVariant").addEventListener("click", function () { saveCrop(true); });
  $("#btnRefreshTemplates").addEventListener("click", refreshTemplates);
  $("#btnOpenAssets2").addEventListener("click", function () { apiQ("open_assets_folder"); });

  /* --- image picker -------------------------------------------------- */
  $("#tplPickFilter").addEventListener("input", function () {
    tplPick.filter = $("#tplPickFilter").value.trim();
    renderTplPickGrid();
  });
  $("#btnTplPickNone").addEventListener("click", function () { closeTemplatePicker(""); });
  $("#btnTplPickNew").addEventListener("click", templatePickerCaptureNew);
  $("#btnTplPickCancel").addEventListener("click", function () { closeTemplatePicker(undefined); });
  $("#btnTplPickClose").addEventListener("click", function () { closeTemplatePicker(undefined); });

  /* --- settings screen ---------------------------------------------- */
  $("#btnRefreshWindows").addEventListener("click", refreshWindows);
  $("#winSearch").addEventListener("input", renderWindows);
  $("#btnUseScreen").addEventListener("click", async function () {
    var result = await api("use_screen_target");
    if (result) { state.status.hwnd = 0; applyTargetInfo(result); renderWindows(); }
  });
  $("#btnFocusTarget").addEventListener("click", function () { apiQ("focus_target"); });

  $("#setActionDelay").addEventListener("input", function () {
    $("#valActionDelay").textContent = toInt($("#setActionDelay").value, 0) + " ms";
  });
  $("#setActionDelay").addEventListener("change", function () {
    setSetting("action_delay_ms", toInt($("#setActionDelay").value, 0));
  });
  /* Lives on the Images screen now, next to the Test buttons it drives -- and
     it seeds the confidence of every Vision block created from here on. */
  $("#setThreshold").addEventListener("input", function () {
    $("#valThreshold").textContent = toNum($("#setThreshold").value, 0.88).toFixed(2);
  });
  $("#setThreshold").addEventListener("change", function () {
    setSetting("default_threshold", toNum($("#setThreshold").value, 0.88));
  });
  attachTip($("#confLabel"), "Test confidence",
            "How close a match has to be, from 0.50 to 1.00.\n\n"
            + "The Test buttons below use it, and a newly added Vision block "
            + "starts with it as its Confidence.\n\n"
            + "Blocks that already exist are never changed — edit those on the row itself.");
  $("#setRecordMove").addEventListener("change", function () {
    $("#optRecordMove").checked = $("#setRecordMove").checked;
    setSetting("record_mouse_move", $("#setRecordMove").checked);
  });
  /* The Loop phase header edits the very same two settings. */
  $("#setLoopForever").addEventListener("change", async function () {
    await setSetting("loop_forever", $("#setLoopForever").checked);
    syncLoopControls();
  });
  $("#setLoopCount").addEventListener("change", async function () {
    await setSetting("loop_count", Math.max(1, toInt($("#setLoopCount").value, 1)));
    syncLoopControls();
  });

  /* --- webhook ------------------------------------------------------ */
  $("#hookEnabled").addEventListener("change", toggleWebhookEnabled);
  $("#btnHookSave").addEventListener("click", saveWebhookUrl);
  $("#btnHookClear").addEventListener("click", clearWebhookUrl);
  $("#btnHookTest").addEventListener("click", testWebhook);
  $("#hookUrl").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); saveWebhookUrl(); }
  });
  $("#hookUser").addEventListener("change", async function () {
    var name = ($("#hookUser").value || "").trim() || "Macro Studio";
    applyWebhookResult(await api("save_webhook_settings", null, null, name));
  });

  $("#btnHealth").addEventListener("click", runHealthCheck);
  $("#btnOpenData").addEventListener("click", function () { apiQ("open_data_folder"); });
  $("#btnOpenAssets").addEventListener("click", function () { apiQ("open_assets_folder"); });
  $("#btnResetSettings").addEventListener("click", resetSettings);

  /* --- global keys --------------------------------------------------- */
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;

    /* An open dropdown eats Escape in its own handler, so reaching here means
       there is none -- except for one opened without the keyboard, which is
       still the innermost thing on screen and so goes first. */
    if (openSelect) { e.preventDefault(); closeOpenSelect(true); return; }

    /* Only the TOPMOST overlay closes. Closing every visible one at once
       meant that pressing Escape over the "Reset to original?" confirmation
       also closed the actions editor underneath it -- and answering the
       confirmation afterwards then reset a recording whose editor was gone.
       The prompt/confirm modals cancel themselves in their own handler, so
       they are skipped here. */
    var open = $$(".overlay").filter(function (o) {
      return o.id !== "pickOverlay" && !o.classList.contains("hidden");
    });
    if (!open.length) {
      $("#macroMenu").classList.add("hidden");
      return;
    }
    var top = open.reduce(function (best, o) {
      var z = parseInt(getComputedStyle(o).zIndex, 10) || 0;
      var bz = parseInt(getComputedStyle(best).zIndex, 10) || 0;
      /* Ties break on DOM order: later markup paints on top. */
      return z >= bz ? o : best;
    }, open[0]);

    if (top.id === "textModal" || top.id === "confirmModal") return;  /* self-handled */
    if (top.id === "regionModal") {
      var cancel = $("#btnRegionCancel");
      if (cancel) cancel.click();
      return;
    }
    if (top.id === "recEditModal") { closeRecordingEditor(); return; }
    /* One level of nesting at a time, not the whole stack. */
    if (top.id === "blocksEditModal") { closeBlocksEditor(); return; }
    if (top.id === "bigViewModal") { closeImgLargeView(); return; }
    /* Both of these owe someone a promise; hiding the overlay behind their
       backs would leave the caller waiting for ever. */
    if (top.id === "tplPickModal") { closeTemplatePicker(undefined); return; }
    top.classList.add("hidden");
  });
}

/* ==========================================================================
   21. BOOTSTRAP
   ========================================================================== */
async function init() {
  if (state.booted) return;
  state.booted = true;

  var boot = await api("get_bootstrap");
  if (!boot) {
    toast("Could not load app data — the UI is running with defaults", "err");
    boot = {};
  }

  state.version = boot.version || "0.0.0";
  state.catalog = Array.isArray(boot.catalog) ? boot.catalog : [];
  state.byType = {};
  state.catalog.forEach(function (spec) { state.byType[spec.type] = spec; });
  if (Array.isArray(boot.phases) && boot.phases.length) state.phases = boot.phases;
  state.settings = boot.settings || {};
  state.macros = Array.isArray(boot.macros) ? boot.macros : [];
  state.recordings = Array.isArray(boot.recordings) ? boot.recordings : [];

  /* Before the first render, so the app is never briefly the wrong colour. */
  applyTheme(state.settings.theme);

  $("#appVersion").textContent = "v" + state.version;

  (boot.logs || []).forEach(appendLogEntry);

  renderPalette();
  renderPhases();
  renderMacroMenu();
  renderRecordings();
  applySettingsToUI();
  renderEnvRow(boot);
  setSaveHint("");

  refreshTargetInfo();
  refreshWindows();
  refreshTemplates();
  refreshWebhook();

  await pollStatus();
  clearInterval(state.statusTimer);
  state.statusTimer = setInterval(pollStatus, 1000);
}

wireStatic();
window.addEventListener("pywebviewready", init);
/* If the bridge was already up before this script ran, the event never fires. */
if (bridgeReady()) init();

