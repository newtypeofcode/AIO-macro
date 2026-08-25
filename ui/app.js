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
  phases: [{ key: "setup", label: "Setup" }, { key: "loop", label: "Loop" },
           { key: "watch", label: "Watch" }],
  settings: {},
  macros: [],
  recordings: [],
  templates: [],
  maps: [],
  groups: [],
  palettes: [],
  activePalette: "",
  windows: [],
  /* Which blocks are ticked for "save as group", and in which phase. One
     phase at a time: blocks picked out of two phases have no single order. */
  selection: { phase: null, ids: [] },

  macro: { name: "", phases: { setup: [], loop: [], watch: [] } },
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

var GROUP_ORDER = ["Mouse", "Roblox", "Keyboard", "Timing", "Vision", "Flow", "Notify"];
var COLORS = {
  rose: "var(--rose)", blue: "var(--blue)", amber: "var(--amber)",
  teal: "var(--teal)", violet: "var(--violet)", lime: "var(--lime)"
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

/* Every failure core/webhook.py can report is reported through t() below, as
   `wh_<reason>`; unknown reasons fall through to the two shaped ones. */
function webhookReason(reason) {
  var key = String(reason || "unknown");
  if (hasString("wh_" + key)) return t("wh_" + key);
  if (key.indexOf("rejected_") === 0) return tf("wh_rejected", key.slice(9));
  if (key.indexOf("http_") === 0) return tf("wh_http", key.slice(5));
  return tf("wh_unreachable", key);
}

var HOTKEYS = [
  { key: "hotkey_start", label: "hk_start" },
  { key: "hotkey_stop", label: "hk_stop" },
  { key: "hotkey_pause", label: "hk_pause" },
  { key: "hotkey_record", label: "hk_record" },
  { key: "hotkey_pick", label: "hk_pick" }
];

/* ==========================================================================
   1b. INTERFACE LANGUAGE

   One table, two columns. Block TYPE names are deliberately absent: "Click"
   and "Wait for Image" are identifiers shared with the runner and the saved
   macro files, and they come from the catalog rather than from here. The
   catalog's `desc` / `help` prose IS translated -- by Python, which hands the
   whole catalog back in the chosen language (see setLanguage below).
   ========================================================================== */
var LANGUAGES = [
  { key: "en", label: "English", code: "EN" },
  { key: "ru", label: "Русский", code: "RU" }
];
var DEFAULT_LANG = "en";

var STRINGS = {
  en: {
    /* ---- chrome / navigation ---- */
    tip_target_chip: "Click to open the target picker",
    target_none: "No target selected",
    target_screen: "Whole screen",
    win_minimize: "Minimize", win_maximize: "Maximize", win_restore: "Restore down",
    win_close: "Close",
    nav_builder: "Builder", nav_build: "Build", nav_record: "Record",
    nav_images: "Images", nav_settings: "Settings", nav_setup: "Setup",

    /* ---- generic buttons ---- */
    btn_save: "Save", btn_load: "Load", btn_new: "New", btn_delete: "Delete",
    btn_import: "Import", btn_export: "Export", btn_cancel: "Cancel",
    btn_ok: "OK", btn_confirm: "Confirm", btn_done: "Done", btn_close: "Close",
    btn_refresh: "Refresh", btn_clear: "Clear", btn_continue: "Continue",
    btn_duplicate: "Duplicate", btn_move_up: "Move up", btn_move_down: "Move down",
    btn_pick: "Pick", btn_once: "ONCE",
    none_dash: "— none —", rendering: "Rendering…", loading: "loading…",

    /* ---- builder ---- */
    palette_title: "Block palette",
    palette_manage: "Custom block palettes", palette_name_ph: "Palette name",
    palette_save: "Save palette", palette_new: "New", palette_import: "Import",
    palette_export: "Export", palette_folder: "Open folder", palette_saved: "Saved palettes",
    palette_hint_manage: "Choose the blocks to include. Palettes contain only block types, so they are safe to share.",
    palette_select_all: "Select all", palette_select_none: "Select none",
    palette_use: "Use", palette_edit: "Edit", palette_delete: "Delete",
    palette_empty: "No custom palettes yet.", palette_need_name: "Enter a palette name.",
    palette_need_blocks: "Select at least one block.", palette_save_failed: "Could not save palette.",
    palette_saved_toast: "Palette saved", palette_exported: "Palette exported",
    palette_imported: "Palette imported", palette_import_failed: "Could not import palette.",
    palette_delete_q: "Delete this palette?", palette_delete_body: "Only the palette file will be removed.",
    palette_hint: "Drag a block into a phase, or click it to append.",
    palette_hint_list: "Drag a block into the list, or click it to append.",
    palette_drag_hint: "Drag it into a phase, or click to append it to Loop.",
    palette_drag_list: "Drag it into the list, or click to append it to the end.",
    macro_name_ph: "Untitled macro",
    phase_setup: "Setup", phase_loop: "Loop", phase_watch: "Watch",
    badge_watch: "always",
    watch_hint: "Checked between blocks for as long as the macro runs. Give the "
      + "block that looks for the event On fail = \"skip rest\" -- a pass that "
      + "finds nothing then stops there and nothing below it runs. When it does "
      + "find it, the rest of this phase runs and then the choice above applies.",
    watch_on_word: "Watch",
    watch_on_tip: "Check this phase while the macro runs",
    watch_every: "every", watch_then: "then",
    watch_after_continue: "continue",
    watch_after_loop: "restart Loop",
    watch_after_macro: "restart macro",
    tip_watch_title: "Watch phase",
    tip_watch_body: "Runs between the blocks of Setup and Loop, at the interval "
      + "you set here.\n\nUse it for things that can happen at any moment: a "
      + "death screen, a level-up popup, a disconnect dialog.\n\nAfter it has "
      + "fired you can carry on where the macro left off, restart the Loop from "
      + "the top, or restart the whole macro including Setup.",
    ctl_runtime_tip: "Running for %s, %s loop pass(es)",
    /* ---- block groups ---- */
    grp_title: "Saved block groups",
    grp_filter_ph: "filter by name...",
    grp_hint: "Adds the group's blocks to the end of the chosen phase. They are copies -- editing them here changes nothing in the saved group.",
    grp_folder: "Groups folder",
    grp_empty: "No groups saved yet. Tick the # numbers of a few blocks and press Save group.",
    grp_no_match: "No group matches that.",
    grp_insert: "Insert",
    grp_rename: "Rename",
    grp_delete_q: "Delete the group \u201c%s\u201d?",
    grp_delete_body: "Only the saved group goes -- blocks already inserted into a macro stay.",
    grp_inserted: "%s block(s) added to %s",
    grp_saved: "Group \u201c%s\u201d saved (%s block(s))",
    grp_save_title: "Name for the group",
    grp_save_sel: "%s selected block(s) from %s.",
    grp_save_all: "All %s block(s) of %s.",
    grp_need_name: "The group needs a name",
    grp_nothing: "Nothing to save in this phase",
    grp_overwrite: "Replace the group \u201c%s\u201d?",
    grp_overwrite_body: "A group with that name already exists and will be overwritten.",
    grp_save_failed: "Could not save the group",
    grp_load_failed: "Could not open that group",
    grp_btn_insert: "Group",
    grp_btn_insert_tip: "Insert a saved block group into this phase",
    grp_btn_save: "Save group",
    grp_btn_save_sel: "Save group (%s)",
    grp_btn_save_tip: "Save the ticked blocks as a reusable group -- or the whole phase when nothing is ticked.",
    grp_btn_clear_sel: "Clear ticks",
    grp_pick_title: "Pick for a group",
    grp_pick_body: "Click the number to tick this block, then press Save group in the phase header.",
    set_roblox_share: "Roblox share link",
    set_roblox_place: "Roblox place id",
    set_roblox_code: "Private server code",
    set_roblox_hint: "Used by the Rejoin Server block whenever its own fields are left empty. A share link is enough on its own \u2014 the id and the code below are only for the older form of joining.",
    badge_once: "RUNS ONCE", badge_repeat: "REPEATS",
    phase_collapse: "Collapse",
    block_1: "block", block_n: "blocks",
    dropzone: "drag blocks here",
    tip_drag_reorder: "Drag to reorder",
    tip_toggle_block: "Clicking the name switches the block on and off.",
    tip_once: "Run this block only on the first pass",
    tip_run_block: "Run just this block",
    row_edit_actions: "Edit actions",
    row_edit_actions_tip: "Open the recorded actions and edit them in place",
    row_preview: "Preview",
    row_preview_tip: "Show the image this block would attach — nothing is sent",
    field_coords: "Coords",
    tip_pick_point: "Click anywhere on screen to set X and Y",
    tip_pick_region: "Drag a rectangle on a capture of the target",
    tip_pick_color: "Pick a colour from the screen",
    region_full: "full target",
    key_press_prompt: "click, then press",
    key_pressing: "press a key...",
    tpl_choose: "choose image…",
    tpl_chosen: "Image: %s — click to change",
    tpl_empty_tip: "No image chosen — click to pick one",
    missing_suffix: "(missing)",
    blocks_field_tip: "Edit the %s block(s) that run when this one fails",
    blocks_field_empty_tip: "No fallback blocks yet — click to add some",
    loop_forever_word: "forever",
    loop_forever_tip: "Repeat the Loop phase until you press Stop",
    tip_repeats_title: "Repeats",
    tip_repeats_body: "How many times to run the Loop phase.\n\n"
      + "“forever” repeats until you press Stop. Switch it off and the macro "
      + "stops by itself after that many passes.\n\n"
      + "These are the same two settings the Setup screen shows.",

    /* ---- macro IO ---- */
    hint_unsaved: "unsaved", hint_not_saved: "not saved yet",
    hint_saved: "saved", hint_save_failed: "save failed", hint_loaded: "loaded",
    hint_imported: "imported — press Save to keep it",
    ask_save_as: "Save macro as",
    ask_save_as_hint: "Letters, numbers, spaces, - and _ only.",
    toast_saved: "Macro '%s' saved",
    toast_loaded: "Loaded '%s'",
    menu_no_macros: "No saved macros yet",
    ask_new_title: "Start a new macro?",
    ask_new_body: "Unsaved changes to the current macro are lost.",
    ask_delete_title: "Delete '%s'?",
    ask_delete_body: "The saved file is removed from the Templates folder.",
    toast_nothing_delete: "Nothing to delete",
    toast_deleted: "Deleted '%s'",
    toast_delete_failed: "Could not delete '%s'",
    ask_clear_phase: "Clear %s?",
    ask_clear_phase_body: "Every block in this phase is removed. This cannot be undone.",
    toast_run_failed: "Could not run block",
    toast_imported: "Macro imported",
    toast_import_failed: "Import failed",
    toast_export_failed: "Export failed",
    toast_exported: "Exported to %s",
    menu_export_json: "Export macro only (.json)",
    menu_export_json_sub: "The blocks alone — images and recordings stay behind.",
    menu_export_bundle: "Export with images and recordings (.macrozip)",
    menu_export_bundle_sub: "One file another machine can open and run.",
    menu_import_json: "Import macro (.json)",
    menu_import_json_sub: "Blocks only; any image it names must already exist here.",
    menu_import_bundle: "Import bundle (.macrozip)",
    menu_import_bundle_sub: "Brings its images and recordings with it.",

    /* ---- bundles ---- */
    bundle_export_title: "Export bundle",
    bundle_export_lead: "The bundle will carry the macro plus exactly the images "
      + "and recordings it references. Nothing else of yours goes in — not your "
      + "other images, not your settings, not your webhook URL.",
    bundle_export_ok: "Choose a file…",
    bundle_import_title: "Import bundle",
    bundle_import_lead: "This is what the bundle holds. Nothing has been written yet.",
    bundle_import_ok: "Import",
    bundle_images: "Images", bundle_recordings: "Recordings",
    bundle_missing: "Missing — will NOT be included",
    bundle_clash: "Names you already use",
    bundle_none: "none",
    bundle_missing_hint: "Those files are gone from your folders, so the bundle "
      + "will be incomplete.",
    bundle_clash_hint: "By default your own files are kept and the bundle's "
      + "copies are skipped.",
    bundle_overwrite: "Replace my existing files",
    bundle_read_failed: "Could not read that bundle",
    bundle_exported: "Bundle written to %s",
    bundle_imported: "Imported %s image(s) and %s recording(s)",
    bundle_kept: "kept your existing: %s",

    /* ---- record screen ---- */
    rec_title: "Recorder",
    rec_start: "Start Recording", rec_stop: "Stop Recording",
    rec_events: "events captured",
    opt_record_move: "Record mouse movement",
    opt_min_gap: "Minimum gap (ms)",
    rec_discard: "Discard pending",
    rec_hotkey_hint: "Hotkey rebind is on the Setup screen. The recorder never captures your own hotkeys.",
    rec_saved: "Saved recordings",
    rec_converted: "Converted blocks",
    rec_select_all: "Select all", rec_select_none: "Select none",
    rec_insert_setup: "Insert into Setup", rec_insert_loop: "Insert into Loop",
    rec_insert_separate: "Insert as separate blocks",
    rec_save_as: "Save as recording",
    rec_empty: "Nothing recorded yet. Press Start Recording, do the actions, then stop.",
    rec_preview_hint: "The tick boxes only affect “Insert as separate blocks” — the two Insert "
      + "buttons always add one Play Recording block for the whole take.",
    rec_none_saved: "No saved recordings.",
    rec_btn_edit: "Edit", rec_btn_use: "Use", rec_btn_run: "Run now",
    rec_tip_edit: "Breaks the recording into separate blocks and shows them in the "
      + "preview below. From there you can untick what you do not want and insert "
      + "the rest into Setup or Loop.",
    rec_tip_use: "Adds one “Play Recording” block to Loop that replays the whole "
      + "take with its own timing.",
    rec_tip_run: "Plays the recording right now without adding anything to the "
      + "macro. Stop it with the Stop button or the hotkey.",
    rec_ask_delete: "Delete recording '%s'?",
    rec_ask_delete_body: "The .json file is removed.",
    rec_ask_name: "Name this recording",
    rec_ask_name_hint: "Saved in the Recordings folder, then inserted as one block.",
    rec_ask_save: "Save recording as",
    rec_ask_save_hint: "Stored in the Recordings folder.",
    rec_toast_saved: "Recording saved as '%s'",
    rec_toast_save_failed: "Could not save the recording",
    rec_toast_nothing: "Nothing to insert — record something first",
    rec_toast_added: "Added a Play Recording block for '%s'",
    rec_toast_discarded: "Pending recording discarded",
    rec_toast_select: "Select at least one block first",
    rec_toast_inserted: "%s block(s) added to %s",
    rec_toast_playing: "Playing '%s'",
    rec_toast_play_failed: "Could not play",
    rec_toast_loaded: "Loaded '%s' — pick rows, then insert",
    rec_not_recording: "Not recording",
    rec_cannot: "Cannot record",

    /* ---- recording actions editor ---- */
    recedit_title: "Actions",
    recedit_title_of: "Actions in “%s”",
    recedit_hint: "Edit the fields, drag the grip (or use ↑ ↓) to reorder, and delete what "
      + "you do not need. New block types are added in the Builder, not here.",
    recedit_reset: "Reset to original",
    recedit_empty: "No actions left. “Reset to original” brings back what was recorded.",
    recedit_derived: "derived from %s recorded events",
    recedit_edited: "edited",
    recedit_gone: "this recording no longer exists",
    recedit_load_failed: "could not load this recording",
    recedit_toast_gone: "Recording '%s' no longer exists",
    recedit_toast_failed: "Could not load '%s'",
    recedit_ask_empty: "Remove every action from '%s'?",
    recedit_ask_empty_body: "The recording will still exist, but playing it will do "
      + "nothing. “Reset to original” can bring the recorded actions back.",
    recedit_toast_saved: "%s action(s) saved in '%s'",
    recedit_save_failed: "Could not save actions",
    recedit_ask_reset: "Reset '%s' to the original?",
    recedit_ask_reset_body: "The edited action list is dropped and the actions are "
      + "re-derived from the events that were actually recorded.",
    recedit_reset_failed: "Could not reset",
    recedit_reset_done: "Back to the original actions",
    recedit_close_first: "Close the actions editor first",

    /* ---- nested blocks editor ---- */
    cond_choose: "Choose condition...",
    cond_clear: "Clear condition",
    cond_add: "+ Add condition",
    cond_pick_hint: "Pick a condition type from the list on the left",
    cond_empty: "No conditions yet — click + to add one",
    blocks_edit_title: "Fallback blocks",
    blocks_edit_hint: "These blocks run instead of continuing when the block above fails. "
      + "Drag the grip (or ↑ ↓) to reorder.",
    blocks_edit_clear: "Remove all",
    blocks_edit_levels: "%s levels deep",
    blocks_ask_clear: "Remove all %s block(s)?",
    blocks_ask_clear_body: "The fallback list is emptied. The block will then simply "
      + "carry on when it fails.",

    /* ---- images ---- */
    img_manager: "Image manager",
    img_kind_ui: "UI", img_kind_map: "MAP",
    img_save_map: "Save as map",
    img_save_map_tip: "Saves into the Maps folder instead of Assets — with a selection it saves the "
      + "crop, without one the whole shot. Maps are what Place Unit picks spots on.",
    img_map_saved: "Map '%s' saved",
    img_open_maps: "Open Maps folder",
    img_import_map: "Add map from file",
    img_map_imported: "Map '%s' added",
    img_map_import_failed: "Could not add that file",
    img_map_delete_tip: "Delete this map",
    img_ask_delete_map: "Delete map '%s'?",
    img_ask_delete_map_body: "Removes the picture from the Maps folder. Place Unit blocks keep the "
      + "name and show it as missing.",
    img_map_reshoot: "Re-shoot",
    img_map_reshoot_tip: "Shoot a window again and save it over '%s'.",
    img_map_pick_tip: "Open '%s' and look at the spots units are placed on.",
    img_map_size: "%s × %s",
    img_shot_from: "Shot: %s",
    img_shot_cancelled: "Capture cancelled",
    winpick_title: "Which window should be captured?",
    winpick_hint: "Only for this screenshot — the macro target is not changed.",
    winpick_filter_ph: "Filter by title or process...",
    winpick_screen: "Whole screen (the app hides itself)",
    winpick_target: "current macro target",
    img_capture: "Capture target", img_pick_large: "Pick in large view",
    img_capture_hint: "Capture asks which window to shoot, then opens the large view — "
      + "drag with the left button to crop, middle-drag to pan.",
    img_capture_size: "%s — drag a rectangle to crop. The large view is where the cropping happens.",
    img_no_capture: "No capture yet",
    img_capturing: "Capturing...",
    img_capture_failed: "Capture failed",
    img_decode_failed: "Could not decode the capture",
    img_name: "Image name", img_name_ph: "e.g. play_button",
    img_save_new: "Save as new", img_save_variant: "Save as variant",
    img_open_assets: "Open Assets folder",
    img_variant_hint: "Variants let one name match several looks (hover, pressed, different scale).",
    img_templates: "Images and maps", img_test_conf: "Test confidence",
    img_conf_hint: "Used by the Test buttons below, and as the starting confidence for newly "
      + "added Vision blocks. Blocks you already built keep their own value.",
    img_none: "No images yet. Capture the target and crop one.",
    img_no_preview: "no preview",
    img_variant_1: "%s variant", img_variant_n: "%s variants",
    img_test: "Test",
    img_test_tip: "Look for this image on the target right now, at the “Test confidence” "
      + "set above this grid.",
    img_found: "found %s (%s)", img_not_found: "not found", img_error: "error",
    img_reshoot: "Re-shoot",
    img_reshoot_tip: "Capture the target again and crop it in the large view.\n\n"
      + "Saving then writes back to '%s': either over the main image, or as one "
      + "more variant — the large view offers both.",
    img_delete_tip: "Delete image and variants",
    img_ask_delete: "Delete '%s'?",
    img_ask_delete_body: "Removes %s file(s) from the Assets folder.",
    img_need_name: "Give the image a name first",
    img_need_rect: "Drag a rectangle on the capture first",
    img_save_failed: "Save failed",
    img_saved: "Image '%s' saved", img_variant_saved: "Variant '%s' saved",
    img_replaced: "Replaced the image for '%s'",
    img_variant_added: "Variant added to '%s'",
    img_capture_first: "Capture the target first",
    zoom_in: "Zoom in", zoom_out: "Zoom out", zoom_fit: "Fit",
    zoom_hint_pan: "Wheel scrolls · shift+wheel sideways · ctrl+wheel zooms · middle-drag pans.",

    /* ---- large crop view ---- */
    big_title: "Crop image — large view",
    big_recapture: "Re-capture", big_clear_sel: "Clear selection",
    big_reshooting: "re-shooting “%s”",
    big_replace_main: "Replace main image", big_add_variant: "Add as variant",
    big_hint: "Left-drag crops · middle-drag pans · ctrl+wheel zooms.",
    big_hint_reshoot: "“Replace main image” overwrites the image itself; “Add as variant” "
      + "keeps it and adds another look.",

    /* ---- image picker ---- */
    tplpick_title: "Choose a saved image",
    tplpick_filter_ph: "Filter by name…",
    tplpick_new: "＋ Capture new", tplpick_none: "Use no image",
    map_pick_prompt: "pick location…",
    map_pick_chosen: "%1$s at %2$s — click to change",
    map_pick_empty_tip: "No spot picked — click to open the map",
    mappick_title: "Pick the spot on the map",
    mappick_hint: "Click the picture where the unit goes. Amber dots are units other blocks place on this same map.",
    mappick_no_spot: "no spot yet",
    mappick_empty: "No maps yet — add your own screenshot of the map.",
    mappick_loading: "Opening the picture…",
    mappick_load_failed: "Could not open this map picture.",
    mappick_import: "＋ Add picture", mappick_folder: "Maps folder",
    mappick_clear: "Clear spot", mappick_apply: "Use this spot",
    mappick_added: "Map added: %s",
    mappick_need_spot: "Click the map first — nothing is picked yet.",
    mappick_this: "this one",
    mapgal_title: "Your maps",
    mapgal_hint: "Pick the map this unit goes on. The amber count is how many units other blocks already place on that map.",
    mapgal_filter_ph: "filter by name...",
    mapgal_empty: "No maps yet -- add your own screenshot of the map.",
    mapgal_no_match: "No map matches that.",
    mapgal_none: "choose a map...",
    mapgal_choose_tip: "%s saved maps -- click to look through them",
    mapgal_count: "%s shown",
    mapgal_units: "%s units",
    mapgal_current: "current",
    tplpick_no_match: "No saved image matches “%s”.",
    tplpick_empty: "No saved images yet — press “＋ Capture new”.",

    /* ---- region picker ---- */
    region_title: "Select region",
    region_capturing: "Capturing target...",
    region_clear: "Clear region", region_apply: "Use region",
    region_readout_none: "no region — full target",

    /* ---- picking ---- */
    pick_point: "Click anywhere to capture a coordinate",
    pick_color: "Click anywhere to sample a colour",
    pick_sub: "The next left click anywhere on screen is captured.",
    pick_left: "s left.",
    pick_busy: "Already waiting for a click",
    pick_timeout: "Pick timed out",
    pick_failed: "Pick failed",
    pick_focus_first: "Focus an X or Y field first",
    pick_block_gone: "That block no longer exists",

    /* ---- settings ---- */
    set_target: "Target window", set_not_attached: "not attached",
    set_attached: "attached · %s", set_attached_min: "attached · minimized",
    set_window_gone: "window gone",
    set_filter_ph: "Filter by title or process...",
    set_use_screen: "Use whole screen", set_focus_target: "Focus target",
    set_no_windows: "No windows found. Press Refresh.",
    set_no_window_match: "No window matches that filter.",
    set_minimized: "minimized",
    set_win_min_tip: "%s (minimized — attaching will restore it)",
    set_window_gone_toast: "That window is gone — press Refresh",
    set_hotkeys: "Hotkeys",
    set_hotkeys_hint: "Click a key, then press the key you want. Hotkeys are global.",
    set_unbound: "unbound",
    hk_start: "Start macro", hk_stop: "Stop macro", hk_pause: "Pause / resume",
    hk_record: "Toggle recording", hk_pick: "Pick coordinate",
    set_execution: "Execution", set_action_delay: "Action delay",
    set_loop_forever: "Loop forever", set_loop_count: "Loop count",
    set_conf_moved: "Match confidence now lives on the Images screen as “Test confidence”, "
      + "next to the Test buttons it drives.",
    set_appearance: "Appearance",
    set_theme_hint: "Pick a theme. It is applied instantly and remembered.",
    set_language: "Language",
    set_language_hint: "Changes the interface and the block help text straight away.",
    toast_theme: "Theme: %s",
    toast_language: "Language: %s",
    tip_conf_title: "Test confidence",
    tip_conf_body: "How close a match has to be, from 0.50 to 1.00.\n\n"
      + "The Test buttons below use it, and a newly added Vision block starts with "
      + "it as its Confidence.\n\n"
      + "Blocks that already exist are never changed — edit those on the row itself.",
    set_ask_reset: "Reset all settings?",
    set_ask_reset_body: "Hotkeys, delays, thresholds and the target selection go back to defaults.",
    set_reset_done: "Settings reset",

    /* ---- webhook ---- */
    hook_title: "Discord webhook", hook_not_configured: "not configured",
    hook_armed: "armed", hook_configured_off: "configured · off",
    hook_state_off: "Sending is OFF — nothing is ever sent to Discord, not even by a Send Webhook block.",
    hook_state_on: "Sending is ON — Send Webhook blocks and the test button will post to Discord.",
    hook_state_no_url: "Sending is on, but no valid URL is saved yet, so nothing can be sent.",
    hook_enable: "Enable sending", hook_saved_url: "Saved URL", hook_no_url: "no URL saved",
    hook_new_url: "New webhook URL", hook_bot_name: "Bot name",
    hook_design_title: "Embed title", hook_design_color: "Accent color",
    hook_design_footer: "Footer", hook_design_description: "Default description",
    hook_design_timestamp: "Show timestamp in embed",
    hook_design_hint: "The Send Webhook block message overrides the default description. These styles are used by the test and by every webhook block.",
    hook_save_url: "Save URL", hook_test: "Send test message", hook_sending: "Sending…",
    hook_remove: "Remove URL",
    hook_secret_hint: "The URL is a secret: once saved it never leaves the app again, only a masked form is shown.",
    hook_saved_hint: "Saved. Only the masked form is ever shown again.",
    hook_removed_hint: "URL removed. Nothing can be sent until a new one is saved.",
    hook_url_saved: "Webhook URL saved",
    hook_ask_clear: "Remove the saved webhook URL?",
    hook_ask_clear_body: "The URL is deleted and sending is switched off. You will have to "
      + "paste it again to use it.",
    hook_url_removed: "Webhook URL removed",
    hook_enabled_toast: "Webhook sending enabled", hook_disabled_toast: "Webhook sending disabled",
    hook_test_ok: "Test message delivered", hook_test_failed: "Test failed",
    hook_preview_title: "Webhook attachment preview",
    hook_preview_hint: "Nothing has been sent — this is only what the block would attach.",
    hook_preview_failed: "failed",
    hook_preview_text_only: "No image — this block would send text only.",
    wh_empty: "Paste a webhook URL first.",
    wh_not_https: "The URL has to start with https://",
    wh_not_discord: "That host is not Discord — the URL must be on discord.com.",
    wh_bad_format: "That does not look like a Discord webhook URL. In Discord: Channel "
      + "settings → Integrations → Webhooks → Copy Webhook URL.",
    wh_requests_missing: "The 'requests' package is not installed, so nothing can be sent.",
    wh_nothing_to_send: "There was nothing to send — add a message or an attachment.",
    wh_attachment_too_large: "The attachment is too large for Discord (8 MB limit).",
    wh_capture_failed: "The screen could not be captured.",
    wh_no_such_image: "There is no saved image by that name.",
    wh_rejected: "Discord rejected the webhook (%s) — it was probably deleted.",
    wh_http: "Discord answered with HTTP %s.",
    wh_unreachable: "Could not reach Discord (%s).",

    /* ---- diagnostics ---- */
    diag_title: "Diagnostics", diag_run: "Run health check",
    diag_empty: "Run the check to verify capture, input and OCR.",
    diag_running: "Running...", diag_failed: "Health check failed to run.",
    diag_data_folder: "Data folder", diag_assets_folder: "Assets folder",
    diag_reset: "Reset settings",
    env_version: "version", env_ocr: "OCR", env_scale: "display scale",

    /* ---- log + control bar ---- */
    log_title: "Activity log", log_clear: "Clear",
    ctl_start: "Start", ctl_pause: "Pause", ctl_resume: "Resume", ctl_stop: "Stop",
    ctl_idle: "Idle", ctl_loop: "loop %s",
    ctl_recording: "recording · %s events",
    ctl_target: "target: %s", ctl_no_target: "no target",
    ctl_already: "Already running",
    ctl_need_block: "Add at least one block first",
    ctl_cannot_start: "Could not start",
    ctl_no_target_reason: "no target window attached",
    ctl_recording_reason: "stop the recorder first",

    /* ---- misc modals ---- */
    ask_title: "Name", ask_sure: "Are you sure?",
    boot_failed: "Could not load app data — the UI is running with defaults"
  },

  ru: {
    /* ---- chrome / navigation ---- */
    tip_target_chip: "Нажми, чтобы открыть выбор окна-цели",
    target_none: "Цель не выбрана",
    target_screen: "Весь экран",
    win_minimize: "Свернуть", win_maximize: "Развернуть", win_restore: "Восстановить",
    win_close: "Закрыть",
    nav_builder: "Конструктор", nav_build: "Сборка", nav_record: "Запись",
    nav_images: "Картинки", nav_settings: "Настройки", nav_setup: "Настройки",

    /* ---- generic buttons ---- */
    btn_save: "Сохранить", btn_load: "Открыть", btn_new: "Новый", btn_delete: "Удалить",
    btn_import: "Импорт", btn_export: "Экспорт", btn_cancel: "Отмена",
    btn_ok: "ОК", btn_confirm: "Подтвердить", btn_done: "Готово", btn_close: "Закрыть",
    btn_refresh: "Обновить", btn_clear: "Очистить", btn_continue: "Продолжить",
    btn_duplicate: "Дублировать", btn_move_up: "Вверх", btn_move_down: "Вниз",
    btn_pick: "Взять", btn_once: "1 РАЗ",
    none_dash: "— нет —", rendering: "Готовим…", loading: "загрузка…",

    /* ---- builder ---- */
    palette_title: "Палитра блоков",
    palette_manage: "Свои палитры блоков", palette_name_ph: "Название палитры",
    palette_save: "Сохранить палитру", palette_new: "Новая", palette_import: "Импорт",
    palette_export: "Экспорт", palette_folder: "Открыть папку", palette_saved: "Сохранённые палитры",
    palette_hint_manage: "Выбери блоки для палитры. В палитре хранятся только типы блоков — ею безопасно делиться.",
    palette_select_all: "Выбрать все", palette_select_none: "Снять выбор",
    palette_use: "Использовать", palette_edit: "Изменить", palette_delete: "Удалить",
    palette_empty: "Своих палитр пока нет.", palette_need_name: "Введи название палитры.",
    palette_need_blocks: "Выбери хотя бы один блок.", palette_save_failed: "Не удалось сохранить палитру.",
    palette_saved_toast: "Палитра сохранена", palette_exported: "Палитра экспортирована",
    palette_imported: "Палитра импортирована", palette_import_failed: "Не удалось импортировать палитру.",
    palette_delete_q: "Удалить эту палитру?", palette_delete_body: "Будет удалён только файл палитры.",
    palette_hint: "Перетащи блок в фазу или кликни, чтобы добавить.",
    palette_hint_list: "Перетащи блок в список или кликни, чтобы добавить.",
    palette_drag_hint: "Перетащи в фазу или кликни, чтобы добавить в Loop.",
    palette_drag_list: "Перетащи в список или кликни, чтобы добавить в конец.",
    macro_name_ph: "Без названия",
    phase_setup: "Подготовка", phase_loop: "Цикл", phase_watch: "Наблюдение",
    badge_watch: "всегда",
    watch_hint: "Проверяется между блоками всё время, пока работает "
      + "макрос. У блока, который ищет событие, поставьте «При неудаче = "
      + "skip rest» — тогда проход, в котором ничего нет, просто "
      + "обрывается. Если событие нашлось — выполняется остаток фазы, а потом "
      + "то, что выбрано выше.",
    watch_on_word: "Следить",
    watch_on_tip: "Проверять эту фазу, пока работает макрос",
    watch_every: "каждые", watch_then: "потом",
    watch_after_continue: "продолжить",
    watch_after_loop: "перезапустить Цикл",
    watch_after_macro: "перезапустить макрос",
    tip_watch_title: "Фаза Наблюдение",
    tip_watch_body: "Выполняется между блоками Подготовки и Цикла с заданным "
      + "здесь интервалом.\n\nНужна для того, что может случиться в любой "
      + "момент: экран смерти, окно уровня, диалог об отключении.\n\nПосле "
      + "срабатывания можно продолжить с того же места, перезапустить Цикл "
      + "с начала или весь макрос вместе с Подготовкой.",
    ctl_runtime_tip: "Работает %s, проходов цикла: %s",
    /* ---- \u0433\u0440\u0443\u043f\u043f\u044b \u0431\u043b\u043e\u043a\u043e\u0432 ---- */
    grp_title: "\u0421\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u044b\u0435 \u0433\u0440\u0443\u043f\u043f\u044b \u0431\u043b\u043e\u043a\u043e\u0432",
    grp_filter_ph: "\u0444\u0438\u043b\u044c\u0442\u0440 \u043f\u043e \u0438\u043c\u0435\u043d\u0438...",
    grp_hint: "\u0411\u043b\u043e\u043a\u0438 \u0433\u0440\u0443\u043f\u043f\u044b \u0434\u043e\u0431\u0430\u0432\u043b\u044f\u044e\u0442\u0441\u044f \u0432 \u043a\u043e\u043d\u0435\u0446 \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u043e\u0439 \u0444\u0430\u0437\u044b. \u042d\u0442\u043e \u043a\u043e\u043f\u0438\u0438 \u2014 \u043f\u0440\u0430\u0432\u043a\u0438 \u0437\u0434\u0435\u0441\u044c \u043d\u0435 \u043c\u0435\u043d\u044f\u044e\u0442 \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u0443\u044e \u0433\u0440\u0443\u043f\u043f\u0443.",
    grp_folder: "\u041f\u0430\u043f\u043a\u0430 Groups",
    grp_empty: "\u0413\u0440\u0443\u043f\u043f \u043f\u043e\u043a\u0430 \u043d\u0435\u0442. \u041e\u0442\u043c\u0435\u0442\u044c \u043d\u043e\u043c\u0435\u0440\u0430 # \u043d\u0443\u0436\u043d\u044b\u0445 \u0431\u043b\u043e\u043a\u043e\u0432 \u0438 \u043d\u0430\u0436\u043c\u0438 \u00ab\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443\u00bb.",
    grp_no_match: "\u041d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043d\u0430\u0448\u043b\u043e\u0441\u044c.",
    grp_insert: "\u0412\u0441\u0442\u0430\u0432\u0438\u0442\u044c",
    grp_rename: "\u041f\u0435\u0440\u0435\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u0442\u044c",
    grp_delete_q: "\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443 \u00ab%s\u00bb?",
    grp_delete_body: "\u0423\u0434\u0430\u043b\u0438\u0442\u0441\u044f \u0442\u043e\u043b\u044c\u043a\u043e \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u0430\u044f \u0433\u0440\u0443\u043f\u043f\u0430 \u2014 \u0443\u0436\u0435 \u0432\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u043d\u044b\u0435 \u0431\u043b\u043e\u043a\u0438 \u043e\u0441\u0442\u0430\u043d\u0443\u0442\u0441\u044f.",
    grp_inserted: "\u0414\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u043e \u0431\u043b\u043e\u043a\u043e\u0432: %s \u2192 %s",
    grp_saved: "\u0413\u0440\u0443\u043f\u043f\u0430 \u00ab%s\u00bb \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0430 (\u0431\u043b\u043e\u043a\u043e\u0432: %s)",
    grp_save_title: "\u0418\u043c\u044f \u0433\u0440\u0443\u043f\u043f\u044b",
    grp_save_sel: "\u041e\u0442\u043c\u0435\u0447\u0435\u043d\u043e \u0431\u043b\u043e\u043a\u043e\u0432: %s \u0438\u0437 %s.",
    grp_save_all: "\u0412\u0441\u0435 \u0431\u043b\u043e\u043a\u0438 (%s) \u0438\u0437 %s.",
    grp_need_name: "\u0413\u0440\u0443\u043f\u043f\u0435 \u043d\u0443\u0436\u043d\u043e \u0438\u043c\u044f",
    grp_nothing: "\u0412 \u044d\u0442\u043e\u0439 \u0444\u0430\u0437\u0435 \u043d\u0435\u0447\u0435\u0433\u043e \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u0442\u044c",
    grp_overwrite: "\u0417\u0430\u043c\u0435\u043d\u0438\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443 \u00ab%s\u00bb?",
    grp_overwrite_body: "\u0413\u0440\u0443\u043f\u043f\u0430 \u0441 \u0442\u0430\u043a\u0438\u043c \u0438\u043c\u0435\u043d\u0435\u043c \u0443\u0436\u0435 \u0435\u0441\u0442\u044c \u0438 \u0431\u0443\u0434\u0435\u0442 \u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0438\u0441\u0430\u043d\u0430.",
    grp_save_failed: "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443",
    grp_load_failed: "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u0442\u043a\u0440\u044b\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443",
    grp_btn_insert: "\u0413\u0440\u0443\u043f\u043f\u0430",
    grp_btn_insert_tip: "\u0412\u0441\u0442\u0430\u0432\u0438\u0442\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u0443\u044e \u0433\u0440\u0443\u043f\u043f\u0443 \u0431\u043b\u043e\u043a\u043e\u0432 \u0432 \u044d\u0442\u0443 \u0444\u0430\u0437\u0443",
    grp_btn_save: "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443",
    grp_btn_save_sel: "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443 (%s)",
    grp_btn_save_tip: "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u043e\u0442\u043c\u0435\u0447\u0435\u043d\u043d\u044b\u0435 \u0431\u043b\u043e\u043a\u0438 \u043a\u0430\u043a \u0433\u0440\u0443\u043f\u043f\u0443 \u2014 \u0438\u043b\u0438 \u0432\u0441\u044e \u0444\u0430\u0437\u0443, \u0435\u0441\u043b\u0438 \u043d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043e\u0442\u043c\u0435\u0447\u0435\u043d\u043e.",
    grp_btn_clear_sel: "\u0421\u043d\u044f\u0442\u044c \u043e\u0442\u043c\u0435\u0442\u043a\u0438",
    grp_pick_title: "\u041e\u0442\u043c\u0435\u0442\u043a\u0430 \u0434\u043b\u044f \u0433\u0440\u0443\u043f\u043f\u044b",
    grp_pick_body: "\u041a\u043b\u0438\u043a \u043f\u043e \u043d\u043e\u043c\u0435\u0440\u0443 \u043e\u0442\u043c\u0435\u0447\u0430\u0435\u0442 \u0431\u043b\u043e\u043a, \u043f\u043e\u0442\u043e\u043c \u043d\u0430\u0436\u043c\u0438 \u00ab\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443\u00bb \u0432 \u0448\u0430\u043f\u043a\u0435 \u0444\u0430\u0437\u044b.",
    set_roblox_share: "\u0421\u0441\u044b\u043b\u043a\u0430-\u043f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d\u0438\u0435 Roblox",
    set_roblox_place: "Place id \u0438\u0433\u0440\u044b Roblox",
    set_roblox_code: "\u041a\u043e\u0434 \u043f\u0440\u0438\u0432\u0430\u0442\u043d\u043e\u0433\u043e \u0441\u0435\u0440\u0432\u0435\u0440\u0430",
    set_roblox_hint: "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0435\u0442\u0441\u044f \u0431\u043b\u043e\u043a\u043e\u043c \xab\u041f\u0435\u0440\u0435\u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u044c\u0441\u044f\xbb, \u043a\u043e\u0433\u0434\u0430 \u0435\u0433\u043e \u0441\u043e\u0431\u0441\u0442\u0432\u0435\u043d\u043d\u044b\u0435 \u043f\u043e\u043b\u044f \u043f\u0443\u0441\u0442\u044b\u0435. \u0421\u0441\u044b\u043b\u043a\u0438-\u043f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d\u0438\u044f \u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u0441\u0430\u043c\u043e\u0439 \u043f\u043e \u0441\u0435\u0431\u0435 \u2014 ID \u0438 \u043a\u043e\u0434 \u043d\u0438\u0436\u0435 \u043d\u0443\u0436\u043d\u044b \u0442\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f \u0441\u0442\u0430\u0440\u043e\u0433\u043e \u0441\u043f\u043e\u0441\u043e\u0431\u0430 \u0432\u0445\u043e\u0434\u0430.",
    badge_once: "ОДИН РАЗ", badge_repeat: "ПОВТОРЯЕТСЯ",
    phase_collapse: "Свернуть",
    block_1: "блок", block_n: "блоков",
    dropzone: "перетащи блоки сюда",
    tip_drag_reorder: "Потяни, чтобы переставить",
    tip_toggle_block: "Клик по названию включает и выключает блок.",
    tip_once: "Выполнить этот блок только на первом проходе",
    tip_run_block: "Выполнить только этот блок",
    row_edit_actions: "Правка действий",
    row_edit_actions_tip: "Открыть записанные действия и отредактировать их",
    row_preview: "Просмотр",
    row_preview_tip: "Показать, что этот блок приложил бы — ничего не отправляется",
    field_coords: "Координаты",
    tip_pick_point: "Кликни в любом месте экрана, чтобы задать X и Y",
    tip_pick_region: "Выдели прямоугольник на снимке цели",
    tip_pick_color: "Взять цвет с экрана",
    region_full: "вся цель",
    key_press_prompt: "кликни и нажми",
    key_pressing: "нажми клавишу...",
    tpl_choose: "выбрать картинку…",
    tpl_chosen: "Картинка: %s — кликни, чтобы сменить",
    tpl_empty_tip: "Картинка не выбрана — кликни, чтобы выбрать",
    missing_suffix: "(нет файла)",
    blocks_field_tip: "Изменить %s блок(ов), которые выполнятся при неудаче",
    blocks_field_empty_tip: "Запасных блоков пока нет — кликни, чтобы добавить",
    loop_forever_word: "бесконечно",
    loop_forever_tip: "Повторять фазу Loop, пока не нажмёшь Stop",
    tip_repeats_title: "Повторы",
    tip_repeats_body: "Сколько раз выполнить фазу Loop.\n\n"
      + "«бесконечно» — повторять, пока не нажмёшь Stop. Если выключить, "
      + "макрос остановится сам после указанного числа проходов.\n\n"
      + "Это те же настройки, что и на экране Setup.",

    /* ---- macro IO ---- */
    hint_unsaved: "не сохранено", hint_not_saved: "ещё не сохранялся",
    hint_saved: "сохранено", hint_save_failed: "не сохранилось", hint_loaded: "загружено",
    hint_imported: "импортировано — нажми Сохранить",
    ask_save_as: "Сохранить макрос как",
    ask_save_as_hint: "Только буквы, цифры, пробелы, - и _.",
    toast_saved: "Макрос «%s» сохранён",
    toast_loaded: "Загружен «%s»",
    menu_no_macros: "Сохранённых макросов пока нет",
    ask_new_title: "Начать новый макрос?",
    ask_new_body: "Несохранённые изменения текущего макроса пропадут.",
    ask_delete_title: "Удалить «%s»?",
    ask_delete_body: "Файл будет удалён из папки Templates.",
    toast_nothing_delete: "Нечего удалять",
    toast_deleted: "Удалён «%s»",
    toast_delete_failed: "Не удалось удалить «%s»",
    ask_clear_phase: "Очистить %s?",
    ask_clear_phase_body: "Все блоки этой фазы будут удалены. Отменить нельзя.",
    toast_run_failed: "Не удалось выполнить блок",
    toast_imported: "Макрос импортирован",
    toast_import_failed: "Импорт не удался",
    toast_export_failed: "Экспорт не удался",
    toast_exported: "Сохранено в %s",
    menu_export_json: "Только макрос (.json)",
    menu_export_json_sub: "Одни блоки — картинки и записи останутся здесь.",
    menu_export_bundle: "С картинками и записями (.macrozip)",
    menu_export_bundle_sub: "Один файл, который откроется и заработает на другой машине.",
    menu_import_json: "Импорт макроса (.json)",
    menu_import_json_sub: "Только блоки; нужные картинки должны уже быть здесь.",
    menu_import_bundle: "Импорт набора (.macrozip)",
    menu_import_bundle_sub: "Приносит свои картинки и записи с собой.",

    /* ---- bundles ---- */
    bundle_export_title: "Экспорт набора",
    bundle_export_lead: "В набор попадут макрос и ровно те картинки и записи, "
      + "на которые он ссылается. Больше ничего твоего туда не идёт — ни другие "
      + "картинки, ни настройки, ни адрес вебхука.",
    bundle_export_ok: "Выбрать файл…",
    bundle_import_title: "Импорт набора",
    bundle_import_lead: "Вот что лежит в наборе. Пока ничего не записано.",
    bundle_import_ok: "Импортировать",
    bundle_images: "Картинки", bundle_recordings: "Записи",
    bundle_missing: "Не найдены — в набор НЕ попадут",
    bundle_clash: "Имена, которые уже заняты",
    bundle_none: "нет",
    bundle_missing_hint: "Этих файлов в твоих папках нет, так что набор будет неполным.",
    bundle_clash_hint: "По умолчанию твои файлы остаются, а копии из набора пропускаются.",
    bundle_overwrite: "Заменить мои файлы",
    bundle_read_failed: "Не удалось прочитать набор",
    bundle_exported: "Набор записан в %s",
    bundle_imported: "Добавлено картинок: %s, записей: %s",
    bundle_kept: "оставлено твоё: %s",

    /* ---- record screen ---- */
    rec_title: "Рекордер",
    rec_start: "Начать запись", rec_stop: "Остановить запись",
    rec_events: "событий записано",
    opt_record_move: "Записывать движение мыши",
    opt_min_gap: "Минимальный интервал (мс)",
    rec_discard: "Отбросить черновик",
    rec_hotkey_hint: "Горячие клавиши меняются на экране Setup. Свои горячие клавиши рекордер не записывает.",
    rec_saved: "Сохранённые записи",
    rec_converted: "Полученные блоки",
    rec_select_all: "Выбрать все", rec_select_none: "Снять все",
    rec_insert_setup: "Вставить в Setup", rec_insert_loop: "Вставить в Loop",
    rec_insert_separate: "Вставить отдельными блоками",
    rec_save_as: "Сохранить как запись",
    rec_empty: "Пока ничего не записано. Нажми «Начать запись», сделай действия и останови.",
    rec_preview_hint: "Галочки влияют только на «Вставить отдельными блоками» — две кнопки "
      + "«Вставить» всегда добавляют один блок Play Recording на всю запись.",
    rec_none_saved: "Сохранённых записей нет.",
    rec_btn_edit: "Правка", rec_btn_use: "Взять", rec_btn_run: "Проиграть",
    rec_tip_edit: "Разбирает запись на отдельные блоки и показывает их в предпросмотре "
      + "ниже. Оттуда можно снять лишние галочки и вставить в Setup или Loop.",
    rec_tip_use: "Добавляет в Loop один блок «Play Recording», который проигрывает "
      + "эту запись целиком с её собственным таймингом.",
    rec_tip_run: "Проигрывает запись прямо сейчас, ничего не добавляя в макрос. "
      + "Остановить — Stop внизу или горячей клавишей.",
    rec_ask_delete: "Удалить запись «%s»?",
    rec_ask_delete_body: "Файл .json будет удалён.",
    rec_ask_name: "Назови эту запись",
    rec_ask_name_hint: "Сохранится в папке Recordings и вставится одним блоком.",
    rec_ask_save: "Сохранить запись как",
    rec_ask_save_hint: "Хранится в папке Recordings.",
    rec_toast_saved: "Запись сохранена как «%s»",
    rec_toast_save_failed: "Не удалось сохранить запись",
    rec_toast_nothing: "Нечего вставлять — сначала запиши что-нибудь",
    rec_toast_added: "Добавлен блок Play Recording для «%s»",
    rec_toast_discarded: "Черновик записи отброшен",
    rec_toast_select: "Отметь хотя бы один блок",
    rec_toast_inserted: "Блоков добавлено в %2$s: %1$s",
    rec_toast_playing: "Проигрываю «%s»",
    rec_toast_play_failed: "Не удалось проиграть",
    rec_toast_loaded: "Загружено «%s» — отметь строки и вставь",
    rec_not_recording: "Запись не идёт",
    rec_cannot: "Записывать нельзя",

    /* ---- recording actions editor ---- */
    recedit_title: "Действия",
    recedit_title_of: "Действия в «%s»",
    recedit_hint: "Меняй поля, тяни за ручку (или ↑ ↓), чтобы переставить, и удаляй лишнее. "
      + "Новые типы блоков добавляются в Конструкторе, а не здесь.",
    recedit_reset: "Вернуть исходные",
    recedit_empty: "Действий не осталось. «Вернуть исходные» восстановит записанное.",
    recedit_derived: "получено из %s записанных событий",
    recedit_edited: "изменено",
    recedit_gone: "этой записи больше нет",
    recedit_load_failed: "не удалось загрузить эту запись",
    recedit_toast_gone: "Записи «%s» больше нет",
    recedit_toast_failed: "Не удалось загрузить «%s»",
    recedit_ask_empty: "Убрать из «%s» все действия?",
    recedit_ask_empty_body: "Запись останется, но проигрывать будет нечего. "
      + "«Вернуть исходные» восстановит записанные действия.",
    recedit_toast_saved: "Действий сохранено в «%2$s»: %1$s",
    recedit_save_failed: "Не удалось сохранить действия",
    recedit_ask_reset: "Вернуть «%s» к исходному?",
    recedit_ask_reset_body: "Изменённый список действий будет отброшен, а действия заново "
      + "выведены из реально записанных событий.",
    recedit_reset_failed: "Не удалось вернуть",
    recedit_reset_done: "Вернулись к исходным действиям",
    recedit_close_first: "Сначала закрой редактор действий",

    /* ---- nested blocks editor ---- */
    cond_choose: "Выбрать условие...",
    cond_clear: "Убрать условие",
    cond_add: "+ Добавить условие",
    cond_pick_hint: "Выбери тип условия из списка слева",
    cond_empty: "Условий нет — нажми + чтобы добавить",
    blocks_edit_title: "Запасные блоки",
    blocks_edit_hint: "Эти блоки выполнятся вместо продолжения, если блок выше не сработает. "
      + "Тяни за ручку (или ↑ ↓), чтобы переставить.",
    blocks_edit_clear: "Убрать все",
    blocks_edit_levels: "вложенность %s",
    blocks_ask_clear: "Убрать все блоки (%s)?",
    blocks_ask_clear_body: "Список запасных блоков будет очищен. При неудаче блок просто "
      + "продолжит работу дальше.",

    /* ---- images ---- */
    img_manager: "Менеджер картинок",
    img_kind_ui: "UI", img_kind_map: "КАРТА",
    img_save_map: "Сохранить картой",
    img_save_map_tip: "Сохраняет в папку Maps, а не в Assets — если есть выделение, "
      + "сохранится оно, если нет — весь снимок. На картах блок «Поставить юнита» выбирает места.",
    img_map_saved: "Карта «%s» сохранена",
    img_open_maps: "Открыть папку Maps",
    img_import_map: "Добавить карту из файла",
    img_map_imported: "Карта «%s» добавлена",
    img_map_import_failed: "Не удалось добавить этот файл",
    img_map_delete_tip: "Удалить эту карту",
    img_ask_delete_map: "Удалить карту «%s»?",
    img_ask_delete_map_body: "Картинка будет удалена из папки Maps. Блоки «Поставить юнита» "
      + "сохранят имя и покажут его как пропавшее.",
    img_map_reshoot: "Переснять",
    img_map_reshoot_tip: "Снять окно заново и сохранить поверх «%s».",
    img_map_pick_tip: "Открыть «%s» и посмотреть, куда ставятся юниты.",
    img_map_size: "%s × %s",
    img_shot_from: "Снято: %s",
    img_shot_cancelled: "Съёмка отменена",
    winpick_title: "Какое окно снять?",
    winpick_hint: "Только для этого снимка — цель макроса не меняется.",
    winpick_filter_ph: "Фильтр по заголовку или процессу...",
    winpick_screen: "Весь экран (приложение прячется)",
    winpick_target: "текущая цель макроса",
    img_capture: "Снять цель", img_pick_large: "Открыть большой вид",
    img_capture_hint: "Снимок сначала спросит окно, потом откроется в большом виде — "
      + "тяни левой кнопкой, чтобы вырезать, средней — чтобы двигать.",
    img_capture_size: "%s — выдели прямоугольник. Вырезать удобнее в большом виде.",
    img_no_capture: "Снимка пока нет",
    img_capturing: "Снимаю...",
    img_capture_failed: "Снимок не удался",
    img_decode_failed: "Не удалось раскодировать снимок",
    img_name: "Имя картинки", img_name_ph: "например play_button",
    img_save_new: "Сохранить как новую", img_save_variant: "Сохранить вариантом",
    img_open_assets: "Открыть папку Assets",
    img_variant_hint: "Варианты позволяют одному имени совпадать с разными видами (наведение, нажатие, другой масштаб).",
    img_templates: "Картинки и карты", img_test_conf: "Порог для теста",
    img_conf_hint: "Используется кнопками «Тест» ниже и как стартовый порог для новых "
      + "Vision-блоков. У уже собранных блоков остаётся своё значение.",
    img_none: "Картинок пока нет. Сними цель и вырежи первую.",
    img_no_preview: "нет превью",
    img_variant_1: "вариантов: %s", img_variant_n: "вариантов: %s",
    img_test: "Тест",
    img_test_tip: "Поискать эту картинку на цели прямо сейчас, с порогом, заданным над сеткой.",
    img_found: "найдено %s (%s)", img_not_found: "не найдено", img_error: "ошибка",
    img_reshoot: "Переснять",
    img_reshoot_tip: "Снять цель заново и вырезать в большом виде.\n\n"
      + "Сохранение запишет обратно в «%s»: либо поверх основной картинки, "
      + "либо ещё одним вариантом — большой вид предложит и то, и другое.",
    img_delete_tip: "Удалить картинку и все её варианты",
    img_ask_delete: "Удалить «%s»?",
    img_ask_delete_body: "Из папки Assets будет удалено файлов: %s.",
    img_need_name: "Сначала задай имя картинки",
    img_need_rect: "Сначала выдели прямоугольник на снимке",
    img_save_failed: "Не удалось сохранить",
    img_saved: "Картинка «%s» сохранена", img_variant_saved: "Вариант «%s» сохранён",
    img_replaced: "Картинка «%s» заменена",
    img_variant_added: "К «%s» добавлен вариант",
    img_capture_first: "Сначала сними цель",
    zoom_in: "Приблизить", zoom_out: "Отдалить", zoom_fit: "Вписать",
    zoom_hint_pan: "Колесо — прокрутка · shift+колесо — вбок · ctrl+колесо — масштаб · средняя кнопка — двигать.",

    /* ---- large crop view ---- */
    big_title: "Вырезать картинку — большой вид",
    big_recapture: "Снять заново", big_clear_sel: "Снять выделение",
    big_reshooting: "пересъёмка «%s»",
    big_replace_main: "Заменить основную", big_add_variant: "Добавить вариантом",
    big_hint: "Левая кнопка — вырезать · средняя — двигать · ctrl+колесо — масштаб.",
    big_hint_reshoot: "«Заменить основную» перезапишет саму картинку; «Добавить вариантом» "
      + "оставит её и добавит ещё один вид.",

    /* ---- image picker ---- */
    tplpick_title: "Выбери сохранённую картинку",
    tplpick_filter_ph: "Фильтр по имени…",
    tplpick_new: "＋ Снять новую", tplpick_none: "Без картинки",
    map_pick_prompt: "выбрать место…",
    map_pick_chosen: "%1$s, точка %2$s — кликни, чтобы сменить",
    map_pick_empty_tip: "Место не выбрано — кликни, чтобы открыть карту",
    mappick_title: "Выбери место на карте",
    mappick_hint: "Нажми на картинке туда, куда ставить юнита. Оранжевые точки — юниты из других блоков на этой же карте.",
    mappick_no_spot: "место не выбрано",
    mappick_empty: "Карт пока нет — добавь свой скриншот карты.",
    mappick_loading: "Открываю картинку…",
    mappick_load_failed: "Не удалось открыть картинку карты.",
    mappick_import: "＋ Добавить картинку", mappick_folder: "Папка Maps",
    mappick_clear: "Убрать место", mappick_apply: "Выбрать место",
    mappick_added: "Карта добавлена: %s",
    mappick_need_spot: "Сначала ткни в карту — место ещё не выбрано.",
    mappick_this: "этот",
    mapgal_title: "Твои карты",
    mapgal_hint: "Выбери карту, на которую ставить юнита. Оранжевая цифра — сколько юнитов другие блоки уже ставят на эту карту.",
    mapgal_filter_ph: "фильтр по названию...",
    mapgal_empty: "Карт пока нет — добавь свой скриншот карты.",
    mapgal_no_match: "Ничего не нашлось.",
    mapgal_none: "выбрать карту...",
    mapgal_choose_tip: "Сохранённых карт: %s — нажми, чтобы посмотреть",
    mapgal_count: "показано: %s",
    mapgal_units: "юнитов: %s",
    mapgal_current: "текущая",
    tplpick_no_match: "Ни одна картинка не подходит под «%s».",
    tplpick_empty: "Картинок пока нет — нажми «＋ Снять новую».",

    /* ---- region picker ---- */
    region_title: "Выбор области",
    region_capturing: "Снимаю цель...",
    region_clear: "Убрать область", region_apply: "Взять область",
    region_readout_none: "область не задана — вся цель",

    /* ---- picking ---- */
    pick_point: "Кликни в любом месте, чтобы взять координату",
    pick_color: "Кликни в любом месте, чтобы взять цвет",
    pick_sub: "Следующий левый клик в любом месте экрана будет пойман. Осталось",
    pick_left: " с.",
    pick_busy: "Уже жду клик",
    pick_timeout: "Время на выбор вышло",
    pick_failed: "Выбор не удался",
    pick_focus_first: "Сначала поставь курсор в поле X или Y",
    pick_block_gone: "Этого блока больше нет",

    /* ---- settings ---- */
    set_target: "Окно-цель", set_not_attached: "не подключено",
    set_attached: "подключено · %s", set_attached_min: "подключено · свёрнуто",
    set_window_gone: "окна больше нет",
    set_filter_ph: "Фильтр по заголовку или процессу...",
    set_use_screen: "Весь экран", set_focus_target: "Активировать цель",
    set_no_windows: "Окон не найдено. Нажми «Обновить».",
    set_no_window_match: "Ни одно окно не подходит под фильтр.",
    set_minimized: "свёрнуто",
    set_win_min_tip: "%s (свёрнуто — при подключении развернётся)",
    set_window_gone_toast: "Этого окна больше нет — нажми «Обновить»",
    set_hotkeys: "Горячие клавиши",
    set_hotkeys_hint: "Кликни по клавише и нажми нужную. Горячие клавиши работают глобально.",
    set_unbound: "не задана",
    hk_start: "Запустить макрос", hk_stop: "Остановить макрос", hk_pause: "Пауза / продолжить",
    hk_record: "Вкл/выкл запись", hk_pick: "Взять координату",
    set_execution: "Выполнение", set_action_delay: "Задержка между действиями",
    set_loop_forever: "Бесконечный цикл", set_loop_count: "Число проходов",
    set_conf_moved: "Порог совпадения теперь на экране Images под именем «Порог для теста», "
      + "рядом с кнопками «Тест», на которые он влияет.",
    set_appearance: "Оформление",
    set_theme_hint: "Выбери тему. Применяется сразу и запоминается.",
    set_language: "Язык",
    set_language_hint: "Меняет интерфейс и подсказки к блокам сразу же.",
    toast_theme: "Тема: %s",
    toast_language: "Язык: %s",
    tip_conf_title: "Порог для теста",
    tip_conf_body: "Насколько точным должно быть совпадение, от 0.50 до 1.00.\n\n"
      + "Кнопки «Тест» ниже используют его, и новый Vision-блок получает его как "
      + "свой Confidence.\n\n"
      + "Уже существующие блоки не меняются — их правь прямо в строке.",
    set_ask_reset: "Сбросить все настройки?",
    set_ask_reset_body: "Горячие клавиши, задержки, пороги и выбор цели вернутся к значениям по умолчанию.",
    set_reset_done: "Настройки сброшены",

    /* ---- webhook ---- */
    hook_title: "Вебхук Discord", hook_not_configured: "не настроен",
    hook_armed: "готов", hook_configured_off: "настроен · выключен",
    hook_state_off: "Отправка ВЫКЛЮЧЕНА — в Discord не уходит ничего, даже из блока Send Webhook.",
    hook_state_on: "Отправка ВКЛЮЧЕНА — блоки Send Webhook и кнопка теста будут писать в Discord.",
    hook_state_no_url: "Отправка включена, но корректный адрес не сохранён, так что отправить нечего.",
    hook_enable: "Включить отправку", hook_saved_url: "Сохранённый адрес", hook_no_url: "адрес не сохранён",
    hook_new_url: "Новый адрес вебхука", hook_bot_name: "Имя бота",
    hook_design_title: "Заголовок embed", hook_design_color: "Цвет акцента",
    hook_design_footer: "Подпись", hook_design_description: "Описание по умолчанию",
    hook_design_timestamp: "Показывать время в embed",
    hook_design_hint: "Сообщение из блока Send Webhook заменяет описание по умолчанию. Эти стили используются тестом и всеми блоками вебхука.",
    hook_save_url: "Сохранить адрес", hook_test: "Отправить тест", hook_sending: "Отправляю…",
    hook_remove: "Удалить адрес",
    hook_secret_hint: "Адрес — секрет: после сохранения он больше не покидает приложение, показывается только маска.",
    hook_saved_hint: "Сохранено. Дальше показывается только маска.",
    hook_removed_hint: "Адрес удалён. Пока не сохранишь новый, отправить нельзя.",
    hook_url_saved: "Адрес вебхука сохранён",
    hook_ask_clear: "Удалить сохранённый адрес вебхука?",
    hook_ask_clear_body: "Адрес будет удалён, а отправка выключена. Чтобы пользоваться снова, "
      + "придётся вставить его заново.",
    hook_url_removed: "Адрес вебхука удалён",
    hook_enabled_toast: "Отправка вебхуков включена", hook_disabled_toast: "Отправка вебхуков выключена",
    hook_test_ok: "Тестовое сообщение доставлено", hook_test_failed: "Тест не прошёл",
    hook_preview_title: "Что приложит вебхук",
    hook_preview_hint: "Ничего не отправлено — это только то, что блок приложил бы.",
    hook_preview_failed: "не вышло",
    hook_preview_text_only: "Картинки нет — этот блок отправил бы только текст.",
    wh_empty: "Сначала вставь адрес вебхука.",
    wh_not_https: "Адрес должен начинаться с https://",
    wh_not_discord: "Это не Discord — адрес должен быть на discord.com.",
    wh_bad_format: "Не похоже на адрес вебхука Discord. В Discord: настройки канала → "
      + "Интеграции → Вебхуки → Скопировать адрес вебхука.",
    wh_requests_missing: "Пакет 'requests' не установлен, отправить нечем.",
    wh_nothing_to_send: "Отправлять нечего — добавь текст или вложение.",
    wh_attachment_too_large: "Вложение слишком большое для Discord (лимит 8 МБ).",
    wh_capture_failed: "Не удалось снять экран.",
    wh_no_such_image: "Картинки с таким именем нет.",
    wh_rejected: "Discord отклонил вебхук (%s) — скорее всего, его удалили.",
    wh_http: "Discord ответил HTTP %s.",
    wh_unreachable: "Не удалось достучаться до Discord (%s).",

    /* ---- diagnostics ---- */
    diag_title: "Диагностика", diag_run: "Проверить",
    diag_empty: "Запусти проверку, чтобы убедиться в захвате, вводе и OCR.",
    diag_running: "Проверяю...", diag_failed: "Проверка не запустилась.",
    diag_data_folder: "Папка данных", diag_assets_folder: "Папка Assets",
    diag_reset: "Сбросить настройки",
    env_version: "версия", env_ocr: "OCR", env_scale: "масштаб экрана",

    /* ---- log + control bar ---- */
    log_title: "Журнал", log_clear: "Очистить",
    ctl_start: "Пуск", ctl_pause: "Пауза", ctl_resume: "Продолжить", ctl_stop: "Стоп",
    ctl_idle: "Простой", ctl_loop: "проход %s",
    ctl_recording: "запись · %s событий",
    ctl_target: "цель: %s", ctl_no_target: "цели нет",
    ctl_already: "Уже выполняется",
    ctl_need_block: "Сначала добавь хотя бы один блок",
    ctl_cannot_start: "Не удалось запустить",
    ctl_no_target_reason: "окно-цель не подключено",
    ctl_recording_reason: "сначала останови рекордер",

    /* ---- misc modals ---- */
    ask_title: "Имя", ask_sure: "Уверен?",
    boot_failed: "Не удалось загрузить данные — интерфейс работает на значениях по умолчанию"
  }
};

function currentLang() {
  var lang = String((state.settings && state.settings.language) || DEFAULT_LANG);
  return STRINGS[lang] ? lang : DEFAULT_LANG;
}

function langLabel(key) {
  for (var i = 0; i < LANGUAGES.length; i++) if (LANGUAGES[i].key === key) return LANGUAGES[i].label;
  return key;
}

function hasString(key) {
  return STRINGS[currentLang()][key] !== undefined || STRINGS[DEFAULT_LANG][key] !== undefined;
}

/* Missing keys fall back to English rather than to a blank label -- a
   half-finished translation must never blank a button. */
function t(key) {
  var value = STRINGS[currentLang()][key];
  if (value === undefined) value = STRINGS[DEFAULT_LANG][key];
  return value === undefined ? String(key) : value;
}

/* %s in order, or %1$s / %2$s when a language needs a different word order. */
function tf(key) {
  var args = Array.prototype.slice.call(arguments, 1);
  var next = 0;
  return t(key).replace(/%(?:(\d+)\$)?s/g, function (_m, index) {
    var value = index ? args[parseInt(index, 10) - 1] : args[next++];
    return value === undefined || value === null ? "" : String(value);
  });
}

/* Plural helper for the handful of counted nouns the UI shows. */
function tn(one, many, count) {
  return tf(count === 1 ? one : many, count);
}

function applyI18n(root) {
  var scope = root || document;
  $$("[data-i18n]", scope).forEach(function (node) {
    node.textContent = t(node.getAttribute("data-i18n"));
  });
  $$("[data-i18n-title]", scope).forEach(function (node) {
    node.title = t(node.getAttribute("data-i18n-title"));
  });
  $$("[data-i18n-ph]", scope).forEach(function (node) {
    node.setAttribute("placeholder", t(node.getAttribute("data-i18n-ph")));
  });
  document.documentElement.setAttribute("lang", currentLang());
}

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
    $("#textModalTitle").textContent = title || t("ask_title");
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
    $("#confirmTitle").textContent = title || t("ask_sure");
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
  /* Newest first. The tail of a long run is what anyone actually wants to
     read, and appending meant scrolling for it every single time. */
  body.insertBefore(line, body.firstChild);
  while (body.childElementCount > 400) body.removeChild(body.lastElementChild);
  body.scrollTop = 0;
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
  if (name === "settings") { refreshWindows(); refreshWebhook(); renderRunStats(); }
  if (name === "images") { refreshTemplates(); }
  if (name === "record") { refreshRecordings(); }
}

/* ==========================================================================
   7. BLOCK MODEL
   ========================================================================== */
function specFor(type) { return state.byType[type] || null; }
function prettyType(type) {
  return String(type || "Block").replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
}

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
    phases: {
      setup: phaseArray("setup"),
      loop: phaseArray("loop"),
      watch: phaseArray("watch")
    }
  };
}

/* ==========================================================================
   8. BUILDER -- palette
   ========================================================================== */
function renderPalette() {
  buildPalette($("#paletteGroups"), {
    scope: "phase",
    hint: t("palette_drag_hint"),
    onPick: function (spec) {
      phaseArray("loop").push(makeBlock(spec.type));
      renderPhases();
      markDirty();
    },
    onGroup: async function (group) {
      var result = await api("load_block_group", group.name);
      if (!result || !result.ok) { toast(t("grp_load_failed"), "err"); return; }
      var copies = normalizeList(result.blocks || [], true);
      copies.forEach(function (block) { phaseArray("loop").push(block); });
      renderPhases(); markDirty();
      toast(tf("grp_inserted", copies.length, group.name), "ok");
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
  var customPalettes = opts.allowCustom !== false ? (state.palettes || []) : [];
  var customBlocks = opts.allowCustom !== false ? (state.groups || []) : [];
  var active = opts.allowCustom !== false && state.activePalette && (state.palettes || []).find(function (p) {
    return p.name === state.activePalette;
  });
  var allowed = active ? new Set(active.types || []) : null;
  if (opts.allowCustom !== false) {
    var tabs = el("div", { class: "palette-tabs" });
    var allTab = el("button", { class: "palette-tab" + (!active ? " active" : ""), text: "Blocks" });
    allTab.addEventListener("click", function () { state.activePalette = ""; renderPalette(); });
    tabs.appendChild(allTab);
    customPalettes.forEach(function (palette) {
      var tab = el("button", { class: "palette-tab" + (active && active.name === palette.name ? " active" : ""), text: palette.name });
      tab.addEventListener("click", function () { state.activePalette = palette.name; renderPalette(); });
      tabs.appendChild(tab);
    });
    var customTab = el("button", { class: "palette-tab" + (state.activePalette === "__custom__" ? " active" : ""), text: "Custom" });
    customTab.addEventListener("click", function () { state.activePalette = "__custom__"; renderPalette(); });
    tabs.appendChild(customTab);
    host.appendChild(tabs);
  }

  if (state.activePalette === "__custom__") {
    var customItems = el("div", { class: "pgroup-items" });
    var create = el("div", { class: "chip chip-create", text: "+ Create custom block" });
    create.addEventListener("click", function () { openCustomBlockEditor(); });
    customItems.appendChild(create);
    customBlocks.forEach(function (group) {
      var chip = el("div", { class: "chip", style: "--chip-color:" + colorOf("violet") }, [
        el("span", { class: "chip-dot" }), el("span", { text: group.name })
      ]);
      attachTip(chip, group.name, String(group.count || 0) + " " + t("block_n"));
      chip.addEventListener("click", function () { if (opts.onGroup) opts.onGroup(group); });
      customItems.appendChild(chip);
    });
    host.appendChild(el("div", {}, [el("div", { class: "pgroup-title", text: "Custom blocks" }), customItems]));
    return;
  }
  state.catalog.filter(function (spec) { return !allowed || allowed.has(spec.type); }).forEach(function (spec) {
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
      }, [el("span", { class: "chip-dot" }), el("span", { text: spec.label || prettyType(spec.type) })]);
      attachTip(chip, spec.label || prettyType(spec.type),
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
/* The two phase names come from Python as identifiers with English labels;
   the heading the user reads is translated here, and falls back to whatever
   the catalog said for a phase this table does not know. */
function phaseTitle(ph) {
  var key = "phase_" + ph.key;
  return hasString(key) ? t(key) : (ph.label || ph.key);
}

function renderPhases() {
  var host = $("#phases");
  if (!host) return;
  host.innerHTML = "";

  state.phases.forEach(function (ph) {
    var blocks = phaseArray(ph.key);
    var badgeKey = ph.key === "setup" ? "once" : (ph.key === "watch" ? "watch" : "repeat");
    var badgeText = t("badge_" + badgeKey);
    var badgeClass = "badge badge-" + badgeKey;
    var phaseLabel = phaseTitle(ph);

    var collapseBtn = el("button", { class: "phase-collapse", title: t("phase_collapse") }, [icon("i-chev", "ic-xs")]);
    var head = el("div", { class: "phase-head" }, [
      collapseBtn,
      el("span", { class: "phase-title", text: phaseLabel }),
      el("span", { class: badgeClass, text: badgeText }),
      el("span", { class: "phase-count", text: blocks.length + " " + t(blocks.length === 1 ? "block_1" : "block_n") }),
      el("span", { class: "flex-spacer" })
    ]);
    /* How often the repeating phase repeats is a property OF that phase, so it
       belongs next to it -- the same two settings the Setup screen owns, kept
       in step by syncLoopControls(). */
    if (ph.key === "loop") head.appendChild(loopRepeatControls());
    if (ph.key === "watch") head.appendChild(watchControls());
    /* Reusable groups belong to the phase they are inserted into, so both
       doors -- insert and save -- sit in that phase's own header. */
    var ticked = selectionFor(ph.key);
    head.appendChild(el("button", {
      class: "btn btn-sm", text: t("grp_btn_insert"),
      title: t("grp_btn_insert_tip"),
      onclick: function () { openGroupModal(ph.key); }
    }));
    head.appendChild(el("button", {
      class: "btn btn-sm" + (ticked.length ? " btn-primary" : ""),
      text: ticked.length ? tf("grp_btn_save_sel", ticked.length) : t("grp_btn_save"),
      title: t("grp_btn_save_tip"),
      onclick: function () { saveGroupFrom(ph.key, phaseLabel); }
    }));
    if (ticked.length) {
      head.appendChild(el("button", {
        class: "btn btn-sm", text: t("grp_btn_clear_sel"),
        onclick: function () { clearSelection(); }
      }));
    }
    head.appendChild(el("button", {
      class: "btn btn-sm btn-ghost-danger", text: t("btn_clear"),
      onclick: function () { clearPhase(ph.key, phaseLabel); }
    }));

    var list = el("div", { class: "blocklist" });
    list.dataset.phase = ph.key;
    var ctx = phaseCtx(ph.key);

    if (!blocks.length) {
      list.appendChild(el("div", { class: "dropzone", text: t("dropzone") }));
    } else {
      blocks.forEach(function (block, index) { list.appendChild(renderBlockRow(block, index, ctx)); });
    }
    wireDropTarget(list, ctx);

    var bodyKids = [list];
    /* The one thing about Watch that is not obvious from looking at it: the
       block that CHECKS must abandon the pass when it finds nothing. */
    if (ph.key === "watch") bodyKids.unshift(el("div", { class: "phase-note", text: t("watch_hint") }));
    var panel = el("div", { class: "phase" + (state.collapsed[ph.key] ? " collapsed" : "") }, [
      head, el("div", { class: "phase-body" }, bodyKids)
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
    el("label", { class: "switch-row", title: t("loop_forever_tip") }, [
      el("span", { class: "switch" }, [forever, el("span", { class: "slider" })]),
      el("span", { text: t("loop_forever_word") })
    ]),
    el("span", { class: "loop-x", text: "×" }),
    count
  ]);
  attachTip(node, t("tip_repeats_title"), t("tip_repeats_body"));
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
   The Watch phase's three settings, rendered into its header next to the
   name: whether it is watched at all, how often, and what happens once it
   has fired. Plain settings, like the Loop repeat controls above.
   -------------------------------------------------------------------------- */
function watchControls() {
  var enabled = el("input", { type: "checkbox", id: "watchEnabled" });
  var every = el("input", {
    class: "inp inp-watch", type: "number", min: "50", step: "50", id: "watchInterval"
  });
  var after = el("select", { class: "inp sel-watch", id: "watchAfter" });
  [["continue", "watch_after_continue"],
   ["restart loop", "watch_after_loop"],
   ["restart macro", "watch_after_macro"]].forEach(function (pair) {
    after.appendChild(el("option", { value: pair[0], text: t(pair[1]) }));
  });

  enabled.addEventListener("change", async function () {
    await setSetting("watch_enabled", enabled.checked);
    syncWatchControls();
  });
  every.addEventListener("change", async function () {
    var n = Math.max(50, toInt(every.value, 400));
    every.value = n;
    await setSetting("watch_interval_ms", n);
  });
  after.addEventListener("change", async function () {
    await setSetting("watch_after", after.value);
  });

  var node = el("div", { class: "loop-ctl watch-ctl" }, [
    el("label", { class: "switch-row", title: t("watch_on_tip") }, [
      el("span", { class: "switch" }, [enabled, el("span", { class: "slider" })]),
      el("span", { text: t("watch_on_word") })
    ]),
    el("span", { class: "loop-x", text: t("watch_every") }), every,
    el("span", { class: "loop-x", text: t("watch_then") }), after
  ]);
  attachTip(node, t("tip_watch_title"), t("tip_watch_body"));
  syncWatchControlsIn(node);
  return node;
}

function syncWatchControlsIn(root) {
  var s = state.settings || {};
  var on = s.watch_enabled !== false;
  var enabled = $("#watchEnabled", root);
  var every = $("#watchInterval", root);
  var after = $("#watchAfter", root);
  if (enabled) enabled.checked = on;
  if (every) { every.value = Math.max(50, toInt(s.watch_interval_ms, 400)); every.disabled = !on; }
  if (after) { after.value = String(s.watch_after || "continue"); after.disabled = !on; }
}

function syncWatchControls() { syncWatchControlsIn(document); }

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
  if (phase && isSelected(phase, block.id)) row.classList.add("sel");

  /* drag handle -- the row only becomes draggable while the grip is held */
  var grip = el("div", { class: "grip", title: t("tip_drag_reorder") }, [icon("i-grip")]);
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
    text: spec ? spec.label : prettyType(block.type)
  });
  attachTip(typeLabel, spec ? spec.label : prettyType(block.type),
            ((spec && spec.desc) ? spec.desc + "\n\n" : "")
            + t("tip_toggle_block"));
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
  /* The Pick button belongs to the same x/y pair the catalog declares, so it
     rides along in `conditional` and disappears with them (Focus Target only
     has coordinates when "Move" is on). */
  if (hasXY(spec)) {
    var coordField = { key: "__coords" };
    var coordNode = coordPickButton(block, ctx);
    fields.appendChild(coordNode);
    conditional.push({ f: coordField, node: coordNode });
  }

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
      class: "btn btn-xs rowbtn-edit", text: t("row_edit_actions"),
      title: t("row_edit_actions_tip")
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
      class: "btn btn-xs rowbtn-edit", text: t("row_preview"),
      title: t("row_preview_tip")
    });
    previewBtn.addEventListener("click", function () { previewWebhookSource(block); });
    extra.push(previewBtn);
  }

  var actions = [];
  if (ctx.full) {
    var onceBtn = el("button", {
      class: "once-toggle" + (block.once ? " on" : ""), text: t("btn_once"),
      title: t("tip_once")
    });
    onceBtn.addEventListener("click", function () {
      block.once = !block.once;
      onceBtn.classList.toggle("on", block.once);
      ctx.changed();
    });

    var runBtn = el("button", { class: "iconbtn go", title: t("tip_run_block") }, [icon("i-play", "ic-xs")]);
    runBtn.addEventListener("click", function () { runSingle(block, row); });

    var dupBtn = el("button", { class: "iconbtn", title: t("btn_duplicate") }, [icon("i-copy", "ic-xs")]);
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
    var upBtn = el("button", { class: "iconbtn", title: t("btn_move_up"), text: "↑" });
    upBtn.disabled = index === 0;
    upBtn.addEventListener("click", function () { moveInList(ctx, block, -1); });
    var downBtn = el("button", { class: "iconbtn", title: t("btn_move_down"), text: "↓" });
    downBtn.disabled = index >= ctx.list().length - 1;
    downBtn.addEventListener("click", function () { moveInList(ctx, block, 1); });
    actions.push(upBtn, downBtn);
  }

  var delBtn = el("button", { class: "iconbtn danger", title: t("btn_delete") }, [icon("i-trash", "ic-xs")]);
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
  /* The ordinal doubles as the tick box for "save as group". It is the one
     spot on the row that carries no editor of its own, so clicking it can
     never be confused with editing a field. */
  var ord = el("div", {
    class: "row-ord" + (ctx.full && phase ? " pickable" : ""),
    text: "#" + (index + 1)
  });
  if (ctx.full && phase) {
    attachTip(ord, t("grp_pick_title"), t("grp_pick_body"));
    ord.addEventListener("click", function () { toggleSelected(phase, block.id); });
  }
  row.appendChild(ord);
  row.appendChild(fields);
  /* Keep every block-level action in one stable cell.  Putting the edit/
     preview button beside the fields as a direct flex child made it compete
     with .row-actions and wrap onto a different line on narrow windows. */
  var rowActions = el("div", { class: "row-actions" });
  extra.forEach(function (node) { rowActions.appendChild(node); });
  actions.forEach(function (node) { rowActions.appendChild(node); });
  row.appendChild(rowActions);
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
  askConfirm(tf("ask_clear_phase", label), t("ask_clear_phase_body"))
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
    toast(t("toast_run_failed") + ": " + (result.reason || "unknown"), "err");
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

/* `title` and `body` may be functions, for the few tips that are wired once
   but whose text has to follow the interface language. */
function attachTip(node, title, body) {
  if (!body) return node;
  node.addEventListener("mouseenter", function () {
    if (tipTimer) clearTimeout(tipTimer);
    tipTimer = setTimeout(function () {
      showTip(node,
              typeof title === "function" ? title() : title,
              typeof body === "function" ? body() : body);
    }, 220);
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
  /* Read Text only compares when asked to; a "Value" next to "off" is a
     box whose contents change nothing. */
  if (block.type === "read_text" && f.key === "expect") {
    var cmp = String(params.compare || "off");
    return cmp !== "off" && cmp !== "";
  }
  /* Camera Setup: a sweep has no step count and an exact turn has no sweep,
     so only one of the two is ever a real setting. */
  if (block.type === "mouse_look") {
    var toLimit = String(params.mode || "to limit") !== "exact";
    if (f.key === "sweep_px") return toLimit;
    if (f.key === "steps") return !toLimit;
  }
  if (block.type === "send_webhook" && f.key === "region") {
    return String(params.source || "") === "region";
  }
  if (block.type === "send_webhook" && f.key === "template") {
    return String(params.source || "") === "saved image";
  }
  /* Focus Target only resizes when asked to, and only moves when asked to --
     a Width next to a switched-off "Resize" is a number that does nothing. */
  if (block.type === "focus_window") {
    if (f.key === "width" || f.key === "height") return !!params.resize;
    if (f.key === "x" || f.key === "y" || f.key === "__coords") return !!params.move;
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
    case "map_point": return fieldMapPoint(block, f);
    case "coord": return null;
    case "condition":  return fieldCondition(block, f);
    case "conditions": return fieldConditions(block, f);
    case "filepath":   return fieldFilepath(block, f);
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
  var btn = el("button", { class: "keybtn" + (value ? "" : " empty"), text: value || t("key_press_prompt") });
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
    btn.textContent = (f.label || t("blocks_edit_title")) + " (" + list.length + ")";
    btn.classList.toggle("filled", list.length > 0);
    btn.title = list.length ? tf("blocks_field_tip", list.length) : t("blocks_field_empty_tip");
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
  var empty = el("span", { class: "region-null", text: t("region_full") });

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

  var pick = el("button", { class: "pickbtn", title: t("tip_pick_region") },
    [icon("i-target", "ic-xs"), el("span", { text: t("btn_pick") })]);
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

  var pick = el("button", { class: "pickbtn", title: t("tip_pick_color") },
    [icon("i-target", "ic-xs"), el("span", { text: t("btn_pick") })]);
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
    name.textContent = value || t("tpl_choose");
    btn.classList.toggle("empty", !value);
    btn.title = value ? tf("tpl_chosen", value) : t("tpl_empty_tip");
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

/* --------------------------------------------------------------------------
   kind: "map_point" -- a spot on one of the user's own map screenshots.

   Stored as [map name, x, y, image width, image height]. The size of the
   picture the spot was picked on travels with it so the runner can scale the
   point onto a game window of a different size; without it the same macro
   placed units further and further off the moment the window changed.
   -------------------------------------------------------------------------- */
function fieldMapPoint(block, f) {
  var btn = el("button", { class: "tplbtn", type: "button" });
  var name = el("span", { class: "tplbtn-name" });
  btn.appendChild(name);

  function label() {
    var value = block.params[f.key];
    var set = Array.isArray(value) && value.length >= 3;
    var where = set ? (Math.round(value[1]) + "," + Math.round(value[2])) : "";
    name.textContent = set ? (value[0] + " · " + where) : t("map_pick_prompt");
    btn.classList.toggle("empty", !set);
    btn.title = set ? tf("map_pick_chosen", value[0], where) : t("map_pick_empty_tip");
  }
  label();

  btn.addEventListener("click", function (e) {
    e.preventDefault();
    /* The block's own id is passed so the picker can leave this block's dot
       out of the "already placed" markers -- otherwise every re-open showed
       the spot twice, once as itself and once as a neighbour. */
    openMapPicker(block.params[f.key], block.id).then(function (chosen) {
      if (chosen === undefined) return;                     /* cancelled */
      block.params[f.key] = chosen;
      label();
      markDirty();
    });
  });

  var node = wrapField(f.label || f.key, btn, f.help);
  node._syncField = label;
  return node;
}

var mapPick = { resolve: null, selfId: "", map: "", point: null, width: 0, height: 0, list: [], bound: false };

/* Every spot other Place Unit blocks use on this map, so two units are not
   stacked on one tile by accident. Nested lists are walked too: a unit placed
   inside an on-fail branch occupies the same ground as one in the main list. */
function placedUnitsOnMap(mapName, selfId) {
  var out = [];
  if (!mapName) return out;

  function walk(list) {
    (list || []).forEach(function (b) {
      if (!b || typeof b !== "object") return;
      var params = b.params || {};
      if (b.type === "place_unit" && b.id !== selfId) {
        var loc = params.location;
        if (Array.isArray(loc) && loc.length >= 5 && String(loc[0]) === String(mapName)) {
          out.push({
            x: Number(loc[1]) || 0, y: Number(loc[2]) || 0,
            w: Number(loc[3]) || 0, h: Number(loc[4]) || 0,
            unit: String(params.unit || "?")
          });
        }
      }
      Object.keys(params).forEach(function (key) {
        var value = params[key];
        /* Only nested BLOCK lists, which is what a first element with a type
           means -- a map point is an array too, and recursing into it threw. */
        if (Array.isArray(value) && value.length && value[0] && value[0].type) walk(value);
      });
    });
  }
  walk(phaseArray("setup"));
  walk(phaseArray("loop"));
  return out;
}

function mapMark(leftPct, topPct, label, kind) {
  return el("div", {
    class: "map-mark map-mark-" + kind,
    style: "left:" + leftPct + "%;top:" + topPct + "%",
    title: String(label || "")
  }, [
    el("span", { class: "map-mark-dot" }),
    el("span", { class: "map-mark-label", text: String(label || "") })
  ]);
}

function renderMapPickMarks() {
  var host = $("#mapPickMarks");
  if (!host) return;
  host.innerHTML = "";
  if (!mapPick.width || !mapPick.height) return;

  placedUnitsOnMap(mapPick.map, mapPick.selfId).forEach(function (u) {
    /* Each neighbour is scaled by the size IT was picked at, not by this
       picture's -- two blocks can hold the same map from before it was
       re-imported at another resolution. */
    var w = u.w || mapPick.width, h = u.h || mapPick.height;
    host.appendChild(mapMark(u.x / w * 100, u.y / h * 100, u.unit, "other"));
  });
  if (mapPick.point) {
    host.appendChild(mapMark(mapPick.point[0] / mapPick.width * 100,
                             mapPick.point[1] / mapPick.height * 100,
                             t("mappick_this"), "self"));
  }
}

function syncMapPickReadout() {
  var readout = $("#mapPickCurrent");
  if (readout) {
    readout.textContent = mapPick.point
      ? (mapPick.map + " · " + mapPick.point[0] + "," + mapPick.point[1])
      : t("mappick_no_spot");
  }
  var apply = $("#btnMapPickApply");
  if (apply) apply.disabled = !(mapPick.point && mapPick.map && mapPick.width);
}

async function refreshMapPickList() {
  var list = await apiQ("list_maps");
  mapPick.list = Array.isArray(list) ? list.slice() : [];
  /* A map file deleted behind the app's back stays in the list, marked: the
     block still points at it, and quietly dropping it would let Apply write
     a different map than the one the row says. */
  if (mapPick.map && mapPick.list.indexOf(mapPick.map) < 0) mapPick.list.push(mapPick.map);
  /* Only auto-picked when there is nothing to choose between -- with several
     maps the gallery opens instead, so the first one is not silently used. */
  if (!mapPick.map && mapPick.list.length === 1) mapPick.map = mapPick.list[0];
  syncMapPickChoose();
  if (mapGal.open) renderMapGallery();
}

function syncMapPickChoose() {
  var name = $("#mapPickChosenName");
  var known = mapPick.map && mapPick.list.indexOf(mapPick.map) >= 0;
  if (name) {
    name.textContent = mapPick.map
      ? (mapPick.map + (known ? "" : " " + t("missing_suffix")))
      : t("mapgal_none");
  }
  var btn = $("#btnMapPickChoose");
  if (btn) {
    btn.classList.toggle("empty", !mapPick.map);
    btn.title = tf("mapgal_choose_tip", mapPick.list.length);
  }
}

/* --------------------------------------------------------------------------
   The map gallery -- the pictures themselves, laid out.

   A dropdown of file names was useless for this: the whole question is which
   picture, and "forest2" and "forest_new" are indistinguishable until you
   look at them. It sits on top of the spot picker rather than replacing it,
   so switching maps does not throw away the picker's state.
   -------------------------------------------------------------------------- */
var mapGal = { open: false, filter: "" };

function closeMapGallery() {
  mapGal.open = false;
  var overlay = $("#mapGalleryModal");
  if (overlay) overlay.classList.add("hidden");
}

function openMapGallery() {
  var overlay = $("#mapGalleryModal");
  if (!overlay) return;
  mapGal.open = true;
  mapGal.filter = "";
  var filter = $("#mapGalFilter");
  if (filter) filter.value = "";
  overlay.classList.remove("hidden");
  renderMapGallery();
  if (filter) filter.focus();
}

function chooseMapFromGallery(name) {
  closeMapGallery();
  if (name === mapPick.map) return;
  mapPick.map = name;
  /* A spot belongs to the picture it was clicked on, so switching maps drops
     it rather than carrying the old coordinates onto another map. */
  mapPick.point = null;
  syncMapPickChoose();
  showMapPickImage(mapPick.map);
}

function mapGalleryCard(name) {
  var on = name === mapPick.map;
  var card = el("button", { class: "tplpick-card mapgal-card" + (on ? " on" : ""), type: "button" });
  var thumb = el("div", { class: "tpl-thumb" }, [el("span", { class: "hint", text: "..." })]);
  var meta = el("div", { class: "tpl-meta mapgal-meta" });
  /* What is already on a map is usually the reason to pick one over another. */
  var units = placedUnitsOnMap(name, mapPick.selfId).length;

  card.appendChild(thumb);
  card.appendChild(el("div", { class: "tpl-name", text: name }));
  card.appendChild(meta);

  mapThumb(name).then(function (info) {
    thumb.innerHTML = "";
    meta.innerHTML = "";
    if (info && info.ok) {
      thumb.appendChild(el("img", { src: info.image, alt: name }));
      meta.appendChild(el("span", { text: info.width + "×" + info.height }));
    } else {
      thumb.appendChild(el("span", { class: "hint", text: t("img_no_preview") }));
      meta.appendChild(el("span", { class: "hint", text: t("missing_suffix") }));
    }
    if (units) meta.appendChild(el("span", { class: "mapgal-units", text: tf("mapgal_units", units) }));
    if (on) meta.appendChild(el("span", { class: "mapgal-cur", text: t("mapgal_current") }));
  });

  card.addEventListener("click", function (e) {
    e.preventDefault();
    chooseMapFromGallery(name);
  });
  return card;
}

function renderMapGallery() {
  var grid = $("#mapGalGrid"), empty = $("#mapGalEmpty"), count = $("#mapGalCount");
  if (!grid) return;
  var needle = String(mapGal.filter || "").trim().toLowerCase();
  var shown = (mapPick.list || []).filter(function (name) {
    return !needle || String(name).toLowerCase().indexOf(needle) >= 0;
  });

  grid.innerHTML = "";
  shown.forEach(function (name) { grid.appendChild(mapGalleryCard(name)); });
  if (count) count.textContent = tf("mapgal_count", shown.length);
  if (empty) {
    empty.classList.toggle("hidden", shown.length > 0);
    /* "nothing here" and "nothing matches your filter" are different
       problems, and only one of them is fixed by adding a picture. */
    empty.textContent = (mapPick.list || []).length ? t("mapgal_no_match") : t("mappick_empty");
  }
}

/* Shared by the picker's foot button and the gallery's, so a picture added
   from either place lands in the same state: chosen, on screen, in the grid. */
async function importMapIntoPicker() {
  var result = await api("import_map");
  if (!result || !result.ok) {
    if (result && result.reason !== "cancelled") toast(t("mappick_load_failed"), "err");
    return;
  }
  mapPick.map = result.name;
  mapPick.point = null;
  await refreshMaps();                 /* Images grid + the thumbnail cache */
  await refreshMapPickList();
  closeMapGallery();
  await showMapPickImage(mapPick.map);
  toast(tf("mappick_added", result.name));
}

async function showMapPickImage(name) {
  var img = $("#mapPickImg"), empty = $("#mapPickEmpty"), marks = $("#mapPickMarks");
  if (!img || !empty) return;
  if (marks) marks.innerHTML = "";

  if (!name) {
    img.classList.add("hidden");
    img.removeAttribute("src");
    empty.classList.remove("hidden");
    empty.textContent = t("mappick_empty");
    mapPick.width = mapPick.height = 0;
    syncMapPickReadout();
    return;
  }
  empty.classList.remove("hidden");
  empty.textContent = t("mappick_loading");

  var result = await api("get_map", name);
  /* A slow load must not paint over a map chosen since. */
  if (mapPick.map !== name) return;
  if (!result || !result.ok) {
    img.classList.add("hidden");
    img.removeAttribute("src");
    empty.textContent = t("mappick_load_failed");
    mapPick.width = mapPick.height = 0;
    syncMapPickReadout();
    return;
  }
  mapPick.width = Number(result.width) || 0;
  mapPick.height = Number(result.height) || 0;
  img.src = result.image;
  img.classList.remove("hidden");
  empty.classList.add("hidden");
  renderMapPickMarks();
  syncMapPickReadout();
}

function closeMapPicker(value) {
  closeMapGallery();
  var overlay = $("#mapPickModal");
  if (overlay) overlay.classList.add("hidden");
  var resolve = mapPick.resolve;
  mapPick.resolve = null;
  if (resolve) resolve(value);
}

/* Wired once and left in place: the handlers read mapPick, so re-binding on
   every open would only pile up duplicates on the same buttons. */
function bindMapPicker() {
  if (mapPick.bound) return;
  mapPick.bound = true;

  var img = $("#mapPickImg");
  if (img) {
    img.addEventListener("click", function (e) {
      if (!mapPick.width || !mapPick.height) return;
      var rect = img.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      /* Measured against the rendered box, not offsetX: the picture is scaled
         to fit the modal, so screen pixels have to be turned back into the
         picture's own pixels -- that is what the runner scales from. */
      mapPick.point = [
        clamp(Math.round((e.clientX - rect.left) / rect.width * mapPick.width), 0, mapPick.width - 1),
        clamp(Math.round((e.clientY - rect.top) / rect.height * mapPick.height), 0, mapPick.height - 1)
      ];
      renderMapPickMarks();
      syncMapPickReadout();
    });
  }

  var choose = $("#btnMapPickChoose");
  if (choose) {
    choose.addEventListener("click", function (e) {
      e.preventDefault();
      openMapGallery();
    });
  }

  var galFilter = $("#mapGalFilter");
  if (galFilter) {
    galFilter.addEventListener("input", function () {
      mapGal.filter = galFilter.value;
      renderMapGallery();
    });
  }
  var galImport = $("#btnMapGalImport");
  if (galImport) galImport.addEventListener("click", function () { importMapIntoPicker(); });
  var galFolder = $("#btnMapGalFolder");
  if (galFolder) galFolder.addEventListener("click", function () { api("open_maps_folder"); });
  ["#btnMapGalCancel", "#btnMapGalClose"].forEach(function (sel) {
    var node = $(sel);
    if (node) node.addEventListener("click", function () { closeMapGallery(); });
  });

  var importBtn = $("#btnMapPickImport");
  if (importBtn) importBtn.addEventListener("click", function () { importMapIntoPicker(); });

  var folderBtn = $("#btnMapPickFolder");
  if (folderBtn) folderBtn.addEventListener("click", function () { api("open_maps_folder"); });

  var applyBtn = $("#btnMapPickApply");
  if (applyBtn) {
    applyBtn.addEventListener("click", function () {
      if (!mapPick.point || !mapPick.map || !mapPick.width) {
        toast(t("mappick_need_spot"), "err");
        return;
      }
      closeMapPicker([mapPick.map, mapPick.point[0], mapPick.point[1],
                      mapPick.width, mapPick.height]);
    });
  }
  var clearBtn = $("#btnMapPickClear");
  if (clearBtn) clearBtn.addEventListener("click", function () { closeMapPicker(null); });
  ["#btnMapPickCancel", "#btnMapPickClose"].forEach(function (sel) {
    var node = $(sel);
    if (node) node.addEventListener("click", function () { closeMapPicker(undefined); });
  });

  /* Capture phase: the global Escape handler would hide the overlay behind
     this promise's back and strand the field waiting for an answer. */
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || !mapPick.resolve) return;
    e.preventDefault();
    e.stopPropagation();
    /* The gallery sits on top: Escape there means "keep the map I had", not
       "cancel the whole pick". */
    if (mapGal.open) { closeMapGallery(); return; }
    closeMapPicker(undefined);
  }, true);
}

/* Resolves with [map, x, y, width, height], null to clear the spot, or
   undefined when the picker was dismissed. */
function openMapPicker(current, selfId) {
  return new Promise(function (resolve) {
    var overlay = $("#mapPickModal");
    if (!overlay) { resolve(undefined); return; }
    /* Opening a second one over the first would strand the first promise. */
    closeMapPicker(undefined);

    var value = Array.isArray(current) && current.length >= 3 ? current : null;
    mapPick.resolve = resolve;
    mapPick.selfId = selfId || "";
    mapPick.map = value ? String(value[0] || "") : "";
    mapPick.point = value ? [Math.round(Number(value[1]) || 0), Math.round(Number(value[2]) || 0)] : null;
    mapPick.width = mapPick.height = 0;

    bindMapPicker();
    overlay.classList.remove("hidden");
    syncMapPickReadout();

    refreshMapPickList().then(function () {
      /* Nothing chosen yet: the gallery is what there is to do next, rather
         than an empty stage with a button to discover. */
      if (!mapPick.map && mapPick.list.length) {
        openMapGallery();
        return null;
      }
      return showMapPickImage(mapPick.map);
    });
  });
}


/* --------------------------------------------------------------------------
   kind: "filepath" -- text + Browse button
   -------------------------------------------------------------------------- */
function fieldFilepath(block, f) {
  var input = el("input", { class: "inp f-text", type: "text", spellcheck: "false",
    placeholder: "C:\\path\\to\\app.exe" });
  input.value = block.params[f.key] == null ? "" : String(block.params[f.key]);
  input.addEventListener("input", function () {
    block.params[f.key] = input.value; markDirty();
  });
  var browse = el("button", { class: "pickbtn", type: "button", title: "Browse" },
    [el("span", { text: "..." })]);
  browse.addEventListener("click", function () {
    api("pick_exe_path").then(function (res) {
      if (res && res.ok) { block.params[f.key] = res.path; input.value = res.path; markDirty(); }
    });
  });
  return wrapField(f.label || f.key, el("div", { class: "inline-group" }, [input, browse]), f.help);
}

/* --------------------------------------------------------------------------
   kind: "condition" / "conditions" -- visual condition builder
   -------------------------------------------------------------------------- */
var _condTypes = null;
function loadCondTypes(cb) {
  if (_condTypes) { cb(_condTypes); return; }
  api("get_condition_types").then(function (types) {
    _condTypes = Array.isArray(types) ? types : [];
    cb(_condTypes);
  }).catch(function () { _condTypes = []; cb([]); });
}

var COND_FIELD_NAMES = {
  text:           "Текст",
  region:         "Область",
  region2:        "Область 2",
  case_sensitive: "Учитывать регистр",
  template:       "Шаблон",
  template2:      "Шаблон 2",
  operator:       "Оператор",
  value:          "Значение",
  min:            "Минимум",
  max:            "Максимум",
  threshold:      "Порог",
  ms:             "Время (мс)",
  delta:          "Дельта",
  n:              "N",
  percent:        "Вероятность %",
  words:          "Слова (через запятую)",
  pattern:        "Шаблон regex",
  px:             "X точки",
  py:             "Y точки",
  x:              "X",
  y:              "Y",
  min_dist:       "Мин. расстояние",
  max_dist:       "Макс. расстояние",
  name:           "Имя процесса / заголовок",
  title:          "Заголовок окна",
  path:           "Путь к файлу",
  condition:      "Условие",
  conditions:     "Условия",
};

var COND_FIELD_NAMES_EN = {
  text: "Text", region: "Region", region2: "Region 2", case_sensitive: "Case sensitive",
  template: "Image", template2: "Image 2", operator: "Operator", value: "Value",
  min: "Minimum", max: "Maximum", threshold: "Confidence", ms: "Time (ms)", delta: "Delta",
  n: "N", percent: "Chance %", words: "Words (comma-separated)", pattern: "Regex pattern",
  px: "Point X", py: "Point Y", x: "X", y: "Y", min_dist: "Min distance", max_dist: "Max distance",
  name: "Process name / window title", title: "Window title", path: "File path",
  condition: "Condition", conditions: "Conditions"
};

var COND_GROUP_NAMES_EN = {
  "Текст": "Text", "Числа": "Numbers", "Изображение": "Image", "Расстояние": "Distance",
  "Система": "System", "Макрос": "Macro", "Логика": "Logic"
};

var COND_TYPE_NAMES_EN = {
  text_contains:"Text contains", text_not_contains:"Text does not contain", text_equals:"Text equals",
  text_starts_with:"Text starts with", text_ends_with:"Text ends with", text_is_empty:"Text is empty",
  text_is_not_empty:"Text is not empty", text_length:"Text length", text_word_count:"Word count",
  text_is_number:"Text is a number", text_matches_regex:"Text matches regex", text_is_date:"Text is a date",
  text_is_time:"Text is a time", text_all_caps:"Text is uppercase", text_contains_any_of:"Text contains any of",
  text_contains_all_of:"Text contains all of", text_changed:"Text changed", text_stable_for:"Text stable for",
  text_same_in_regions:"Text same in two regions", text_different_in_regions:"Text different in two regions",
  text_count:"Text count", text_present_anywhere:"Text appears on screen", text_near_image:"Text near image",
  number_compare:"Compare number", number_in_range:"Number in range", number_changed:"Number changed",
  number_increased:"Number increased", number_decreased:"Number decreased", number_delta:"Number delta",
  ratio_compare:"Compare numbers in two regions", image_present:"Image present", image_absent:"Image absent",
  image_count:"Image count", pixel_brightness:"Pixel brightness", images_same:"Images same",
  color_changed:"Color changed at point", screen_frozen:"Screen frozen", distance_from_point:"Distance from point",
  distance_between_images:"Distance between images", image_in_ring:"Image in ring", images_clustered:"Images clustered",
  image_moving_toward:"Image moving toward point", images_overlap:"Images overlap", process_running:"Process running",
  window_exists:"Window exists", file_exists:"File exists", loop_iteration:"Loop iteration", random_chance:"Random chance",
  not:"NOT (invert)", and:"AND (all true)", or:"OR (any true)", xor:"XOR (exactly one)", n_of:"N of (at least N)"
};

function condIsRussian() {
  return String(state.settings.language || "en").toLowerCase().startsWith("ru");
}
function condGroupLabel(group) {
  return condIsRussian() ? group : (COND_GROUP_NAMES_EN[group] || prettyType(group));
}

function condLabel(cond) {
  if (!cond || !cond.type) return "\u2014";
  if (!condIsRussian() && COND_TYPE_NAMES_EN[cond.type]) return COND_TYPE_NAMES_EN[cond.type];
  if (_condTypes) {
    var spec = _condTypes.find(function (s) { return s.type === cond.type; });
    if (spec && spec.label) return spec.label;
  }
  return cond.type.replace(/_/g, " ");
}

function condValueText(value) {
  if (value === null || value === undefined || value === "") return "…";
  if (typeof value === "object") {
    if (value.x !== undefined && value.y !== undefined) return "region";
    return "…";
  }
  var text = String(value);
  return text.length > 28 ? text.slice(0, 25) + "…" : text;
}

function condOperatorText(value) {
  return ({equals:"==", "not equals":"!=", greater:">", "greater or equal":">=", less:"<", "less or equal":"<=", contains:"contains", "not contains":"does not contain"})[value] || value || "?";
}

function condExpression(cond) {
  if (!cond || !cond.type) return "…";
  var p = cond.params || {};
  if (["and", "or", "xor", "n_of"].indexOf(cond.type) >= 0) {
    var nested = Array.isArray(p.conditions) ? p.conditions.map(condExpression) : [];
    var joiner = cond.type === "or" ? " OR " : cond.type === "xor" ? " XOR " : cond.type === "n_of" ? " · " : " AND ";
    var body = nested.length ? nested.join(joiner) : "…";
    return cond.type === "n_of" ? "at least " + condValueText(p.n) + " of (" + body + ")" : "(" + body + ")";
  }
  var left = condLabel(cond);
  if (p.operator && p.value !== undefined) {
    return condValueText(p.region || p.template || p.text || left) + " " + condOperatorText(p.operator) + " " + condValueText(p.value);
  }
  if (p.text !== undefined && p.text !== "") return left + " \"" + condValueText(p.text) + "\"";
  if (p.template) return left + " [" + condValueText(p.template) + "]";
  return left;
}

function fieldCondition(block, f) {
  var btn = el("button", { class: "blocksbtn", type: "button" });
  function sync() {
    var c = block.params[f.key];
    btn.textContent = (c && c.type) ? "IF " + condExpression(c) : t("cond_choose");
    btn.classList.toggle("filled", !!(c && c.type));
  }
  sync();
  btn.addEventListener("click", function (e) {
    e.preventDefault();
    openConditionEditor(block.params[f.key] || null, function (cond) {
      block.params[f.key] = cond; sync(); markDirty();
    });
  });
  return wrapField(f.label || f.key, btn, f.help);
}

function fieldConditions(block, f) {
  if (!Array.isArray(block.params[f.key])) block.params[f.key] = [];
  var chain = el("div", { class: "cond-inline-chain" });
  var logic = block.type === "or" ? "OR" : block.type === "xor" ? "XOR" : block.type === "n_of" ? "N OF" : "AND";

  function rebuild() {
    chain.innerHTML = "";
    var list = block.params[f.key] || [];
    chain.appendChild(el("div", { class: "cond-inline-title", text: condIsRussian() ? "Составные условия" : "Combined conditions" }));
    if (!list.length) {
      chain.appendChild(el("div", { class: "cond-inline-empty", text: condIsRussian() ? "Добавьте первое условие ниже" : "Add the first condition below" }));
    }
    list.forEach(function (cond, index) {
      if (index > 0) chain.appendChild(el("div", { class: "cond-inline-connector" }, [
        el("span", { class: "cond-chain-line" }),
        el("span", { class: "cond-chain-operator", text: logic }),
        el("span", { class: "cond-chain-line" })
      ]));
      var card = el("div", { class: "cond-inline-card" });
      card.appendChild(el("span", { class: "cond-inline-number", text: String(index + 1) }));
      card.appendChild(el("span", { class: "cond-inline-expression", text: condExpression(cond) }));
      var edit = el("button", { class: "btn btn-xs", text: condIsRussian() ? "Изменить" : "Edit" });
      edit.addEventListener("click", function () {
        openConditionEditor(cond, function (next) { if (next) { list[index] = next; rebuild(); markDirty(); } });
      });
      var remove = el("button", { class: "btn btn-xs btn-danger", text: "×" });
      remove.addEventListener("click", function () { list.splice(index, 1); rebuild(); markDirty(); });
      card.appendChild(edit); card.appendChild(remove); chain.appendChild(card);
    });
    var add = el("button", { class: "btn btn-sm cond-inline-add", text: "+ " + (condIsRussian() ? "Добавить условие" : "Add condition") });
    add.addEventListener("click", function () {
      openConditionEditor(null, function (next) { if (next) { list.push(next); rebuild(); markDirty(); } });
    });
    chain.appendChild(add);
  }
  rebuild();
  return wrapField(f.label || f.key, chain, f.help);
}

function openConditionEditor(current, onSave) {
  loadCondTypes(function (types) {
    var overlay = el("div", { class: "overlay cond-overlay" });
    var modal = el("div", { class: "modal cond-modal cond-simple-modal" });
    var details = el("div", { class: "cond-details cond-simple-details" });
    var typeSelect = el("select", { class: "inp cond-type-select" });
    var working = current ? JSON.parse(JSON.stringify(current)) : null;
    var expression = el("div", { class: "cond-expression-preview" });

    var groupOrder = ["Текст", "Числа", "Изображение", "Расстояние", "Система", "Макрос", "Логика"];
    var grouped = {};
    types.forEach(function (spec) { (grouped[spec.group] = grouped[spec.group] || []).push(spec); });
    Object.keys(grouped).sort(function (a, b) {
      var ai = groupOrder.indexOf(a), bi = groupOrder.indexOf(b);
      return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi);
    }).forEach(function (group) {
      var optgroup = document.createElement("optgroup");
      optgroup.label = condGroupLabel(group);
      grouped[group].sort(function (a, b) {
        return condLabel({ type: a.type }).localeCompare(condLabel({ type: b.type }));
      }).forEach(function (spec) {
        optgroup.appendChild(el("option", {
          value: spec.type,
          text: condLabel({ type: spec.type })
        }));
      });
      typeSelect.appendChild(optgroup);
    });

    var logicButtons = el("div", { class: "cond-logic-buttons" });
    var logicNames = [
      ["and", "AND", "all conditions must be true", "все условия должны быть истинны"],
      ["or", "OR", "any condition can be true", "достаточно одного условия"],
      ["xor", "XOR", "exactly one must be true", "истинно ровно одно"],
      ["n_of", "N OF", "at least N conditions", "минимум N условий"]
    ];
    logicNames.forEach(function (entry) {
      var button = el("button", {
        class: "btn cond-logic-btn",
        type: "button",
        text: entry[1],
        title: condIsRussian() ? entry[3] : entry[2]
      });
      button.dataset.logic = entry[0];
      button.addEventListener("click", function () {
        typeSelect.value = entry[0];
        renderDetails();
      });
      logicButtons.appendChild(button);
    });

    function refreshExpression() {
      expression.textContent = working && working.type
        ? "IF " + condExpression(working)
        : (condIsRussian() ? "ЕСЛИ выберите условие..." : "IF choose a condition...");
    }
    function renderDetails() {
      var spec = types.find(function (s) { return s.type === typeSelect.value; });
      details.innerHTML = "";
      if (!spec) {
        details.appendChild(el("p", { class: "cond-hint", text: condIsRussian() ? "Выберите условие выше" : "Choose a condition above" }));
        refreshExpression();
        return;
      }
      if (!working || working.type !== spec.type) {
        working = { type: spec.type, params: {} };
        (spec.fields || []).forEach(function (fd) {
          working.params[fd.key] = fd.default !== undefined ? fd.default : null;
        });
      }
      (spec.fields || []).forEach(function (fd) {
        var node = renderCondField(working, fd);
        if (node) details.appendChild(node);
      });
      refreshExpression();
      logicButtons.querySelectorAll(".cond-logic-btn").forEach(function (button) {
        button.classList.toggle("active", button.dataset.logic === typeSelect.value);
      });
    }

    if (working && working.type) typeSelect.value = working.type;
    else typeSelect.selectedIndex = -1;
    typeSelect.addEventListener("change", renderDetails);
    details.addEventListener("input", refreshExpression);
    details.addEventListener("change", refreshExpression);
    renderDetails();

    var btnCancel = el("button", { class: "btn", text: t("btn_cancel") });
    var btnClear  = el("button", { class: "btn btn-danger", text: t("cond_clear") });
    var btnSave   = el("button", { class: "btn btn-primary", text: t("btn_ok") });
    function close() { if (document.body.contains(overlay)) document.body.removeChild(overlay); }
    btnCancel.addEventListener("click", close);
    btnClear.addEventListener("click",  function () { onSave(null); close(); });
    btnSave.addEventListener("click",   function () { onSave(working ? JSON.parse(JSON.stringify(working)) : null); close(); });

    modal.appendChild(expression);
    modal.appendChild(el("div", { class: "cond-simple-picker" }, [
      el("div", { class: "cond-step", text: condIsRussian() ? "1. Что проверяем?" : "1. What are we checking?" }),
      el("div", { class: "cond-hint", text: condIsRussian() ? "Выберите действие, которое должно быть истинным." : "Choose the statement that should be true." }),
      el("div", { class: "cond-logic-label", text: condIsRussian() ? "Логика нескольких условий" : "Combine multiple conditions" }),
      logicButtons,
      el("label", { class: "cond-type-label", text: condIsRussian() ? "Условие" : "Condition" }),
      typeSelect
    ]));
    modal.appendChild(el("div", { class: "cond-simple-form" }, [
      el("div", { class: "cond-step", text: condIsRussian() ? "2. Заполните значения" : "2. Fill in the values" }),
      details
    ]));
    modal.appendChild(el("div", { class: "modal-foot cond-footer" }, [btnClear, btnCancel, btnSave]));
    overlay.appendChild(modal);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
    document.body.appendChild(overlay);
  });
}

function renderCondField(cond, f) {
  var fRu = Object.assign({}, f, {
    label: (condIsRussian() ? COND_FIELD_NAMES[f.key] : COND_FIELD_NAMES_EN[f.key]) || f.label || f.key
  });
  var proxy = { type: cond.type, params: cond.params || (cond.params = {}) };
  f = fRu;
  switch (f.kind) {
    case "int":        return fieldNumber(proxy, f, null, true);
    case "float":      return fieldNumber(proxy, f, null, false);
    case "text":       return fieldText(proxy, f);
    case "bool":       return fieldBool(proxy, f);
    case "choice":     return fieldChoice(proxy, f);
    case "region":     return fieldRegion(proxy, f);
    case "template":   return fieldTemplate(proxy, f);
    case "condition":  return fieldCondition(proxy, f);
    case "conditions": return fieldConditions(proxy, f);
    default:           return fieldText(proxy, f);
  }
}

function openConditionsListEditor(list, onSave, logicType) {
  var working = Array.isArray(list) ? JSON.parse(JSON.stringify(list)) : [];
  var overlay = el("div", { class: "overlay cond-overlay" });
  var modal   = el("div", { class: "modal cond-modal-list" });
  var listEl  = el("div", { class: "cond-list" });

  function rebuild() {
    listEl.innerHTML = "";
    if (!working.length) {
      listEl.appendChild(el("p", { class: "cond-hint", text: t("cond_empty") }));
      return;
    }
    working.forEach(function (cond, i) {
      if (i > 0) {
        var link = el("div", { class: "cond-chain-link" });
        link.appendChild(el("span", { class: "cond-chain-line" }));
        var connector = logicType === "or" ? "OR" : logicType === "xor" ? "XOR" : logicType === "n_of" ? "N OF" : "AND";
        link.appendChild(el("span", { class: "cond-chain-operator", text: connector }));
        link.appendChild(el("span", { class: "cond-chain-line" }));
        listEl.appendChild(link);
      }
      var row     = el("div", { class: "cond-list-row cond-chain-row" });
      var keyword = el("span", { class: "cond-expression-keyword", text: i === 0 ? "IF" : "" });
      var lbl     = el("span", { class: "cond-list-label", text: cond && cond.type ? condExpression(cond) : "\u2014" });
      var btnEdit = el("button", { class: "btn btn-xs", text: "\u270e" });
      var btnDel  = el("button", { class: "btn btn-xs btn-danger", text: "\u2715" });
      var btnUp = el("button", { class: "btn btn-xs", text: "↑", title: condIsRussian() ? "Выше" : "Move up" });
      var btnDown = el("button", { class: "btn btn-xs", text: "↓", title: condIsRussian() ? "Ниже" : "Move down" });
      btnUp.disabled = i === 0; btnDown.disabled = i === working.length - 1;
      btnUp.addEventListener("click", function () { if (i > 0) { var item = working.splice(i, 1)[0]; working.splice(i - 1, 0, item); rebuild(); } });
      btnDown.addEventListener("click", function () { if (i < working.length - 1) { var item = working.splice(i, 1)[0]; working.splice(i + 1, 0, item); rebuild(); } });
      btnEdit.addEventListener("click", function () {
        openConditionEditor(cond, function (c) { if (c) { working[i] = c; rebuild(); } });
      });
      btnDel.addEventListener("click", function () { working.splice(i, 1); rebuild(); });
      row.appendChild(keyword); row.appendChild(lbl); row.appendChild(btnUp); row.appendChild(btnDown); row.appendChild(btnEdit); row.appendChild(btnDel);
      listEl.appendChild(row);
    });
  }
  rebuild();

  var btnAdd    = el("button", { class: "btn", text: t("cond_add") });
  var btnCancel = el("button", { class: "btn", text: t("btn_cancel") });
  var btnSave   = el("button", { class: "btn btn-primary", text: t("btn_ok") });
  function close() { if (document.body.contains(overlay)) document.body.removeChild(overlay); }
  btnAdd.addEventListener("click", function () {
    openConditionEditor(null, function (c) { if (c) { working.push(c); rebuild(); } });
  });
  btnCancel.addEventListener("click", close);
  btnSave.addEventListener("click", function () { onSave(JSON.parse(JSON.stringify(working))); close(); });

  modal.appendChild(el("div", {
    class: "cond-chain-head",
    text: (condIsRussian() ? "Логика: " : "Logic: ") +
      (logicType === "or" ? "OR — достаточно одного" : logicType === "xor" ? "XOR — ровно одно" : logicType === "n_of" ? "N OF — минимум N" : condIsRussian() ? "AND — все должны быть истинны" : "AND — all must be true")
  }));
  modal.appendChild(listEl);
  modal.appendChild(el("div", { class: "modal-foot cond-footer" }, [btnAdd, btnCancel, btnSave]));
  overlay.appendChild(modal);
  overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
  document.body.appendChild(overlay);
}

function fieldRecording(block, f) {
  var select = el("select", { class: "inp f-recording" });
  function fill() {
    var value = block.params[f.key] == null ? "" : String(block.params[f.key]);
    select.innerHTML = "";
    select.appendChild(el("option", { value: "", text: t("none_dash") }));
    state.recordings.forEach(function (name) {
      select.appendChild(el("option", { value: name, text: name }));
    });
    if (value && state.recordings.indexOf(value) < 0) {
      select.appendChild(el("option", { value: value, text: value + " " + t("missing_suffix") }));
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
  var btn = el("button", { class: "pickbtn", title: t("tip_pick_point") },
    [icon("i-target", "ic-xs"), el("span", { text: t("btn_pick") })]);
  btn.addEventListener("click", function () {
    if (ctx && ctx.phase) state.focusedCoord = { phase: ctx.phase, id: block.id };
    pickPointInto(block, ctx);
  });
  return wrapField(t("field_coords"), btn);
}

/* Every other block's x/y is measured inside the target window's client area,
   which is what pick_point returns. Focus Target is the exception: it moves
   the window itself, so its x/y are screen coordinates and MoveWindow reads
   them as such. Filling them with client coordinates put the window off by
   the client origin every time -- clicking where you wanted the corner threw
   the window off the top-left of the monitor. */
function screenCoordBlock(block) {
  return block && block.type === "focus_window";
}

async function pickPointInto(block, ctx) {
  var point = await pickPoint();
  if (!point || !point.ok) return;
  var screenSpace = screenCoordBlock(block);
  block.params.x = screenSpace && point.screen_x !== undefined ? point.screen_x : point.x;
  block.params.y = screenSpace && point.screen_y !== undefined ? point.screen_y : point.y;
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
  btn.textContent = t("key_pressing");

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
/* Takes a STRINGS key rather than finished text, and remembers it: the hint
   is written once and then sits there, so translating at the call site left
   "loaded" in English next to a fully Russian toolbar until the next save. */
function setSaveHint(key, saved) {
  var hint = $("#saveHint");
  state.saveHintKey = key || "";
  state.saveHintSaved = !!saved;
  if (!hint) return;
  hint.textContent = key ? t(key) : "";
  hint.classList.toggle("saved", !!saved);
}

function repaintSaveHint() {
  setSaveHint(state.saveHintKey, state.saveHintSaved);
}

function markDirty() {
  if (state.dirtySink) { state.dirtySink(); return; }
  setSaveHint(state.currentName ? "hint_unsaved" : "hint_not_saved", false);
  debounce("saveTimer", 800, function () {
    if (!state.currentName) return;
    autosave();
  });
}

async function autosave() {
  var result = await apiQ("save_macro", state.currentName, currentMacro());
  if (result && result.macros) state.macros = result.macros;
  setSaveHint(result ? "hint_saved" : "hint_save_failed", !!result);
}

async function saveMacroClicked() {
  var name = ($("#macroName").value || "").trim();
  if (!name) {
    name = await askText(t("ask_save_as"), "", t("ask_save_as_hint"));
    if (!name) return;
    $("#macroName").value = name;
  }
  var result = await api("save_macro", name, currentMacro());
  if (!result) return;
  state.currentName = result.name || name;
  $("#macroName").value = state.currentName;
  state.macro.name = state.currentName;
  if (result.macros) state.macros = result.macros;
  setSaveHint("hint_saved", true);
  toast(tf("toast_saved", state.currentName), "ok");
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
  setSaveHint("hint_loaded", true);
  toast(tf("toast_loaded", macro.name || name));
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
    menu.appendChild(el("div", { class: "menu-empty", text: t("menu_no_macros") }));
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
  var yes = await askConfirm(t("ask_new_title"), t("ask_new_body"));
  if (!yes) return;
  state.macro = { name: "", phases: { setup: [], loop: [] } };
  state.currentName = "";
  $("#macroName").value = "";
  renderPhases();
  setSaveHint("");
}

async function deleteMacro() {
  var name = state.currentName || ($("#macroName").value || "").trim();
  if (!name) { toast(t("toast_nothing_delete"), "err"); return; }
  var yes = await askConfirm(tf("ask_delete_title", name), t("ask_delete_body"));
  if (!yes) return;
  var result = await api("delete_macro", name);
  if (!result) return;
  if (result.macros) state.macros = result.macros;
  renderMacroMenu();
  if (result.ok) {
    toast(tf("toast_deleted", name), "ok");
    state.currentName = "";
    $("#macroName").value = "";
  } else {
    toast(tf("toast_delete_failed", name), "err");
  }
}

function macroFileName() {
  return state.currentName || (($("#macroName") && $("#macroName").value) || "").trim() || "macro";
}

async function importMacro() {
  var result = await api("import_macro_file");
  if (!result) return;
  if (!result.ok) {
    if (result.reason !== "cancelled") toast(t("toast_import_failed") + ": " + result.reason, "err");
    return;
  }
  var macro = result.macro || {};
  setMacro(macro, macro.name || "");
  setSaveHint("hint_imported");
  toast(t("toast_imported"), "ok");
}

async function exportMacro() {
  var result = await api("export_macro_file", currentMacro(), macroFileName());
  if (!result) return;
  if (result.ok) toast(tf("toast_exported", result.path), "ok");
  else if (result.reason !== "cancelled") toast(t("toast_export_failed") + ": " + result.reason, "err");
}

/* ==========================================================================
   13b. SHAREABLE BUNDLES  (.macrozip -- macro + its images + its recordings)

   Both directions are two steps on purpose. Exporting asks Python what the
   macro actually depends on and shows that list BEFORE a file dialog opens,
   so "it exported fine" can never mean "half the images were missing".
   Importing inspects the zip without writing a single byte, so the dialog
   that offers to overwrite your own files can name them first.
   ========================================================================== */
function bundleGroup(group) {
  var names = el("div", { class: "bundle-names" });
  if (group.names && group.names.length) {
    group.names.forEach(function (name) {
      names.appendChild(el("span", { class: "bundle-name", text: name }));
    });
  } else {
    names.appendChild(el("span", { class: "bundle-empty", text: t("bundle_none") }));
  }
  return el("div", { class: "bundle-group" + (group.warn ? " warn" : "") }, [
    el("div", { class: "bundle-group-head" }, [
      el("span", { text: group.title }),
      el("span", { class: "bundle-count", text: String((group.names || []).length) })
    ]),
    names
  ]);
}

/* Resolves with false (cancelled) or { overwrite: bool }. */
function openBundleDialog(opts) {
  return new Promise(function (resolve) {
    var overlay = $("#bundleModal");
    if (!overlay) { resolve(false); return; }
    var okBtn = $("#btnBundleOk");
    var cancelBtn = $("#btnBundleCancel");
    var closeBtn = $("#btnBundleClose");
    var check = $("#bundleOverwrite");
    var row = $("#bundleOverwriteRow");

    $("#bundleTitle").textContent = opts.title || "";
    $("#bundleSub").textContent = opts.sub || "—";
    $("#bundleHint").textContent = opts.hint || "";
    okBtn.textContent = opts.okLabel || t("btn_continue");
    okBtn.classList.toggle("btn-danger", !!opts.danger);
    okBtn.classList.toggle("btn-primary", !opts.danger);

    var body = $("#bundleBody");
    body.innerHTML = "";
    if (opts.lead) body.appendChild(el("div", { class: "bundle-lead", text: opts.lead }));
    (opts.groups || []).forEach(function (group) { body.appendChild(bundleGroup(group)); });

    check.checked = false;
    row.classList.toggle("hidden", !opts.overwrite);
    overlay.classList.remove("hidden");
    setTimeout(function () { okBtn.focus(); }, 20);

    function done(value) {
      overlay.classList.add("hidden");
      okBtn.removeEventListener("click", ok);
      cancelBtn.removeEventListener("click", cancel);
      closeBtn.removeEventListener("click", cancel);
      document.removeEventListener("keydown", key, true);
      resolve(value);
    }
    function ok() { done({ overwrite: !!(opts.overwrite && check.checked) }); }
    function cancel() { done(false); }
    /* Capture phase, like askConfirm: this is the topmost thing on screen and
       must answer Escape itself rather than letting the global handler hide
       the overlay behind its back, which would strand this promise. */
    function key(e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancel(); }
    }
    okBtn.addEventListener("click", ok);
    cancelBtn.addEventListener("click", cancel);
    closeBtn.addEventListener("click", cancel);
    document.addEventListener("keydown", key, true);
  });
}

async function exportMacroBundle() {
  var macro = currentMacro();
  var name = macroFileName();
  var deps = await api("macro_dependencies", macro);
  if (!deps) return;

  var missing = (deps.missing_images || []).concat(deps.missing_recordings || []);
  var groups = [
    { title: t("bundle_images"), names: deps.images || [] },
    { title: t("bundle_recordings"), names: deps.recordings || [] }
  ];
  if (missing.length) groups.push({ title: t("bundle_missing"), names: missing, warn: true });

  var answer = await openBundleDialog({
    title: t("bundle_export_title"),
    sub: name,
    lead: t("bundle_export_lead"),
    hint: missing.length ? t("bundle_missing_hint") : "",
    okLabel: t("bundle_export_ok"),
    groups: groups
  });
  if (!answer) return;

  var result = await api("export_macro_bundle", macro, name);
  if (!result) return;
  if (!result.ok) {
    if (result.reason !== "cancelled") toast(t("toast_export_failed") + ": " + result.reason, "err");
    return;
  }
  toast(tf("bundle_exported", result.path), "ok");
}

async function importMacroBundle() {
  /* Step one writes nothing: it only reports what is in the file. */
  var info = await api("inspect_macro_bundle");
  if (!info) return;
  if (!info.ok) {
    if (info.reason !== "cancelled") toast(t("bundle_read_failed") + ": " + info.reason, "err");
    return;
  }

  var clashes = (info.clash_images || []).concat(info.clash_recordings || []);
  var groups = [
    { title: t("bundle_images"), names: info.images || [] },
    { title: t("bundle_recordings"), names: info.recordings || [] }
  ];
  if (clashes.length) groups.push({ title: t("bundle_clash"), names: clashes, warn: true });

  var answer = await openBundleDialog({
    title: t("bundle_import_title"),
    sub: info.macro_name || info.path || "",
    lead: t("bundle_import_lead"),
    hint: clashes.length ? t("bundle_clash_hint") : "",
    okLabel: t("bundle_import_ok"),
    overwrite: clashes.length > 0,
    danger: clashes.length > 0,
    groups: groups
  });
  if (!answer) return;

  var result = await api("import_macro_bundle", info.path, !!answer.overwrite);
  if (!result) return;
  if (!result.ok) {
    toast(t("toast_import_failed") + ": " + (result.reason || "unknown"), "err");
    return;
  }

  /* Before anything repaints. An overwriting import replaces the FILE behind
     a name the rows already show, so the cached thumbnail is stale while the
     name is not -- and refreshTemplates below only drops the cache after its
     await, by which time the rows have been rebuilt from it. */
  invalidateThumbs();

  if (result.macro) {
    setMacro(result.macro, result.macro.name || info.macro_name || "");
    setSaveHint("hint_imported");
  }
  if (Array.isArray(result.recordings_list)) {
    state.recordings = result.recordings_list;
    renderRecordings();
  } else {
    refreshRecordings();
  }
  /* The rows already on screen may name an image that only just landed. */
  refreshTemplates();
  renderPhases();

  toast(tf("bundle_imported", (result.images || []).length, (result.recordings || []).length), "ok");
  var skipped = (result.skipped_images || []).concat(result.skipped_recordings || []);
  if (skipped.length) toast(tf("bundle_kept", skipped.join(", ")));
}

/* --------------------------------------------------------------------------
   Toolbar dropdowns. Three of them now (Load / Import / Export), so opening
   one closes the others and a click anywhere else closes all of them.
   -------------------------------------------------------------------------- */
var TOOL_MENUS = ["#macroMenu", "#importMenu", "#exportMenu"];

function closeToolMenus(except) {
  TOOL_MENUS.forEach(function (sel) {
    var menu = $(sel);
    if (menu && menu !== except) menu.classList.add("hidden");
  });
}

function wireMenuButton(btnSel, menuSel, onOpen) {
  var btn = $(btnSel);
  var menu = $(menuSel);
  if (!btn || !menu) return;
  btn.addEventListener("click", function (e) {
    e.stopPropagation();
    var opening = menu.classList.contains("hidden");
    closeToolMenus(menu);
    if (opening && onOpen) onOpen();
    menu.classList.toggle("hidden", !opening);
  });
  menu.addEventListener("click", function (e) { e.stopPropagation(); });
}

function fillToolMenu(menuSel, items) {
  var menu = $(menuSel);
  if (!menu) return;
  menu.innerHTML = "";
  items.forEach(function (item) {
    var btn = el("button", { class: "menu-item" }, [
      icon(item.icon, "ic-xs"),
      el("span", { class: "menu-item-text" }, [
        el("span", { text: item.label }),
        el("span", { class: "menu-item-sub", text: item.sub })
      ])
    ]);
    btn.addEventListener("click", function () {
      menu.classList.add("hidden");
      item.run();
    });
    menu.appendChild(btn);
  });
}

function renderIoMenus() {
  fillToolMenu("#exportMenu", [
    { icon: "i-down", label: t("menu_export_json"), sub: t("menu_export_json_sub"), run: exportMacro },
    { icon: "i-box", label: t("menu_export_bundle"), sub: t("menu_export_bundle_sub"), run: exportMacroBundle }
  ]);
  fillToolMenu("#importMenu", [
    { icon: "i-up", label: t("menu_import_json"), sub: t("menu_import_json_sub"), run: importMacro },
    { icon: "i-box", label: t("menu_import_bundle"), sub: t("menu_import_bundle_sub"), run: importMacroBundle }
  ]);
}

/* ==========================================================================
   14. RECORD SCREEN
   ========================================================================== */
function recOptions() {
  return {
    keepMoves: !!($("#optRecordMove") && $("#optRecordMove").checked),
    /* Math.max(0): a negative number in the box would otherwise be
       passed straight through. 0 = no wait blocks at all. */
    minGap: Math.max(0, toInt($("#optMinGap") ? $("#optMinGap").value : 60, 60))
  };
}

function setRecordingUI(active) {
  state.recording = active;
  var btn = $("#btnRecToggle");
  if (btn) btn.classList.toggle("recording", active);
  var label = $("#recBtnLabel");
  if (label) label.textContent = t(active ? "rec_stop" : "rec_start");
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
    if (!stopped.ok) { toast(t("rec_not_recording"), "err"); return; }
    setRecCount(stopped.count || 0);
    state.previewSource = { kind: "pending" };
    /* Not setPreview(stopped.preview): that list was built with the
       backend defaults, so recorded mouse movement was missing from
       Converted blocks until some later refresh rebuilt it. Go through
       refreshPreview, which uses the options on this screen. */
    await refreshPreview();
    showScreen("record");
  } else {
    var started = await api("start_recording");
    if (!started) return;
    if (!started.ok) { toast(t("rec_cannot") + ": " + started.reason, "err"); return; }
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
    host.appendChild(el("div", { class: "empty", text: t("rec_empty") }));
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
      el("span", { class: "prow-type", text: spec ? spec.label : prettyType(block.type) }),
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
  if (!picked.length) { toast(t("rec_toast_select"), "err"); return; }
  var blocks = normalizeList(JSON.parse(JSON.stringify(picked)), true);
  phaseArray(phase).push.apply(phaseArray(phase), blocks);
  renderPhases();
  markDirty();
  showScreen("builder");
  toast(tf("rec_toast_inserted", blocks.length, phaseTitle({ key: phase, label: phase })), "ok");
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
      toast(t("rec_toast_nothing"), "err");
      return;
    }
    var wanted = await askText(t("rec_ask_name"), "", t("rec_ask_name_hint"));
    if (!wanted) return;
    var saved = await api("save_pending_recording", wanted);
    if (!saved) return;
    if (!saved.ok) {
      toast(t("rec_toast_save_failed") + ": " + (saved.reason || "unknown"), "err");
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
  var name = await askText(t("rec_ask_save"), "", t("rec_ask_save_hint"));
  if (!name) return;
  var result = await api("save_pending_recording", name);
  if (!result) return;
  if (!result.ok) { toast(t("rec_toast_save_failed") + ": " + result.reason, "err"); return; }
  if (result.recordings) state.recordings = result.recordings;
  renderRecordings();
  toast(tf("rec_toast_saved", result.name), "ok");
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
    host.appendChild(el("div", { class: "empty", text: t("rec_none_saved") }));
    return;
  }
  state.recordings.forEach(function (name) {
    // "Edit" opens it as editable blocks; "Use" drops in a single Play
    // Recording block that replays it verbatim, timing included. Two
    // genuinely different ways to reuse a recording, so both are one click.
    var load = el("button", { class: "btn btn-sm", text: t("rec_btn_edit") });
    attachTip(load, t("rec_btn_edit"), t("rec_tip_edit"));
    load.addEventListener("click", async function () {
      var opts = recOptions();
      var blocks = await api("load_recording_blocks", name, opts.keepMoves, opts.minGap);
      if (!Array.isArray(blocks)) return;
      state.previewSource = { kind: "recording", name: name };
      setPreview(blocks);
      toast(tf("rec_toast_loaded", name));
    });

    var use = el("button", { class: "btn btn-sm btn-primary", text: t("rec_btn_use") });
    attachTip(use, t("rec_btn_use"), t("rec_tip_use"));
    use.addEventListener("click", function () {
      addPlaybackBlock(name, "loop");
    });

    var play = el("button", { class: "iconbtn", text: "▶" });
    attachTip(play, t("rec_btn_run"), t("rec_tip_run"));
    play.addEventListener("click", async function () {
      var block = makeBlock("playback");
      block.params.recording = name;
      var result = await api("run_single_block", block);
      if (result && result.ok) toast(tf("rec_toast_playing", name));
      else if (result) toast(t("rec_toast_play_failed") + ": " + (result.reason || "?"), "err");
    });

    var del = el("button", { class: "iconbtn danger", title: t("btn_delete") }, [icon("i-trash", "ic-xs")]);
    del.addEventListener("click", async function () {
      var yes = await askConfirm(tf("rec_ask_delete", name), t("rec_ask_delete_body"));
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
  toast(tf("rec_toast_added", name), "ok");
}

async function discardPending() {
  var result = await api("discard_pending_recording");
  if (!result) return;
  state.previewSource = { kind: "pending" };
  setPreview([]);
  setRecCount(0);
  toast(t("rec_toast_discarded"));
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
    host.appendChild(el("div", { class: "empty", text: t("recedit_empty") }));
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
      ? t("recedit_edited")
      : tf("recedit_derived", data.event_count || 0);
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
  $("#recEditTitle").textContent = tf("recedit_title_of", name);
  $("#recEditSub").textContent = t("loading");
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
      ? t("recedit_gone")
      : t("recedit_load_failed");
    toast(data && data.reason === "missing"
      ? tf("recedit_toast_gone", name)
      : tf("recedit_toast_failed", name), "err");
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
    var sure = await askConfirm(tf("recedit_ask_empty", recEdit.name), t("recedit_ask_empty_body"));
    if (!sure || !recEdit.open) return;
  }
  var result = await api("save_recording_actions", recEdit.name, payload);
  if (!result) return;
  if (!result.ok) {
    toast(t("recedit_save_failed") + ": " + (result.reason || "unknown"), "err");
    return;
  }
  toast(tf("recedit_toast_saved", payload.length, result.name || recEdit.name), "ok");
  closeRecordingEditor();
}

async function resetRecordingActions() {
  if (!recEdit.name || !recEdit.loaded) return;
  var name = recEdit.name;
  var token = recEdit.token;
  var yes = await askConfirm(tf("recedit_ask_reset", name), t("recedit_ask_reset_body"));
  /* The editor can be closed (Escape) while the confirmation is up. Acting
     afterwards would reset a recording whose editor is no longer on screen. */
  if (!yes || !recEdit.open || recEdit.token !== token) return;
  var data = await api("reset_recording_actions", name);
  if (!data || !data.ok || !recEdit.open || recEdit.token !== token) {
    if (data && !data.ok) toast(t("recedit_reset_failed") + ": " + (data.reason || "unknown"), "err");
    return;
  }
  applyRecEditData(name, data);
  toast(t("recedit_reset_done"), "ok");
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
var blocksEdit = { stack: [], open: false, onLabel: null, custom: false };

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
    sub.textContent = (blocksEdit.stack.length > 1
        ? tf("blocks_edit_levels", blocksEdit.stack.length) + " · " : "")
      + count + " " + t(count === 1 ? "block_1" : "block_n");
  }
}

function renderBlocksEditList() {
  var host = $("#blocksEditList");
  if (!host) return;
  var list = blocksEditCtx.list();
  host.innerHTML = "";
  if (!list.length) {
    host.appendChild(el("div", { class: "dropzone", text: t("dropzone") }));
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
    title: (f.label || t("blocks_edit_title")) + " — " + (spec ? spec.label : prettyType(block.type))
  });
  if (blocksEdit.stack.length === 1) {
    blocksEdit.onLabel = onLabel || null;
    blocksEdit.open = true;
    overlay.classList.remove("hidden");
    buildBlocksEditPalette();
  }
  renderBlocksEditList();
}

function buildBlocksEditPalette() {
  buildPalette($("#blocksEditPalette"), {
    scope: "blocksedit",
    allowCustom: false,
    hint: t("palette_drag_list"),
    onPick: function (chosen) {
      blocksEditCtx.list().push(makeBlock(chosen.type));
      renderBlocksEditList();
      blocksEditCtx.changed();
    }
  });
}

/* Closes one level; the modal itself only goes away with the last one. */
function closeBlocksEditor() {
  if (!blocksEdit.open) return;
  if (blocksEdit.custom) {
    blocksEdit.stack = [];
    blocksEdit.open = false;
    blocksEdit.custom = false;
    $("#blocksEditModal").classList.add("hidden");
    $("#blocksEditCustomName").classList.add("hidden");
    return;
  }
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

async function finishBlocksEditor() {
  if (!blocksEdit.custom) { closeBlocksEditor(); return; }
  var nameNode = $("#blocksEditCustomName");
  var name = nameNode ? nameNode.value.trim() : "";
  var list = blocksEditCtx.list();
  if (!name) { toast(condIsRussian() ? "Введите имя блока" : "Enter a block name", "err"); return; }
  if (!list.length) { toast(condIsRussian() ? "Добавьте хотя бы один блок" : "Add at least one block", "err"); return; }
  var result = await api("save_block_group", name, JSON.parse(JSON.stringify(list)));
  if (!result || !result.ok) { toast(t("grp_save_failed"), "err"); return; }
  state.groups = result.groups || [];
  state.activePalette = "__custom__";
  closeBlocksEditor();
  renderPalette();
  toast(condIsRussian() ? "Пользовательский блок сохранён" : "Custom block saved", "ok");
}

function openCustomBlockEditor() {
  var overlay = $("#blocksEditModal");
  if (!overlay) return;
  blocksEdit.stack = [{ list: [], title: condIsRussian() ? "Новый пользовательский блок" : "New custom block" }];
  blocksEdit.open = true;
  blocksEdit.custom = true;
  var nameNode = $("#blocksEditCustomName");
  if (nameNode) { nameNode.value = ""; nameNode.classList.remove("hidden"); }
  overlay.classList.remove("hidden");
  buildBlocksEditPalette();
  renderBlocksEditList();
}

async function clearBlocksEditor() {
  var list = blocksEditCtx.list();
  if (!list.length) return;
  var yes = await askConfirm(tf("blocks_ask_clear", list.length), t("blocks_ask_clear_body"));
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
  body.appendChild(el("div", { class: "empty", text: t("rendering") }));
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
    detail.textContent = t("hook_preview_failed");
    body.appendChild(el("div", { class: "empty", text: webhookReason(result && result.reason) }));
    return;
  }
  detail.textContent = result.detail || "";
  if (result.image) {
    body.appendChild(el("img", { src: result.image, alt: "attachment preview" }));
  } else {
    body.appendChild(el("div", { class: "empty", text: t("hook_preview_text_only") }));
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
  /* Whether the zoom is still the one we picked. Once the user zooms by hand
     we stop re-fitting on resize -- throwing away a 4x inspection because the
     window was nudged is worse than leaving a stale fit. */
  var autoFit = true;

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
    if (!canvas.offsetParent) return;
    // The picker fills the window, so making the window bigger has to make
    // the picture bigger. Without this the zoom stayed at whatever fitted the
    // old size: enlarge and the image sat in a corner, shrink and it spilled
    // into scrollbars.
    if (autoFit) {
      var next = fitScale();
      if (Math.abs(next - scale) > 1e-9) { scale = next; applyScale(); }
    }
    if (rect) draw();
  });

  return {
    setNatural: function (w, h) {
      natural = { w: w || 1, h: h || 1 };
      scale = fitScale();
      autoFit = true;
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
    zoomIn: function () { autoFit = false; setScale(scale * ZOOM_STEP); },
    zoomOut: function () { autoFit = false; setScale(scale / ZOOM_STEP); },
    zoomAt: function (next, clientX, clientY) {
      autoFit = false;
      setScale(next, clientX, clientY);
    },
    fit: function () { autoFit = true; setScale(fitScale()); },
    getScale: function () { return scale; },
    isAutoFit: function () { return autoFit; }
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

/* --------------------------------------------------------------------------
   Which window a screenshot is OF is a separate question from which window a
   macro DRIVES, and this screen is where the two came apart: images and maps
   are often framed in a window that is not the target at all (a wiki page, a
   second client, the whole desktop). So every capture from here is aimed
   explicitly, and picking one never touches the macro target.

   The choice is remembered for the session so Re-capture and Re-shoot do not
   ask again -- re-shooting is by definition another shot of the same thing.
   -------------------------------------------------------------------------- */
var capShot = { hwnd: null, title: "" };

function capShotLabel() {
  if (capShot.hwnd === null) return t("winpick_target");
  return capShot.title || (capShot.hwnd ? String(capShot.hwnd) : t("target_screen"));
}

async function captureForImages(hwnd, title) {
  var canvas = $("#imgCanvas");
  /* undefined means "the window already chosen" (Re-capture); null is the
     macro target, which is what the pickers outside this screen still use. */
  if (hwnd !== undefined) {
    capShot.hwnd = hwnd === null ? null : Number(hwnd || 0);
    capShot.title = title || "";
  }
  $("#imgCanvasEmpty").classList.remove("hidden");
  $("#imgCanvasEmpty").textContent = t("img_capturing");
  var result = await api("capture_target_preview", capShot.hwnd);
  if (!result || !result.ok) {
    $("#imgCanvasEmpty").textContent = t("img_capture_failed")
      + (result && result.reason ? " (" + result.reason + ")" : "");
    return false;
  }
  var ok = await drawCapture(canvas, result.image, result.width, result.height);
  if (!ok) { $("#imgCanvasEmpty").textContent = t("img_decode_failed"); return false; }
  $("#imgCanvasEmpty").classList.add("hidden");
  imgSel.setNatural(result.width, result.height);
  imgSel.clear();
  $("#captureHint").textContent = tf("img_shot_from", capShotLabel()) + " · "
    + tf("img_capture_size", result.width + " × " + result.height);
  return true;
}

/* Ask, then shoot. A dismissed picker shoots nothing at all: a screenshot of
   whatever happened to be the target is worse than no screenshot. */
async function askAndCapture() {
  var choice = await openWinPicker();
  if (!choice) { toast(t("img_shot_cancelled")); return false; }
  return await captureForImages(choice.hwnd, choice.title);
}

/* The Capture button's whole job: take the shot, then hand it straight to the
   large view. Cropping in the inline strip is a few hundred pixels of image
   and a mouse that has to be steady to a source pixel; the panel stays as the
   preview of what is loaded, but it is no longer where the work is done. */
async function captureAndCrop() {
  var ok = await askAndCapture();
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
  var ok = await askAndCapture();
  /* The mode must never outlive the view it belongs to: left set, the next
     ordinary save would quietly write to this template instead. */
  if (!ok || !openImgLargeView()) bigView.reshoot = "";
}

async function recaptureInBigView() {
  if (!bigView.open) return;
  /* Same window as the shot on screen -- no argument, no second question. */
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
    tag.textContent = reshoot ? tf("big_reshooting", reshoot) : "";
  }
  if (save) save.textContent = t(reshoot ? "big_replace_main" : "img_save_new");
  if (variant) variant.textContent = t(reshoot ? "big_add_variant" : "img_save_variant");
  if (nameInput) {
    nameInput.value = ($("#imgName") && $("#imgName").value) || "";
    nameInput.readOnly = !!reshoot;
    nameInput.classList.toggle("locked", !!reshoot);
  }
  if (hint) hint.textContent = t(reshoot ? "big_hint_reshoot" : "big_hint");
}

function openImgLargeView() {
  var overlay = $("#bigViewModal");
  var col = $("#imgCanvasCol");
  var slot = $("#bigViewSlot");
  if (!overlay || !col || !slot || bigView.open) return false;
  if (!$("#imgCanvasEmpty").classList.contains("hidden")) {
    toast(t("img_capture_first"), "err");
    return false;
  }
  bigView.open = true;
  slot.appendChild(col);
  overlay.classList.remove("hidden");
  applyBigViewMode();
  /* The whole point of this view is that a 2560x1440 capture arrives readable
     rather than shrunk into a corner, so it is fitted to the (now much
     larger) holder the moment it is laid out.

     Twice: once against a forced synchronous layout, and once on the next
     turn. The first is what makes the very first paint correct; the second
     catches the wrapping the head and foot settle into afterwards, which can
     still move the holder's bottom edge by a row of buttons. A timer rather
     than requestAnimationFrame, for the same reason applyTheme uses one: rAF
     never runs while the window is hidden or unpainted, and the capture would
     then sit at the small panel's zoom the next time it shows. */
  void overlay.offsetHeight;
  imgSel.fit();
  setTimeout(function () { if (bigView.open) imgSel.fit(); }, 0);
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
    toast(t("img_need_name"), "err");
    var field = bigView.open ? $("#bigViewName") : $("#imgName");
    if (field) field.focus();
    return null;
  }
  var rect = imgSel.get();
  if (!rect || rect[2] < 2 || rect[3] < 2) { toast(t("img_need_rect"), "err"); return null; }

  var reshot = !!bigView.reshoot;
  var result = await api("save_template_crop", name, rect[0], rect[1], rect[2], rect[3], !!asVariant);
  if (!result) return null;
  if (!result.ok) { toast(t("img_save_failed") + ": " + result.reason, "err"); return null; }

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
  /* A re-shoot changes the picture BEHIND a name every builder row already
     shows, so those rows are now displaying the very look that was replaced. */
  if (reshot) renderPhases();
  toast(tf(reshot
    ? (asVariant ? "img_variant_added" : "img_replaced")
    : (asVariant ? "img_variant_saved" : "img_saved"), name), "ok");

  /* Cleared BEFORE the close, which would otherwise resolve it as cancelled. */
  var pending = bigView.pick;
  bigView.pick = null;
  if (bigView.open) closeImgLargeView();
  if (pending) pending(name);
  return name;
}

/* --------------------------------------------------------------------------
   Maps are the other thing a shot can become: the same frame, written to the
   Maps folder instead of Assets, where Place Unit picks spots on it.

   No crop is required -- a map is normally the whole window -- so a selection
   is used when there is one and ignored when there is not, rather than making
   the user drag a rectangle around the entire frame every time.
   -------------------------------------------------------------------------- */
async function saveMapCrop() {
  var name = ((bigView.open ? $("#bigViewName") : $("#imgName")).value || "").trim()
    || (($("#imgName") && $("#imgName").value) || "").trim();
  if (!name) {
    toast(t("img_need_name"), "err");
    var field = bigView.open ? $("#bigViewName") : $("#imgName");
    if (field) field.focus();
    return null;
  }
  var rect = imgSel.get();
  var whole = !rect || rect[2] < 2 || rect[3] < 2;
  var result = await api("save_map_crop", name,
                        whole ? 0 : rect[0], whole ? 0 : rect[1],
                        whole ? 0 : rect[2], whole ? 0 : rect[3], whole);
  if (!result) return null;
  if (!result.ok) { toast(t("img_save_failed") + ": " + result.reason, "err"); return null; }

  if (Array.isArray(result.maps)) state.maps = result.maps;
  /* Re-shooting a map writes new bytes behind a name every cached thumbnail
     and every open picker still shows the old picture for. */
  invalidateMapThumbs();
  renderTemplates();
  toast(tf("img_map_saved", result.name), "ok");
  if (bigView.open) closeImgLargeView();
  return result.name;
}

/* Re-shooting a map is an ordinary capture with the name filled in: the save
   goes over the existing picture, so the blocks pointing at it follow. */
async function reshootMap(name) {
  if (bigView.open) closeImgLargeView();
  var nameInput = $("#imgName");
  if (nameInput) nameInput.value = name;
  var ok = await askAndCapture();
  if (ok) openImgLargeView();
}

async function importMapFile() {
  var result = await api("import_map", "");
  if (!result) return;
  if (!result.ok) {
    if (result.reason !== "cancelled") toast(t("img_map_import_failed"), "err");
    return;
  }
  if (Array.isArray(result.maps)) state.maps = result.maps;
  invalidateMapThumbs();
  renderTemplates();
  toast(tf("img_map_imported", result.name), "ok");
}

var mapThumbCache = {};

function invalidateMapThumbs() { mapThumbCache = {}; }

function mapThumb(name) {
  var key = String(name);
  if (!mapThumbCache[key]) mapThumbCache[key] = apiQ("get_map_thumb", key, 320);
  return mapThumbCache[key];
}

async function refreshMaps() {
  var list = await apiQ("list_maps");
  if (Array.isArray(list)) state.maps = list;
  invalidateMapThumbs();
  renderTemplates();
}

/* The grid holds two kinds of picture in one place, and a thumbnail alone
   never says which folder it came from -- so each card is tagged. */
function kindBadge(kind) {
  return el("span", {
    class: "tpl-badge is-" + kind,
    text: t(kind === "map" ? "img_kind_map" : "img_kind_ui")
  });
}

function mapCard(name) {
  var thumb = el("div", { class: "tpl-thumb" }, [el("span", { class: "hint", text: "…" })]);
  var size = el("span", { text: "…" });
  mapThumb(name).then(function (info) {
    thumb.innerHTML = "";
    if (info && info.ok) {
      thumb.appendChild(el("img", { src: info.image, alt: name }));
      size.textContent = tf("img_map_size", info.width, info.height);
    } else {
      thumb.appendChild(el("span", { class: "hint", text: t("img_no_preview") }));
      size.textContent = t("missing_suffix");
    }
  });

  var shootBtn = el("button", { class: "btn btn-sm" },
    [icon("i-camera", "ic-xs"), el("span", { text: t("img_map_reshoot") })]);
  attachTip(shootBtn, t("img_map_reshoot"), tf("img_map_reshoot_tip", name));
  shootBtn.addEventListener("click", function () { reshootMap(name); });

  /* The picker is also the only view of a map that shows the spots on it, so
     it doubles as "what does this map already have on it?". */
  var viewBtn = el("button", { class: "btn btn-sm", text: t("mappick_title") });
  attachTip(viewBtn, t("mappick_title"), tf("img_map_pick_tip", name));
  viewBtn.addEventListener("click", function () { openMapPicker([name, 0, 0, 0, 0], ""); });

  var delBtn = el("button", { class: "iconbtn danger", title: t("img_map_delete_tip") }, [icon("i-trash", "ic-xs")]);
  delBtn.addEventListener("click", async function () {
    var yes = await askConfirm(tf("img_ask_delete_map", name), t("img_ask_delete_map_body"));
    if (!yes) return;
    var res = await api("delete_map", name);
    if (!res) return;
    if (Array.isArray(res.maps)) state.maps = res.maps;
    invalidateMapThumbs();
    renderTemplates();
  });

  return el("div", { class: "tpl-card is-map" }, [
    thumb,
    el("div", { class: "tpl-name", text: name, title: name }),
    el("div", { class: "tpl-meta" }, [kindBadge("map"), size]),
    el("div", { class: "tpl-actions" }, [shootBtn, viewBtn, el("span", { class: "flex-spacer" }), delBtn])
  ]);
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
  var maps = state.maps || [];
  if (!state.templates.length && !maps.length) {
    host.appendChild(el("div", { class: "empty", text: t("img_none") }));
    return;
  }
  state.templates.forEach(function (tpl) {
    var thumb = el("div", { class: "tpl-thumb" }, [el("span", { class: "hint", text: "…" })]);
    templateThumb(tpl.name, (tpl.files && tpl.files[0]) || "").then(function (uri) {
      thumb.innerHTML = "";
      if (uri) thumb.appendChild(el("img", { src: uri, alt: tpl.name }));
      else thumb.appendChild(el("span", { class: "hint", text: t("img_no_preview") }));
    });

    var result = el("span", { class: "tpl-result" });
    var testBtn = el("button", { class: "btn btn-sm", text: t("img_test") });
    attachTip(testBtn, t("img_test"), t("img_test_tip"));
    testBtn.addEventListener("click", async function () {
      result.textContent = "…";
      result.className = "tpl-result";
      var threshold = toNum(state.settings.default_threshold, 0.88);
      var found = await api("test_template", tpl.name, threshold);
      if (!found) { result.textContent = t("img_error"); result.className = "tpl-result bad"; return; }
      if (found.ok) {
        result.textContent = tf("img_found", found.cx + "," + found.cy, Number(found.score).toFixed(3));
        result.className = "tpl-result ok";
      } else {
        result.textContent = t("img_not_found");
        result.className = "tpl-result bad";
      }
    });

    /* The one repair for "the button I saved looks different now": shoot the
       target again and drop the new crop onto this same name. */
    var shootBtn = el("button", { class: "btn btn-sm" }, [icon("i-camera", "ic-xs"), el("span", { text: t("img_reshoot") })]);
    attachTip(shootBtn, t("img_reshoot"), tf("img_reshoot_tip", tpl.name));
    shootBtn.addEventListener("click", function () { reshootTemplate(tpl.name); });

    var delBtn = el("button", { class: "iconbtn danger", title: t("img_delete_tip") }, [icon("i-trash", "ic-xs")]);
    delBtn.addEventListener("click", async function () {
      var yes = await askConfirm(tf("img_ask_delete", tpl.name), tf("img_ask_delete_body", tpl.count));
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
        kindBadge("ui"),
        el("span", { text: tn("img_variant_1", "img_variant_n", tpl.count) }),
        el("span", { class: "flex-spacer" }), result
      ]),
      el("div", { class: "tpl-actions" }, [testBtn, shootBtn, el("span", { class: "flex-spacer" }), delBtn])
    ]));
  });

  maps.forEach(function (name) { host.appendChild(mapCard(name)); });
}

/* ==========================================================================
   15a2. "WHICH WINDOW DO I SHOOT?"

   Resolves with { hwnd, title } or undefined when dismissed. hwnd 0 is the
   whole screen (the app hides itself for that one), and nothing here writes
   the macro target -- set_target is deliberately not called.
   ========================================================================== */
var winPick = { resolve: null, filter: "", bound: false };

function winPickRow(title, subtitle, sizeText, extraClass, onPick) {
  var row = el("div", { class: "win-item" + (extraClass ? " " + extraClass : ""), title: title }, [
    el("span", { class: "win-proc", text: subtitle }),
    el("span", { class: "win-title", text: title }),
    el("span", { class: "win-size", text: sizeText })
  ]);
  row.addEventListener("click", onPick);
  return row;
}

function renderWinPickList() {
  var host = $("#winPickList");
  if (!host) return;
  var query = (winPick.filter || "").toLowerCase();
  host.innerHTML = "";

  /* Always offered, never filtered out: it is the fallback when the thing to
     photograph is not a window at all (an overlay, several windows at once). */
  host.appendChild(winPickRow(t("winpick_screen"), "—", "", "win-screen",
    function () { closeWinPicker({ hwnd: 0, title: t("target_screen") }); }));

  var rows = (state.windows || []).filter(function (w) {
    if (!query) return true;
    return (String(w.title) + " " + String(w.process)).toLowerCase().indexOf(query) >= 0;
  });
  if (!rows.length) {
    host.appendChild(el("div", {
      class: "empty",
      text: query ? t("set_no_window_match") : t("set_no_windows")
    }));
    return;
  }
  rows.forEach(function (w) {
    var sizeText = w.minimized ? t("set_minimized") : (w.width + "x" + w.height);
    var current = state.status.hwnd && Number(state.status.hwnd) === Number(w.hwnd);
    host.appendChild(winPickRow(
      w.title, (w.process || "?") + (current ? " · " + t("winpick_target") : ""),
      sizeText, (current ? "selected" : "") + (w.minimized ? " win-min" : ""),
      function () { closeWinPicker({ hwnd: w.hwnd, title: w.title }); }));
  });
}

function closeWinPicker(value) {
  var overlay = $("#winPickModal");
  if (overlay) overlay.classList.add("hidden");
  var pending = winPick.resolve;
  winPick.resolve = null;
  if (pending) pending(value);
}

function bindWinPicker() {
  if (winPick.bound) return;
  winPick.bound = true;
  $("#winPickFilter").addEventListener("input", function () {
    winPick.filter = $("#winPickFilter").value.trim();
    renderWinPickList();
  });
  $("#btnWinPickRefresh").addEventListener("click", async function () {
    await refreshWindows();
    renderWinPickList();
  });
  $("#btnWinPickCancel").addEventListener("click", function () { closeWinPicker(undefined); });
  $("#btnWinPickClose").addEventListener("click", function () { closeWinPicker(undefined); });
}

async function openWinPicker() {
  var overlay = $("#winPickModal");
  if (!overlay) return { hwnd: null, title: "" };
  bindWinPicker();
  /* Asked for fresh every time: the window the user means was very often
     opened after the app was, and a stale list has no row for it. */
  await refreshWindows();
  winPick.filter = "";
  $("#winPickFilter").value = "";
  renderWinPickList();
  overlay.classList.remove("hidden");
  $("#winPickFilter").focus();
  return await new Promise(function (resolve) {
    if (winPick.resolve) winPick.resolve(undefined);
    winPick.resolve = resolve;
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
      text: state.templates.length ? tf("tplpick_no_match", tplPick.filter) : t("tplpick_empty")
    }));
    return;
  }

  rows.forEach(function (tpl) {
    var thumb = el("div", { class: "tpl-thumb" }, [el("span", { class: "hint", text: "…" })]);
    templateThumb(tpl.name, (tpl.files && tpl.files[0]) || "").then(function (uri) {
      thumb.innerHTML = "";
      if (uri) thumb.appendChild(el("img", { src: uri, alt: tpl.name }));
      else thumb.appendChild(el("span", { class: "hint", text: t("img_no_preview") }));
    });

    var card = el("button", {
      class: "tplpick-card" + (tpl.name === tplPick.current ? " on" : ""),
      type: "button", title: tpl.name
    }, [
      thumb,
      el("div", { class: "tpl-name", text: tpl.name }),
      el("div", { class: "tpl-meta" }, [
        el("span", { text: tn("img_variant_1", "img_variant_n", tpl.count) })
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
    if (readout) readout.textContent = tplPick.current || t("none_dash");

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

  var ok = await askAndCapture();
  if (!ok) { resolve(undefined); return; }
  bigView.pick = resolve;
  if (!openImgLargeView()) { bigView.pick = null; resolve(undefined); }
}

/* ==========================================================================
   16. PICKING -- point, colour, region
   ========================================================================== */
function showPickOverlay(title) {
  var overlay = $("#pickOverlay");
  $("#pickTitle").textContent = title || t("pick_point");
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
  if (state.picking) { toast(t("pick_busy"), "err"); return null; }
  state.picking = true;
  showPickOverlay(t("pick_point"));
  var result = await api("pick_point");
  hidePickOverlay();
  state.picking = false;
  if (!result) return null;
  if (!result.ok) {
    toast(result.reason === "timeout" ? t("pick_timeout") : t("pick_failed") + ": " + result.reason, "err");
    return null;
  }
  return result;
}

async function pickColor() {
  if (state.picking) { toast(t("pick_busy"), "err"); return null; }
  state.picking = true;
  showPickOverlay(t("pick_color"));
  var result = await api("pick_color");
  hidePickOverlay();
  state.picking = false;
  if (!result) return null;
  if (!result.ok) {
    toast(result.reason === "timeout" ? t("pick_timeout") : t("pick_failed") + ": " + result.reason, "err");
    return null;
  }
  return result;
}

/* The last rectangle the region picker reported, kept so the readout can be
   repainted in another language. It only ever changes on a selection change,
   so without this a language switch left one English line in an otherwise
   Russian modal -- and clearing the selection put it straight back. */
var regionReadoutRect = null;

function paintRegionReadout(rect) {
  if (rect !== undefined) regionReadoutRect = rect;
  var node = $("#regionReadout");
  if (!node) return;
  var r = regionReadoutRect;
  node.textContent = r
    ? "x " + r[0] + " · y " + r[1] + " · " + r[2] + " × " + r[3]
    : t("region_readout_none");
}

/* Resolves with [x,y,w,h], null (cleared) or undefined (cancelled). */
function openRegionPicker(current) {
  return new Promise(async function (resolve) {
    var overlay = $("#regionModal");
    var canvas = $("#regionCanvas");
    var empty = $("#regionCanvasEmpty");

    empty.classList.remove("hidden");
    empty.textContent = t("region_capturing");
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
      empty.textContent = t("img_capture_failed")
        + (result && result.reason ? " (" + result.reason + ")" : "");
      return;
    }
    var ok = await drawCapture(canvas, result.image, result.width, result.height);
    if (!ok) { empty.textContent = t("img_decode_failed"); return; }
    empty.classList.add("hidden");
    /* Same reason as the crop view: the modal is already laid out here, but a
       forced read makes sure the fit is measured against THIS window rather
       than whatever the holder was the last time it was open. */
    void $("#regionCanvasHolder").offsetHeight;
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
    host.appendChild(el("div", {
      class: "empty",
      text: query ? t("set_no_window_match") : t("set_no_windows")
    }));
    return;
  }
  rows.forEach(function (w) {
    // A minimized window reports no client area at all; showing "0x0" reads
    // as broken. Attaching to it restores it, so say what it actually is.
    var sizeText = w.minimized ? t("set_minimized") : (w.width + "x" + w.height);
    var item = el("div", {
      class: "win-item" + (currentHwnd && Number(currentHwnd) === Number(w.hwnd) ? " selected" : "")
        + (w.minimized ? " win-min" : ""),
      title: w.minimized ? tf("set_win_min_tip", w.title) : w.title
    }, [
      el("span", { class: "win-proc", text: w.process || "?" }),
      el("span", { class: "win-title", text: w.title }),
      el("span", { class: "win-size", text: sizeText })
    ]);
    item.addEventListener("click", async function () {
      var result = await api("set_target", w.hwnd, w.title);
      if (!result) return;
      if (!result.ok) { toast(t("set_window_gone_toast"), "err"); refreshWindows(); return; }
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
  if (title) title.textContent = info.title || t(info.mode === "screen" ? "target_screen" : "target_none");

  var ind = $("#attachInd");
  if (ind) {
    ind.innerHTML = "";
    ind.appendChild(el("span", { class: "dot " + (alive ? "dot-on" : "dot-off") }));
    ind.appendChild(el("span", {
      text: !alive ? t("set_window_gone")
        : info.minimized ? t("set_attached_min")
        : tf("set_attached", (info.width || 0) + "x" + (info.height || 0))
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
    var label = t(hk.label);
    var btn = el("button", { class: "keybtn" + (value ? "" : " empty"), text: value || t("set_unbound") });
    btn.addEventListener("click", function () {
      beginKeyCapture(btn, async function (name) {
        btn.textContent = name;
        btn.classList.remove("empty");
        var merged = await api("set_setting", hk.key, name);
        if (merged) { state.settings = merged; toast(label + " → " + name, "ok"); }
      });
    });
    host.appendChild(el("div", { class: "hotkey-cell" }, [
      el("span", { class: "flab", text: label }), btn
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
      toast(tf("toast_theme", theme.label), "ok");
    });
    host.appendChild(card);
  });
}

/* ==========================================================================
   17b2. INTERFACE LANGUAGE PICKER

   Two halves have to move together. The strings in this file switch the
   moment `state.settings.language` changes; the block descriptions and the
   per-field help do NOT live here at all -- they come from Python inside the
   catalog. So the switch persists the setting, asks for the catalog again,
   rebuilds state.catalog/state.byType from the answer, and only then repaints
   everything that reads either source.
   ========================================================================== */
function renderLanguages() {
  var host = $("#langGrid");
  if (!host) return;
  var current = currentLang();
  host.innerHTML = "";

  LANGUAGES.forEach(function (lang) {
    var card = el("button", {
      class: "theme-card lang-card" + (lang.key === current ? " on" : ""), type: "button"
    }, [
      el("div", { class: "theme-swatch" }, [el("span", { class: "lang-code", text: lang.code })]),
      el("div", { class: "theme-name" }, [
        el("span", { text: lang.label }),
        el("span", { class: "theme-tick", text: lang.key === current ? "✓" : "" })
      ])
    ]);
    card.addEventListener("click", function () { setLanguage(lang.key); });
    host.appendChild(card);
  });
}

/* Everything that carries a translated string, in one place, so a switch can
   never leave half the window in the previous language. */
function relocalize() {
  applyI18n(document);
  renderPalette();
  renderPhases();
  renderIoMenus();
  renderMacroMenu();
  renderRecordings();
  renderPreview();
  renderTemplates();
  renderWindows();
  renderHotkeys();
  renderThemes();
  renderLanguages();
  renderWebhook();
  applyBigViewMode();
  setRecordingUI(state.recording);
  setMaximizedUI(winMaximized);
  /* Written once and then left alone, so each needs asking again in the new
     language rather than waiting for whatever event first wrote it. */
  renderEnvRow(state.boot || {});
  repaintSaveHint();
  paintRegionReadout();
  if (mapGal.open) renderMapGallery();
  if (mapPick.resolve) syncMapPickChoose();
  if (recEdit.open) renderRecEditList();
  if (blocksEdit.open) { buildBlocksEditPalette(); renderBlocksEditList(); }
  /* The control bar and the target chip are written from the poll, not from
     the markup, so they are refreshed rather than re-translated. */
  refreshTargetInfo();
  pollStatus();
}

/* The catalog carries desc/help in whatever language Python was last told to
   use, so it is re-fetched rather than translated here. */
async function refreshCatalog() {
  var boot = await apiQ("get_bootstrap");
  if (!boot || !Array.isArray(boot.catalog) || !boot.catalog.length) return null;
  state.catalog = boot.catalog;
  state.byType = {};
  state.catalog.forEach(function (spec) { state.byType[spec.type] = spec; });
  if (Array.isArray(boot.phases) && boot.phases.length) state.phases = boot.phases;
  state.boot = boot;
  return boot;
}

var langBusy = false;

async function setLanguage(lang) {
  if (langBusy || !STRINGS[lang] || lang === currentLang()) return;
  langBusy = true;
  try {
    /* Flipped locally first so the picker itself answers instantly, then
       persisted; if the write fails the next boot simply comes back in the
       old language rather than in a language nothing was rendered for. */
    state.settings.language = lang;
    renderLanguages();
    var merged = await api("set_setting", "language", lang);
    if (merged) {
      state.settings = merged;
      state.settings.language = lang;
    }

    var boot = await refreshCatalog();
    if (boot && boot.settings) {
      state.settings = boot.settings;
      state.settings.language = lang;
    }

    relocalize();
    toast(tf("toast_language", langLabel(lang)), "ok");
  } finally {
    langBusy = false;
  }
}

/* ==========================================================================
   17c. DISCORD WEBHOOK SETTINGS
   The real URL never crosses the bridge in this direction -- get_webhook_
   settings only ever hands back a masked form, and this screen only ever
   shows that.
   ========================================================================== */
var hookState = { enabled: false, configured: false, masked: "", username: "", design: {} };

function renderWebhook() {
  var card = $("#webhookCard");
  if (!card) return;
  var enabled = !!hookState.enabled;
  var configured = !!hookState.configured;

  card.classList.toggle("off", !enabled);
  $("#hookEnabled").checked = enabled;
  $("#hookMasked").textContent = hookState.masked || t("hook_no_url");
  var user = $("#hookUser");
  if (user && document.activeElement !== user) user.value = hookState.username || "";
  var design = hookState.design || {};
  var title = $("#hookTitle");
  var description = $("#hookDescription");
  var color = $("#hookColor");
  var footer = $("#hookFooter");
  var timestamp = $("#hookTimestamp");
  if (title && document.activeElement !== title) title.value = design.title || "";
  if (description && document.activeElement !== description) description.value = design.description || "";
  if (color && document.activeElement !== color) color.value = /^#[0-9a-f]{6}$/i.test(design.color || "") ? design.color : "#8b5cf6";
  if (footer && document.activeElement !== footer) footer.value = design.footer || "";
  if (timestamp) timestamp.checked = design.timestamp !== false;

  var state_ = $("#hookState");
  var text = $("#hookStateText");
  state_.className = "hook-state" + (enabled && configured ? " armed" : (enabled ? " warn" : ""));
  text.textContent = !enabled
    ? t("hook_state_off")
    : configured ? t("hook_state_on") : t("hook_state_no_url");

  var ind = $("#hookInd");
  ind.innerHTML = "";
  ind.appendChild(el("span", { class: "dot " + (configured ? (enabled ? "dot-on" : "dot-idle") : "dot-off") }));
  ind.appendChild(el("span", {
    text: !configured ? t("hook_not_configured") : t(enabled ? "hook_armed" : "hook_configured_off")
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
    username: result.username || "",
    design: result.design || {}
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
  if (!url) { toast(t("wh_empty"), "err"); input.focus(); return; }

  var result = await api("save_webhook_settings", url, null, username);
  if (!result) return;
  if (result.ok === false) {
    $("#hookHint").textContent = webhookReason(result.reason);
    toast(webhookReason(result.reason), "err");
    return;
  }
  input.value = "";
  $("#hookHint").textContent = t("hook_saved_hint");
  applyWebhookResult(result);
  toast(t("hook_url_saved"), "ok");
}

async function saveWebhookDesign() {
  var result = await api("save_webhook_settings", null, null, null, {
    title: $("#hookTitle").value,
    description: $("#hookDescription").value,
    color: $("#hookColor").value,
    footer: $("#hookFooter").value,
    timestamp: $("#hookTimestamp").checked
  });
  if (result) applyWebhookResult(result);
}

async function toggleWebhookEnabled() {
  var on = $("#hookEnabled").checked;
  /* null for url and username: they are not being changed, and the URL is a
     secret the frontend does not hold in the first place. */
  var result = await api("save_webhook_settings", null, on, null);
  if (!result || result.ok === false) { await refreshWebhook(); return; }
  applyWebhookResult(result);
  toast(t(on ? "hook_enabled_toast" : "hook_disabled_toast"), on ? "ok" : "");
}

async function clearWebhookUrl() {
  var yes = await askConfirm(t("hook_ask_clear"), t("hook_ask_clear_body"));
  if (!yes) return;
  var result = await api("clear_webhook_url");
  if (!result) return;
  applyWebhookResult(result);
  $("#hookHint").textContent = t("hook_removed_hint");
  toast(t("hook_url_removed"), "ok");
}

async function testWebhook() {
  var btn = $("#btnHookTest");
  btn.disabled = true;
  btn.textContent = t("hook_sending");
  var result = await api("test_webhook");
  btn.textContent = t("hook_test");
  renderWebhook();
  if (!result) return;
  if (result.ok) toast(t("hook_test_ok"), "ok");
  else toast(t("hook_test_failed") + ": " + webhookReason(result.reason), "err");
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
  if ($("#optMinGap")) $("#optMinGap").value = toInt(s.record_min_gap_ms, 60);
  if ($("#setRobloxShare")) $("#setRobloxShare").value = s.roblox_share_link || "";
  if ($("#setRobloxPlace")) $("#setRobloxPlace").value = s.roblox_place_id || "";
  if ($("#setRobloxCode")) $("#setRobloxCode").value = s.roblox_link_code || "";
  syncLoopControls();
  renderHotkeys();
  renderThemes();
  renderLanguages();
}

async function setSetting(key, value) {
  var merged = await api("set_setting", key, value);
  if (merged) state.settings = merged;
  return merged;
}

async function runHealthCheck() {
  var host = $("#healthList");
  host.innerHTML = "";
  host.appendChild(el("div", { class: "empty", text: t("diag_running") }));
  var rows = await api("run_health_check");
  host.innerHTML = "";
  if (!Array.isArray(rows)) {
    host.appendChild(el("div", { class: "empty", text: t("diag_failed") }));
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
    [t("env_version"), bootstrap.version || state.version],
    [t("env_ocr"), bootstrap.ocr_engine || "unknown"],
    [t("env_scale"), (bootstrap.display_scale || 100) + "%"]
  ];
  tags.forEach(function (t) {
    host.appendChild(el("span", { class: "env-tag", html: t[0] + " <b>" + String(t[1]) + "</b>" }));
  });
}

async function resetSettings() {
  var yes = await askConfirm(t("set_ask_reset"), t("set_ask_reset_body"));
  if (!yes) return;
  var before = currentLang();
  var merged = await api("reset_settings");
  if (!merged) return;
  state.settings = merged;
  /* A reset puts the language back to its default too, so the whole window
     may have to change language along with everything else. */
  if (currentLang() !== before) {
    await refreshCatalog();
    relocalize();
  }
  applySettingsToUI();          /* re-applies the theme and the loop controls */
  renderPhases();               /* the Loop header carries two of them */
  refreshTargetInfo();
  refreshWebhook();             /* a reset also drops the saved webhook URL */
  toast(t("set_reset_done"), "ok");
}

/* ==========================================================================
   18. CONTROL BAR + STATUS POLLING
   ========================================================================== */
async function startMacro() {
  if (state.status.running) { toast(t("ctl_already")); return; }
  var macro = currentMacro();
  if (!macro.phases.setup.length && !macro.phases.loop.length) {
    toast(t("ctl_need_block"), "err");
    return;
  }
  var result = await api("start_macro", macro);
  if (result && result.ok === false) {
    var why = result.reason === "no_target" ? t("ctl_no_target_reason")
      : result.reason === "recording" ? t("ctl_recording_reason")
        : result.reason;
    toast(t("ctl_cannot_start") + ": " + why, "err");
    return;
  }
  pollStatus();
}

async function stopMacro() { await api("stop_macro"); pollStatus(); }
async function togglePause() { await api("toggle_pause"); pollStatus(); }

/* Seconds as 0:07 / 3:41 / 1:02:33. Hours only appear once there are any,
   so the common case stays as short as the pill is wide. */
function formatRunTime(seconds) {
  var total = Math.max(0, Math.floor(Number(seconds) || 0));
  var h = Math.floor(total / 3600);
  var m = Math.floor((total % 3600) / 60);
  var s = total % 60;
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  return h ? (h + ":" + pad(m) + ":" + pad(s)) : (m + ":" + pad(s));
}

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
  $$("span", pause)[0].textContent = t(status.paused ? "ctl_resume" : "ctl_pause");

  var dot = $("#runDot");
  dot.className = "run-dot" + (status.running ? (status.paused ? " pause" : " on") : "");
  /* The clock keeps the finished run's duration instead of snapping back to
     zero, so "how long did that take" survives pressing Stop. */
  var clock = $("#statusTime");
  if (clock) {
    clock.textContent = formatRunTime(status.elapsed_s || 0);
    clock.classList.toggle("on", !!status.running && !status.paused);
    clock.title = tf("ctl_runtime_tip", formatRunTime(status.elapsed_s || 0),
                     status.passes || 0);
  }
  $("#statusAction").textContent = status.action || t("ctl_idle");
  $("#statusLoop").textContent = tf("ctl_loop", status.loop || 0);
  $("#statusMeta").textContent = status.recording
    ? tf("ctl_recording", status.rec_count || 0)
    : (status.target ? tf("ctl_target", status.target) : t("ctl_no_target"));

  var tdot = $("#targetDot");
  var ttitle = $("#targetTitle");
  if (tdot) tdot.className = "dot " + (status.target_alive ? "dot-on" : "dot-off");
  if (ttitle) ttitle.textContent = status.target || t("target_none");

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
    toast(t("recedit_close_first"), "err");
    return;
  }
  var focus = state.focusedCoord;
  if (!focus) { toast(t("pick_focus_first"), "err"); return; }
  var block = findBlock(focus.phase, focus.id);
  if (!block) { toast(t("pick_block_gone"), "err"); return; }
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
  if (btn) btn.title = t(winMaximized ? "win_restore" : "win_maximize");
  document.body.classList.toggle("is-maximized", winMaximized);
}

/* --------------------------------------------------------------------------
   Frameless move and resize.

   The window has no OS border, so nothing starts Windows' own move/resize
   loops. Doing them here in JavaScript would mean chasing the pointer a
   frame behind and losing snapping, aero-snap and multi-monitor edges, so
   instead the mousedown is handed straight back to Windows.
   -------------------------------------------------------------------------- */
function wireFramelessChrome() {
  $$(".resize-grip").forEach(function (grip) {
    grip.addEventListener("mousedown", function (e) {
      if (e.button !== 0 || winMaximized) return;
      e.preventDefault();
      apiQ("begin_window_resize", grip.dataset.edge);
    });
  });

  var bar = $(".titlebar");
  if (!bar) return;
  bar.addEventListener("mousedown", function (e) {
    /* Left button, and not on something with its own job. */
    if (e.button !== 0) return;
    if (e.target.closest("button, input, select, .target-chip, .sel")) return;
    e.preventDefault();
    apiQ("begin_window_drag");
  });
}

async function toggleMaximize() {
  var result = await apiQ("toggle_maximize");
  /* No answer means the bridge is not there (or the call failed); flipping the
     icon anyway would show "restore" on a window that never maximised. */
  if (!result || result.ok === false) return;
  setMaximizedUI(!!result.maximized);
}

/* ==========================================================================
   20a. BLOCK SEARCH
   ========================================================================== */
function applyBlockSearch() {
  var inp = $("#blockSearchInp");
  var q = inp ? inp.value.trim().toLowerCase() : "";
  var total = 0, shown = 0;
  $$("#phases .phase").forEach(function (ph) {
    var rows = $$("#phases .block-row", ph);
    var phShown = 0;
    rows.forEach(function (row) {
      total++;
      var label = ($("#phases .row-type", row) || row.querySelector(".row-type"));
      var text = label ? label.textContent.toLowerCase() : "";
      var vis = !q || text.indexOf(q) >= 0;
      row.style.display = vis ? "" : "none";
      if (vis) { phShown++; shown++; }
    });
    // If all rows hidden and searching, show a hint; else restore dropzone visibility
    var dz = ph.querySelector(".dropzone");
    if (dz) dz.style.display = (rows.length === 0 || (q && phShown === 0)) ? "" : "none";
  });
  var cnt = $("#blockSearchCount");
  if (cnt) cnt.textContent = q && total > 0 ? shown + " / " + total : "";
}

/* ==========================================================================
   20b. DEBUGGER
   ========================================================================== */
var dbg = { active: false, steps: [], cursor: -1, panel: null };

function debugBuildSteps() {
  var steps = [];
  var phases = (state.macro && state.macro.phases) ? state.macro.phases : {};
  var order = ["setup", "loop", "watch"];
  order.forEach(function (ph) {
    var arr = phases[ph];
    if (!Array.isArray(arr)) return;
    arr.forEach(function (block, idx) {
      steps.push({ phase: ph, idx: idx, block: block });
    });
  });
  return steps;
}

function debugHighlight(stepObj) {
  $$("#phases .block-row").forEach(function (r) { r.classList.remove("debug-current"); });
  if (!stepObj) return;
  // Find block row by its rendered data-id attribute or position
  var rows = $$("#phases .phase-" + stepObj.phase + " .block-row");
  if (!rows.length) rows = $$("#phases .block-row"); // fallback
  var row = rows[stepObj.idx];
  if (row) { row.classList.add("debug-current"); row.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
}

function debugShowPanel(stepObj) {
  var panel = $("#debugPanel");
  if (!panel) return;
  if (!stepObj) { panel.classList.add("hidden"); return; }
  panel.classList.remove("hidden");
  var spec = stepObj.block ? specFor(stepObj.block.type) : null;
  var name = (spec && spec.label) || prettyType(stepObj.block && stepObj.block.type) || "—";
  var info = (stepObj.cursor + 1) + " / " + dbg.steps.length + " · " + stepObj.phase;
  var nameEl = $("#debugBlockName");
  var infoEl = $("#debugStepInfo");
  if (nameEl) nameEl.textContent = name;
  if (infoEl) infoEl.textContent = info;
  // render params
  var varsEl = $("#debugVars");
  if (varsEl) {
    varsEl.innerHTML = "";
    var params = (stepObj.block && stepObj.block.params) ? stepObj.block.params : {};
    var keys = Object.keys(params);
    if (!keys.length) {
      var em = document.createElement("div");
      em.className = "empty"; em.textContent = "No params"; em.style.fontSize = "11px";
      varsEl.appendChild(em);
    } else {
      keys.forEach(function (k) {
        var v = params[k];
        var row = document.createElement("div");
        row.className = "debug-var-row";
        var kEl = document.createElement("span"); kEl.className = "debug-var-key"; kEl.textContent = k;
        var vEl = document.createElement("span"); vEl.className = "debug-var-val";
        vEl.textContent = v == null ? "null" : (typeof v === "object" ? JSON.stringify(v) : String(v));
        row.appendChild(kEl); row.appendChild(vEl);
        varsEl.appendChild(row);
      });
    }
  }
}

function debugStop() {
  dbg.active = false; dbg.steps = []; dbg.cursor = -1;
  $$("#phases .block-row").forEach(function (r) { r.classList.remove("debug-current"); });
  var panel = $("#debugPanel"); if (panel) panel.classList.add("hidden");
  var btnStep = $("#btnDebugStep"); if (btnStep) btnStep.style.display = "none";
  var btnDebug = $("#btnDebug"); if (btnDebug) btnDebug.classList.remove("active");
  toast("Debugger stopped");
}

async function debugStep() {
  if (!dbg.active) return;
  dbg.cursor++;
  if (dbg.cursor >= dbg.steps.length) { debugStop(); toast("Debug complete ✓", "ok"); return; }
  var s = dbg.steps[dbg.cursor];
  s.cursor = dbg.cursor;
  debugHighlight(s);
  debugShowPanel(s);
  // Run this block in isolation
  if (s.block) {
    var res = await apiQ("run_single_block", s.block);
    var ok = res && res.ok !== false;
    var reasonEl = $("#debugVars");
    if (reasonEl && !ok) {
      var errEl = document.createElement("div");
      errEl.style.cssText = "color:var(--danger);font-size:11px;margin-top:4px;";
      errEl.textContent = "⚠ " + ((res && res.reason) || "failed");
      reasonEl.appendChild(errEl);
    }
  }
}

function debugStart() {
  if (dbg.active) { debugStop(); return; }
  dbg.steps = debugBuildSteps();
  if (!dbg.steps.length) { toast("No blocks to debug", "warn"); return; }
  dbg.active = true;
  dbg.cursor = -1;
  var btnDebug = $("#btnDebug"); if (btnDebug) btnDebug.classList.add("active");
  var btnStep = $("#btnDebugStep"); if (btnStep) btnStep.style.display = "";
  toast("Debugger started — click Step ▶ to advance");
  showScreen("builder");
}

/* ==========================================================================
   20c. RUN STATISTICS
   ========================================================================== */
async function renderRunStats() {
  var list = $("#statsList"); if (!list) return;
  list.innerHTML = "<div class=\"empty\">Loading...</div>";
  var data = await apiQ("get_run_stats");
  if (!data) { list.innerHTML = "<div class=\"empty\">Not available</div>"; return; }
  var rows = [
    { name: "Total runs", ok: data.runs > 0, detail: data.runs + " run" + (data.runs !== 1 ? "s" : "") },
    { name: "Errors", ok: data.errors === 0, detail: data.errors + " error" + (data.errors !== 1 ? "s" : "") },
    { name: "Avg duration", ok: true, detail: data.avg_s + " s" },
    { name: "Last error", ok: !data.last_error, detail: data.last_error || "none" }
  ];
  list.innerHTML = "";
  rows.forEach(function (r) {
    var row = document.createElement("div"); row.className = "health-row";
    var dot = document.createElement("span"); dot.className = r.ok ? "dot dot-on" : "dot dot-off";
    var nm = document.createElement("span"); nm.className = "health-name"; nm.textContent = r.name;
    var dt = document.createElement("span"); dt.className = "health-detail"; dt.textContent = r.detail;
    row.appendChild(dot); row.appendChild(nm); row.appendChild(dt);
    list.appendChild(row);
  });
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
  wireFramelessChrome();

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
  $("#macroName").addEventListener("input", function () {
    state.currentName = $("#macroName").value.trim();
    markDirty();
  });

  /* Load / Import / Export are all dropdowns now; only one is ever open. */
  renderIoMenus();
  wireMenuButton("#btnLoadMacro", "#macroMenu", refreshMacroList);
  wireMenuButton("#btnImportMacro", "#importMenu");
  wireMenuButton("#btnExportMacro", "#exportMenu");
  /* Capture-phase mousedown, not a bubbling click: the custom dropdowns in
     the block rows call stopPropagation on their own click, so a toolbar menu
     stayed open behind a select panel that had just opened on top of it. */
  document.addEventListener("mousedown", function (e) {
    if (e.target && e.target.closest && e.target.closest(".dropdown")) return;
    closeToolMenus();
  }, true);

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
  /* change, not input: these are pasted links, and a setting write per
     keystroke would hit the disk for every character. */
  [["#setRobloxShare", "roblox_share_link"],
   ["#setRobloxPlace", "roblox_place_id"], ["#setRobloxCode", "roblox_link_code"]]
    .forEach(function (pair) {
      var node = $(pair[0]);
      if (!node) return;
      node.addEventListener("change", function () {
        setSetting(pair[1], node.value.trim());
      });
    });
  $("#optMinGap").addEventListener("input", function () {
    setSetting("record_min_gap_ms", recOptions().minGap);
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
  $("#btnBlocksEditDone").addEventListener("click", finishBlocksEditor);
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
    paintRegionReadout,
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
  $("#btnBigViewMap").addEventListener("click", function () { saveMapCrop(); });
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
  $("#btnSaveMap").addEventListener("click", function () { saveMapCrop(); });
  attachTip($("#btnSaveMap"), function () { return t("img_save_map"); },
            function () { return t("img_save_map_tip"); });
  $("#btnImportMap2").addEventListener("click", importMapFile);
  $("#btnRefreshTemplates").addEventListener("click", function () {
    refreshTemplates();
    refreshMaps();
  });
  $("#btnOpenAssets2").addEventListener("click", function () { apiQ("open_assets_folder"); });
  $("#btnOpenMaps2").addEventListener("click", function () { apiQ("open_maps_folder"); });

  /* --- image picker -------------------------------------------------- */
  wireGroupUI();
  $("#tplPickFilter").addEventListener("input", function () {
    tplPick.filter = $("#tplPickFilter").value.trim();
    renderTplPickGrid();
  });
  $("#btnTplPickNone").addEventListener("click", function () { closeTemplatePicker(""); });
  $("#btnTplPickNew").addEventListener("click", templatePickerCaptureNew);
  $("#btnTplPickCancel").addEventListener("click", function () { closeTemplatePicker(undefined); });
  $("#btnTplPickClose").addEventListener("click", function () { closeTemplatePicker(undefined); });

  /* --- settings screen ---------------------------------------------- */
  $("#btnPalettes").addEventListener("click", openPaletteManager);
  $("#btnPaletteClose").addEventListener("click", closePaletteManager);
  $("#btnPaletteDone").addEventListener("click", closePaletteManager);
  $("#btnPaletteSave").addEventListener("click", savePaletteDraft);
  $("#btnPaletteNew").addEventListener("click", function () {
    paletteEdit = { name: "", types: [] };
    $("#paletteName").value = "";
    renderPaletteEditor();
  });
  $("#btnPaletteAll").addEventListener("click", function () {
    paletteEdit.types = state.catalog.map(function (spec) { return spec.type; });
    renderPaletteEditor();
  });
  $("#btnPaletteNone").addEventListener("click", function () {
    paletteEdit.types = [];
    renderPaletteEditor();
  });
  $("#btnPaletteImport").addEventListener("click", importPaletteFile);
  $("#btnPaletteFolder").addEventListener("click", function () { apiQ("open_palettes_folder"); });

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
  attachTip($("#confLabel"),
            function () { return t("tip_conf_title"); },
            function () { return t("tip_conf_body"); });
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
  ["#hookTitle", "#hookDescription", "#hookColor", "#hookFooter", "#hookTimestamp"]
    .forEach(function (sel) {
      var node = $(sel);
      if (node) node.addEventListener("change", saveWebhookDesign);
    });

  $("#btnHealth").addEventListener("click", runHealthCheck);
  $("#btnOpenData").addEventListener("click", function () { apiQ("open_data_folder"); });
  $("#btnOpenAssets").addEventListener("click", function () { apiQ("open_assets_folder"); });
  $("#btnResetSettings").addEventListener("click", resetSettings);

  /* --- block search -------------------------------------------------- */
  var bsInp = $("#blockSearchInp");
  if (bsInp) bsInp.addEventListener("input", applyBlockSearch);

  /* --- debugger ------------------------------------------------------ */
  var btnDebug = $("#btnDebug");
  if (btnDebug) btnDebug.addEventListener("click", debugStart);
  var btnDebugStep = $("#btnDebugStep");
  if (btnDebugStep) btnDebugStep.addEventListener("click", debugStep);

  /* --- run stats ----------------------------------------------------- */
  var btnResetStats = $("#btnResetStats");
  if (btnResetStats) btnResetStats.addEventListener("click", async function () {
    await apiQ("reset_run_stats");
    renderRunStats();
    toast("Statistics reset");
  });

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
      closeToolMenus();
      return;
    }
    var top = open.reduce(function (best, o) {
      var z = parseInt(getComputedStyle(o).zIndex, 10) || 0;
      var bz = parseInt(getComputedStyle(best).zIndex, 10) || 0;
      /* Ties break on DOM order: later markup paints on top. */
      return z >= bz ? o : best;
    }, open[0]);

    /* self-handled: each owes its caller a promise */
    if (top.id === "textModal" || top.id === "confirmModal" || top.id === "bundleModal") return;
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
    if (top.id === "groupModal") { closeGroupModal(); return; }
    if (top.id === "paletteModal") { closePaletteManager(); return; }
    /* promptModal answers Escape itself (capture phase), so it never
       reaches here. */
    if (top.id === "tplPickModal") { closeTemplatePicker(undefined); return; }
    if (top.id === "winPickModal") { closeWinPicker(undefined); return; }
    top.classList.add("hidden");
  });
}

/* ==========================================================================
   21. BOOTSTRAP
   ========================================================================== */
/* ==========================================================================
   20b. SAVED BLOCK GROUPS

   A group is a named list of blocks that can be dropped into Setup, Loop or
   Watch as often as needed. Inserting COPIES the blocks (with fresh ids)
   rather than linking to them: two rows sharing an id would delete and edit
   each other, and a group is a starting point, not a live reference.
   ========================================================================== */
var groupPick = { open: false, phase: null, filter: "" };

function phaseLabelOf(key) {
  var found = null;
  state.phases.forEach(function (p) { if (p.key === key) found = p; });
  return found ? phaseTitle(found) : String(key || "");
}

function selectionFor(phase) {
  if (!state.selection || state.selection.phase !== phase) return [];
  return state.selection.ids || [];
}

function isSelected(phase, id) {
  return selectionFor(phase).indexOf(id) >= 0;
}

function toggleSelected(phase, id) {
  /* Ticking in a second phase drops the first one's ticks: a group is one
     ordered list, and blocks from two phases have no single order. */
  if (!state.selection || state.selection.phase !== phase) {
    state.selection = { phase: phase, ids: [] };
  }
  var ids = state.selection.ids;
  var at = ids.indexOf(id);
  if (at >= 0) ids.splice(at, 1);
  else ids.push(id);
  if (!ids.length) state.selection = { phase: null, ids: [] };
  renderPhases();
}

function clearSelection() {
  state.selection = { phase: null, ids: [] };
  renderPhases();
}

/* Ticked blocks in PHASE order, not in the order they were clicked -- the
   group has to run the way it reads on screen. */
function selectedBlocks(phase) {
  var ids = selectionFor(phase);
  if (!ids.length) return [];
  return phaseArray(phase).filter(function (b) { return ids.indexOf(b.id) >= 0; });
}

async function saveGroupFrom(phase, label) {
  var ticked = selectedBlocks(phase);
  var blocks = ticked.length ? ticked : phaseArray(phase).slice();
  if (!blocks.length) { toast(t("grp_nothing"), "err"); return; }

  var name = await askPrompt(
    t("grp_save_title"),
    ticked.length ? tf("grp_save_sel", ticked.length, label)
                  : tf("grp_save_all", blocks.length, label),
    "");
  if (name === null) return;
  name = String(name).trim();
  if (!name) { toast(t("grp_need_name"), "err"); return; }

  var clash = (state.groups || []).some(function (g) { return g.name === name; });
  if (clash) {
    var yes = await askConfirm(tf("grp_overwrite", name), t("grp_overwrite_body"));
    if (!yes) return;
  }

  var result = await api("save_block_group", name,
                         JSON.parse(JSON.stringify(blocks)));
  if (!result || !result.ok) {
    toast(t("grp_save_failed")
          + (result && result.reason ? ": " + result.reason : ""), "err");
    return;
  }
  state.groups = result.groups || [];
  clearSelection();
  toast(tf("grp_saved", result.name, blocks.length), "ok");
}

function closeGroupModal() {
  groupPick.open = false;
  var overlay = $("#groupModal");
  if (overlay) overlay.classList.add("hidden");
}

async function openGroupModal(phase) {
  var overlay = $("#groupModal");
  if (!overlay) return;
  groupPick.open = true;
  groupPick.phase = phase;
  groupPick.filter = "";
  var filter = $("#grpFilter");
  if (filter) filter.value = "";
  overlay.classList.remove("hidden");
  /* Painted from what is already known, then repainted from disk: a group
     saved in another window (or deleted by hand) shows up without a reload,
     and the grid never appears empty for the length of a round trip. */
  renderGroupList();
  var fresh = await api("list_block_groups");
  if (Array.isArray(fresh) && groupPick.open) {
    state.groups = fresh;
    renderGroupList();
  }
}

function renderGroupList() {
  var host = $("#grpList");
  if (!host) return;
  var target = $("#grpTarget");
  if (target) target.textContent = phaseLabelOf(groupPick.phase);

  var needle = String(groupPick.filter || "").trim().toLowerCase();
  var shown = (state.groups || []).filter(function (g) {
    return !needle || String(g.name).toLowerCase().indexOf(needle) >= 0;
  });

  host.innerHTML = "";
  if (!shown.length) {
    /* "nothing saved" and "nothing matches" are different problems, and only
       one of them is fixed by saving a group. */
    host.appendChild(el("div", { class: "empty",
      text: (state.groups || []).length ? t("grp_no_match") : t("grp_empty") }));
    return;
  }
  shown.forEach(function (g) { host.appendChild(groupRow(g)); });
}

function groupRow(g) {
  var count = toInt(g.count, 0);
  var row = el("div", { class: "grp-row" }, [
    el("span", { class: "grp-name", text: g.name }),
    el("span", { class: "grp-count",
                 text: count + " " + t(count === 1 ? "block_1" : "block_n") }),
    el("span", { class: "flex-spacer" })
  ]);

  var insertBtn = el("button", { class: "btn btn-sm btn-primary", text: t("grp_insert") });
  insertBtn.addEventListener("click", function () { insertGroup(g.name); });

  var renameBtn = el("button", { class: "btn btn-sm", text: t("grp_rename") });
  renameBtn.addEventListener("click", async function () {
    var name = await askPrompt(t("grp_rename"), g.name, g.name);
    if (name === null) return;
    name = String(name).trim();
    if (!name || name === g.name) return;
    var result = await api("rename_block_group", g.name, name);
    if (!result || !result.ok) { toast(t("grp_save_failed"), "err"); return; }
    state.groups = result.groups || [];
    renderGroupList();
  });

  var delBtn = el("button", { class: "iconbtn danger", title: t("btn_delete") },
                  [icon("i-trash", "ic-xs")]);
  delBtn.addEventListener("click", async function () {
    var yes = await askConfirm(tf("grp_delete_q", g.name), t("grp_delete_body"));
    if (!yes) return;
    var result = await api("delete_block_group", g.name);
    if (result) state.groups = result.groups || [];
    renderGroupList();
  });

  row.appendChild(insertBtn);
  row.appendChild(renameBtn);
  row.appendChild(delBtn);
  return row;
}

async function insertGroup(name) {
  var phase = groupPick.phase;
  if (!isPhaseKey(phase)) { closeGroupModal(); return; }
  var result = await api("load_block_group", name);
  if (!result || !result.ok || !Array.isArray(result.blocks) || !result.blocks.length) {
    toast(t("grp_load_failed"), "err");
    return;
  }
  /* reid: the same group may sit in Setup and in Loop at once. */
  var copies = normalizeList(result.blocks, true);
  if (!copies.length) { toast(t("grp_load_failed"), "err"); return; }
  var list = phaseArray(phase);
  copies.forEach(function (b) { list.push(b); });
  closeGroupModal();
  renderPhases();
  markDirty();
  toast(tf("grp_inserted", copies.length, phaseLabelOf(phase)), "ok");
}

/* A one-line text question. Same shape as askConfirm: resolves with the text,
   or null when the user backed out -- "" has to stay distinguishable from
   "cancelled", or an empty name would look like a cancel. */
function askPrompt(title, text, value) {
  return new Promise(function (resolve) {
    var overlay = $("#promptModal");
    if (!overlay) { resolve(null); return; }
    $("#promptTitle").textContent = title || t("ask_title");
    $("#promptText").textContent = text || "";
    var input = $("#promptInput");
    input.value = value == null ? "" : String(value);
    overlay.classList.remove("hidden");

    function done(result) {
      overlay.classList.add("hidden");
      $("#btnPromptOk").removeEventListener("click", ok);
      $("#btnPromptCancel").removeEventListener("click", cancel);
      document.removeEventListener("keydown", key, true);
      resolve(result);
    }
    function ok() { done(input.value); }
    function cancel() { done(null); }
    /* Capture phase, like askConfirm: this is the topmost thing on screen, so
       Escape must answer it instead of closing the modal underneath. */
    function key(e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancel(); }
      else if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); ok(); }
    }
    $("#btnPromptOk").addEventListener("click", ok);
    $("#btnPromptCancel").addEventListener("click", cancel);
    document.addEventListener("keydown", key, true);
    setTimeout(function () { input.focus(); input.select(); }, 20);
  });
}

function wireGroupUI() {
  var filter = $("#grpFilter");
  if (filter) {
    filter.addEventListener("input", function () {
      groupPick.filter = filter.value;
      renderGroupList();
    });
  }
  var folder = $("#btnGrpFolder");
  if (folder) folder.addEventListener("click", function () { api("open_groups_folder"); });
  ["#btnGrpCancel", "#btnGrpClose"].forEach(function (sel) {
    var node = $(sel);
    if (node) node.addEventListener("click", function () { closeGroupModal(); });
  });
}

/* =====================================================================
   User block palettes. A palette is intentionally only a named list of
   catalog type ids: it never contains macros, images, recordings or secrets,
   which makes the exported JSON safe to share.
   ===================================================================== */
var paletteEdit = { name: "", types: [] };

function closePaletteManager() {
  var overlay = $("#paletteModal");
  if (overlay) overlay.classList.add("hidden");
}

function renderPaletteEditor() {
  var host = $("#paletteEditorGrid");
  if (!host) return;
  host.innerHTML = "";
  var selected = new Set(paletteEdit.types || []);
  state.catalog.forEach(function (spec) {
    var input = el("input", { type: "checkbox" });
    input.checked = selected.has(spec.type);
    input.addEventListener("change", function () {
      var next = new Set(paletteEdit.types || []);
      if (input.checked) next.add(spec.type); else next.delete(spec.type);
      paletteEdit.types = Array.from(next);
    });
    host.appendChild(el("label", { class: "palette-pick" }, [
      input,
      el("span", { class: "chip-dot", style: "--chip-color:" + colorOf(spec.color) }),
      el("span", { text: spec.label || prettyType(spec.type) })
    ]));
  });
}

function renderSavedPalettes() {
  var host = $("#paletteSavedList");
  if (!host) return;
  host.innerHTML = "";
  if (!(state.palettes || []).length) {
    host.appendChild(el("div", { class: "empty", text: t("palette_empty") }));
    return;
  }
  state.palettes.forEach(function (palette) {
    var row = el("div", { class: "palette-saved-row" }, [
      el("span", { class: "palette-saved-name", text: palette.name }),
      el("span", { class: "palette-saved-count", text: String((palette.types || []).length) }),
      el("span", { class: "flex-spacer" })
    ]);
    var use = el("button", { class: "btn btn-xs" + (state.activePalette === palette.name ? " active" : ""), text: t("palette_use") });
    use.addEventListener("click", function () {
      state.activePalette = state.activePalette === palette.name ? "" : palette.name;
      renderPalette();
      renderSavedPalettes();
    });
    var edit = el("button", { class: "btn btn-xs", text: t("palette_edit") });
    edit.addEventListener("click", function () {
      paletteEdit = { name: palette.name, types: (palette.types || []).slice() };
      $("#paletteName").value = paletteEdit.name;
      renderPaletteEditor();
    });
    var out = el("button", { class: "btn btn-xs", text: t("palette_export") });
    out.addEventListener("click", async function () {
      var result = await api("export_block_palette", palette.name);
      if (result && result.ok) toast(t("palette_exported"), "ok");
    });
    var del = el("button", { class: "btn btn-xs btn-ghost-danger", text: t("palette_delete") });
    del.addEventListener("click", async function () {
      if (!await askConfirm(t("palette_delete_q"), t("palette_delete_body"))) return;
      var result = await api("delete_block_palette", palette.name);
      if (!result || result.ok === false) return;
      state.palettes = result.palettes || [];
      if (state.activePalette === palette.name) { state.activePalette = ""; renderPalette(); }
      renderSavedPalettes();
    });
    row.appendChild(use); row.appendChild(edit); row.appendChild(out); row.appendChild(del);
    host.appendChild(row);
  });
}

function openPaletteManager() {
  paletteEdit = { name: "", types: state.catalog.map(function (spec) { return spec.type; }) };
  $("#paletteName").value = "";
  renderPaletteEditor();
  renderSavedPalettes();
  $("#paletteModal").classList.remove("hidden");
}

async function savePaletteDraft() {
  var name = ($("#paletteName").value || "").trim();
  if (!name) { toast(t("palette_need_name"), "err"); return; }
  if (!(paletteEdit.types || []).length) { toast(t("palette_need_blocks"), "err"); return; }
  var result = await api("save_block_palette", name, paletteEdit.types);
  if (!result || result.ok === false) { toast(t("palette_save_failed"), "err"); return; }
  state.palettes = result.palettes || [];
  paletteEdit.name = result.palette.name;
  state.activePalette = result.palette.name;
  renderPalette(); renderSavedPalettes();
  toast(t("palette_saved_toast"), "ok");
}

async function importPaletteFile() {
  var result = await api("import_block_palette");
  if (!result || result.reason === "cancelled") return;
  if (result.ok === false) { toast(t("palette_import_failed"), "err"); return; }
  state.palettes = result.palettes || [];
  renderSavedPalettes();
  toast(t("palette_imported"), "ok");
}

async function init() {
  if (state.booted) return;
  state.booted = true;

  var boot = await api("get_bootstrap");
  if (!boot) {
    toast(t("boot_failed"), "err");
    boot = {};
  }

  state.boot = boot;                  /* relocalize() repaints the env row */
  state.version = boot.version || "0.0.0";
  state.catalog = Array.isArray(boot.catalog) ? boot.catalog : [];
  state.byType = {};
  state.catalog.forEach(function (spec) { state.byType[spec.type] = spec; });
  if (Array.isArray(boot.phases) && boot.phases.length) state.phases = boot.phases;
  state.settings = boot.settings || {};
  state.groups = Array.isArray(boot.groups) ? boot.groups : [];
  state.palettes = Array.isArray(boot.palettes) ? boot.palettes : [];
  state.macros = Array.isArray(boot.macros) ? boot.macros : [];
  state.recordings = Array.isArray(boot.recordings) ? boot.recordings : [];

  /* Both before the first render, so the app is never briefly the wrong
     colour or briefly in the wrong language. */
  applyTheme(state.settings.theme);
  applyI18n(document);

  $("#appVersion").textContent = "v" + state.version;

  (boot.logs || []).forEach(appendLogEntry);

  renderIoMenus();
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
  refreshMaps();
  refreshWebhook();

  await pollStatus();
  clearInterval(state.statusTimer);
  state.statusTimer = setInterval(pollStatus, 1000);
}

wireStatic();
window.addEventListener("pywebviewready", init);
/* If the bridge was already up before this script ran, the event never fires. */
if (bridgeReady()) init();
