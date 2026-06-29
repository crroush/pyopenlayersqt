(() => {
  "use strict";

  // --- Canvas readback performance hint ---
  // OpenLayers does frequent getImageData readbacks for hit-detection during selection.
  // Setting willReadFrequently reduces warnings and can improve performance.
  (function patchCanvasGetContext() {
    try {
      if (!window.OL_WILL_READ_FREQUENTLY) return;
      const orig = HTMLCanvasElement.prototype.getContext;
      if (!orig) return;
      HTMLCanvasElement.prototype.getContext = function(type, attrs) {
        if (type === "2d") {
          attrs = attrs || {};
          if (attrs.willReadFrequently == null) attrs.willReadFrequently = true;
        }
        return orig.call(this, type, attrs);
      };
    } catch (e) {
      // ignore
    }
  })();

const state = {
    map: null,
    layers: new Map(),     // layer_id -> {type, layer, source, selectable}
    layerByObj: new Map(), // layer object -> layer_id (for selection filter)
    qtBridge: null,
    selectInteraction: null,
    dragBox: null,
    base_layer: null,
    viewInteracting: false,
    // Measurement mode state
    measureMode: false,
    measurePoints: [],       // Array of [lon, lat] coordinates
    measureLayer: null,      // Vector layer for measurement features
    measureSource: null,     // Vector source for measurement features
    measureOverlay: null,    // Tooltip overlay
    measureTempFeature: null, // Temporary preview line while moving mouse
    measurePointerMoveKey: null,  // Event listener key for map event
    measureClickKey: null,   // Event listener key for map event
    measureKeyDownKey: null, // Flag for keydown event listener (true/false)
    // Coordinate display state
    coordinateOverlay: null,      // Overlay element for coordinates
    coordinatePointerMoveKey: null, // Event listener key for coordinate display
    // Country boundaries layer
    countryBoundariesLayer: null,
    countryBoundariesLoaded: false,
    countryBoundariesLoadPromise: null,
    countryBoundariesStrokeColor: null,
    hydrologyLayer: null,
    hydrologyLoaded: false,
    hydrologyLoadPromise: null,
    perfEnabled: false,
    readyEmitted: false,
  };




  window._pyolqt_state = state;

// Binary transport helpers -------------------------------------------------
//
// Python sends large coordinate/id/color payloads as base64-encoded packed
// arrays instead of JSON lists.  Decoding once into TypedArrays avoids parsing
// millions of JSON tokens and lets the render paths read contiguous memory.
function pyolqt_b64_to_bytes(b64) {
  const binary = atob(b64 || "");
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function pyolqt_b64_to_float64(b64) {
  const bytes = pyolqt_b64_to_bytes(b64);
  return new Float64Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 8);
}

function pyolqt_b64_to_uint32(b64) {
  const bytes = pyolqt_b64_to_bytes(b64);
  return new Uint32Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 4);
}

function pyolqt_b64_to_strings(b64) {
  if (!b64) return null;
  const text = new TextDecoder("utf-8").decode(pyolqt_b64_to_bytes(b64));
  return text.length ? text.split("\0") : [];
}

function pyolqt_points_from_msg(msg) {
  if (msg.coords_b64) {
    const flat = pyolqt_b64_to_float64(msg.coords_b64);
    return { flat, count: msg.point_count || Math.floor(flat.length / 2) };
  }
  const coords = msg.coords || [];
  return { coords, count: coords.length };
}

function pyolqt_ids_from_msg(msg) {
  return msg.ids_b64 ? pyolqt_b64_to_strings(msg.ids_b64) : (msg.feature_ids || msg.ids || []);
}

function pyolqt_indices_from_msg(msg) {
  return msg.indices_b64 ? pyolqt_b64_to_uint32(msg.indices_b64) : (msg.indices || []);
}


// ---- Map extent API (one-shot + debounced watch) ----
function _pyolqt_view_extent_obj() {
  const st = window._pyolqt_state;
  if (!st || !st.map) return null;
  const map = st.map;
  const view = map.getView();
  const mapSize = map.getSize() || [0, 0];
  const extent3857 = view.calculateExtent(mapSize);
  const bl = ol.proj.toLonLat([extent3857[0], extent3857[1]]);
  const tr = ol.proj.toLonLat([extent3857[2], extent3857[3]]);
  return {
    lon_min: bl[0],
    lat_min: bl[1],
    lon_max: tr[0],
    lat_max: tr[1],
    zoom: view.getZoom(),
    resolution: view.getResolution(),
    width_px: mapSize[0],
    height_px: mapSize[1],
  };
}

function cmd_map_get_view_extent(msg) {
  const obj = _pyolqt_view_extent_obj();
  if (!obj) return;
  emitToPython("view_extent", obj);
}

function cmd_perf_set_enabled(msg) {
  state.perfEnabled = !!msg.enabled;
}

const _extentWatch = { enabled: false, token: 0, debounce_ms: 150, timer: null, seq: 0, installed: false };

function _extentWatch_emit_now() {
  const obj = _pyolqt_view_extent_obj();
  if (!obj) return;
  _extentWatch.seq += 1;
  obj.token = _extentWatch.token;
  obj.seq = _extentWatch.seq;
  emitToPython("view_extent_changed", obj);
}

function _extentWatch_schedule() {
  if (!_extentWatch.enabled) return;
  if (_extentWatch.timer) clearTimeout(_extentWatch.timer);
  _extentWatch.timer = setTimeout(() => {
    _extentWatch.timer = null;
    _extentWatch_emit_now();
  }, _extentWatch.debounce_ms);
}

function _extentWatch_install() {
  if (_extentWatch.installed) return;
  const st = window._pyolqt_state;
  if (!st || !st.map) return;
  const map = st.map;
  map.on("moveend", _extentWatch_schedule);
  map.on("change:size", _extentWatch_schedule);
  _extentWatch.installed = true;
}

function cmd_map_set_extent_watch(msg) {
  _extentWatch.enabled = !!msg.enabled;
  _extentWatch.token = (msg.token >>> 0);
  if (msg.debounce_ms != null) _extentWatch.debounce_ms = Math.max(0, msg.debounce_ms | 0);

  _extentWatch_install();
  if (_extentWatch.timer) { clearTimeout(_extentWatch.timer); _extentWatch.timer = null; }

  if (_extentWatch.enabled) {
    _extentWatch_emit_now();
  }
}

function cmd_map_set_view(msg) {
  const st = window._pyolqt_state;
  if (!st || !st.map) return;
  const view = st.map.getView();
  if (!view) return;
  
  if (msg.center && Array.isArray(msg.center) && msg.center.length === 2) {
    const center = lonlat_to_3857(msg.center[0], msg.center[1]);
    view.setCenter(center);
  }
  
  if (msg.zoom !== null && msg.zoom !== undefined) {
    view.setZoom(msg.zoom);
  }
}


function _fit_options_from_msg(msg) {
  let padding = [24, 24, 24, 24];
  if (Array.isArray(msg.padding_px) && msg.padding_px.length === 4) {
    padding = msg.padding_px.map((v) => Math.max(0, v | 0));
  } else if (msg.padding_px != null) {
    const p = Math.max(0, msg.padding_px | 0);
    padding = [p, p, p, p];
  }

  const options = { padding };
  if (msg.max_zoom != null) options.maxZoom = msg.max_zoom;
  if (msg.duration_ms != null) options.duration = Math.max(0, msg.duration_ms | 0);
  return options;
}

function _entry_data_extent(entry, onlyVisibleFeatures) {
  if (!entry) return null;

  if (entry.type === 'vector') {
    const ext = entry.source.getExtent();
    return ol.extent.isEmpty(ext) ? null : ext;
  }

  if (entry.type === 'raster') {
    if (entry.source && typeof entry.source.getImageExtent === 'function') {
      const ext = entry.source.getImageExtent();
      return ext && !ol.extent.isEmpty(ext) ? ext : null;
    }
    return null;
  }

  if (entry.type === 'fast_points' || entry.type === 'fast_geopoints') {
    if (!entry.x || entry.x.length === 0) return null;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    let found = false;
    for (let i = 0; i < entry.x.length; i++) {
      if (entry.deleted && entry.deleted[i]) continue;
      if (onlyVisibleFeatures && entry.hidden && entry.hidden[i]) continue;
      const x = entry.x[i], y = entry.y[i];
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      found = true;
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    }
    if (!found) return null;
    return [minX, minY, maxX, maxY];
  }

  return null;
}

function cmd_map_fit_to_data(msg) {
  const st = window._pyolqt_state;
  if (!st || !st.map) return;
  const map = st.map;
  const view = map.getView();
  if (!view) return;

  const onlyVisibleLayers = msg.only_visible_layers !== false;
  const onlyVisibleFeatures = msg.only_visible_features !== false;
  const requestedLayerIds = Array.isArray(msg.layer_ids) ? new Set(msg.layer_ids.map(String)) : null;

  const combined = ol.extent.createEmpty();
  let hasAny = false;

  for (const [layer_id, entry] of st.layers.entries()) {
    if (requestedLayerIds && !requestedLayerIds.has(String(layer_id))) continue;
    if (onlyVisibleLayers && entry.layer && typeof entry.layer.getVisible === 'function' && !entry.layer.getVisible()) continue;

    const ext = _entry_data_extent(entry, onlyVisibleFeatures);
    if (!ext) continue;

    ol.extent.extend(combined, ext);
    hasAny = true;
  }

  if (!hasAny || ol.extent.isEmpty(combined)) return;

  view.fit(combined, _fit_options_from_msg(msg));
}

function cmd_map_fit_bounds(msg) {
  const st = window._pyolqt_state;
  if (!st || !st.map) return;
  const map = st.map;
  const view = map.getView();
  if (!view) return;

  const b = msg && msg.bounds;
  if (!Array.isArray(b) || b.length !== 2) return;
  const a = b[0], c = b[1];
  if (!Array.isArray(a) || a.length !== 2 || !Array.isArray(c) || c.length !== 2) return;

  const extent = extent_from_bounds(b);
  view.fit(extent, _fit_options_from_msg(msg));
}



  function log(...args) { console.log("JS:", ...args); }
  function jsError(...args) { console.error("JS:", ...args); }

  function emitToPython(event_type, payloadObj) {
    try {
      if (state.qtBridge && typeof state.qtBridge.emitEvent === "function") {
        state.qtBridge.emitEvent(event_type, JSON.stringify(payloadObj || {}));
      }
    } catch (e) {
      jsError("emitToPython failed:", e);
    }
  }

  function pyolqt_perf_enabled() {
    return !!(
      state.perfEnabled ||
      window.PYOLQT_RENDER_PERF ||
      window.PYOLQT_SELECTION_PERF
    );
  }

  function emitPerf(payloadObj) {
    if (pyolqt_perf_enabled()) emitToPython("perf", payloadObj);
  }




  function emitReadyIfNeeded() {
    if (state.readyEmitted) return;
    if (!state.qtBridge || typeof state.qtBridge.emitEvent !== "function") return;
    state.readyEmitted = true;
    emitToPython("ready", { ok: true });
  }

  function ensureMap() {
    if (state.map) return;
    // initMap emits "ready" once it finishes, if qtBridge exists.
    initMap();
  }


// --- FastPoints (index-backed canvas layer) ---
function rgba_from_u32(u) {
  const r = (u >>> 24) & 255;
  const g = (u >>> 16) & 255;
  const b = (u >>> 8) & 255;
  const a = (u) & 255;
  return [r, g, b, a];
}

function rgba_to_css(rgba) {
  const r = rgba[0], g = rgba[1], b = rgba[2], a = rgba[3];
  return "rgba(" + r + "," + g + "," + b + "," + (a / 255.0) + ")";
}

function rgba_to_css_with_opacity(rgba, opacity) {
  const rawOpacity = Number(opacity);
  const effectiveOpacity = Number.isFinite(rawOpacity)
    ? Math.max(0, Math.min(1, rawOpacity))
    : 1.0;
  const r = rgba[0], g = rgba[1], b = rgba[2], a = rgba[3];
  return "rgba(" + r + "," + g + "," + b + "," +
    ((a / 255.0) * effectiveOpacity) + ")";
}

function fp_cell_key(ix, iy) { return ix + "," + iy; }

function fp_index_insert(entry, i) {
  const cs = entry.cellSize;
  const ix = Math.floor(entry.x[i] / cs);
  const iy = Math.floor(entry.y[i] / cs);
  const k = fp_cell_key(ix, iy);
  let arr = entry.grid.get(k);
  if (!arr) { arr = []; entry.grid.set(k, arr); }
  arr.push(i);
}

const FP_QT_WORLD = 20037508.342789244;
const FP_QT_MAX_DEPTH = 18;
const FP_QT_LEAF_CAPACITY = 32;

// FastPoints quadtree -------------------------------------------------------
//
// The tree is maintained in WebMercator meters.  Each node keeps a
// `visibleCount` so hide/show/filter operations can skip entire invisible
// subtrees.  Rendering traverses the tree breadth-first by view extent:
//
//   1. Reject nodes outside the current map extent.
//   2. Collapse nodes whose projected size is below the pixel threshold.
//   3. Scan leaf items only when the node is too large to collapse.
//
// `firstIndex` gives "first color wins" representative selection for collapsed
// nodes while preserving deterministic color/category output.
function fp_qt_new_node(minX, minY, maxX, maxY, depth) {
  return {
    minX, minY, maxX, maxY, depth,
    visibleCount: 0,
    firstIndex: -1,
    items: [],
    children: null,
  };
}

function fp_qt_init(entry) {
  entry.qtRoot = fp_qt_new_node(
    -FP_QT_WORLD, -FP_QT_WORLD, FP_QT_WORLD, FP_QT_WORLD, 0
  );
}

function fp_qt_child_slot(node, x, y) {
  const midX = (node.minX + node.maxX) * 0.5;
  const midY = (node.minY + node.maxY) * 0.5;
  return (x >= midX ? 1 : 0) + (y >= midY ? 2 : 0);
}

function fp_qt_make_children(node) {
  if (node.children) return;
  const midX = (node.minX + node.maxX) * 0.5;
  const midY = (node.minY + node.maxY) * 0.5;
  const d = node.depth + 1;
  node.children = [
    fp_qt_new_node(node.minX, node.minY, midX, midY, d),
    fp_qt_new_node(midX, node.minY, node.maxX, midY, d),
    fp_qt_new_node(node.minX, midY, midX, node.maxY, d),
    fp_qt_new_node(midX, midY, node.maxX, node.maxY, d),
  ];
}

function fp_qt_insert_into_child(entry, node, i) {
  fp_qt_make_children(node);
  const slot = fp_qt_child_slot(node, entry.x[i], entry.y[i]);
  fp_qt_insert_node(entry, node.children[slot], i);
}

function fp_qt_insert_node(entry, node, i) {
  node.visibleCount++;
  if (node.firstIndex < 0) node.firstIndex = i;
  if (node.children) {
    fp_qt_insert_into_child(entry, node, i);
    return;
  }
  if (node.items.length < FP_QT_LEAF_CAPACITY || node.depth >= FP_QT_MAX_DEPTH) {
    node.items.push(i);
    return;
  }
  const oldItems = node.items;
  node.items = [];
  for (let k = 0; k < oldItems.length; k++) {
    fp_qt_insert_into_child(entry, node, oldItems[k]);
  }
  fp_qt_insert_into_child(entry, node, i);
}

function fp_qt_insert(entry, i) {
  if (!entry.qtRoot) fp_qt_init(entry);
  fp_qt_insert_node(entry, entry.qtRoot, i);
}

function fp_qt_update_visibility(entry, i, delta) {
  let node = entry.qtRoot;
  while (node) {
    node.visibleCount += delta;
    if (!node.children) return;
    node = node.children[fp_qt_child_slot(node, entry.x[i], entry.y[i])];
  }
}

function fp_qt_clear_visibility(node) {
  if (!node) return;
  node.visibleCount = 0;
  if (!node.children) return;
  for (let c = 0; c < 4; c++) fp_qt_clear_visibility(node.children[c]);
}

function fp_qt_rebuild_visibility_node(entry, node) {
  if (!node) return 0;
  if (node.children) {
    let total = 0;
    for (let c = 0; c < 4; c++) {
      total += fp_qt_rebuild_visibility_node(entry, node.children[c]);
    }
    node.visibleCount = total;
    return total;
  }
  let total = 0;
  for (let k = 0; k < node.items.length; k++) {
    const i = node.items[k];
    if (!entry.deleted[i] && !entry.hidden[i]) total++;
  }
  node.visibleCount = total;
  return total;
}

function fp_qt_rebuild_visibility(entry) {
  // Bulk filters can change millions of visibility bits at once.  Rebuilding
  // counts bottom-up is O(points + nodes), while per-index updates are
  // O(changed_points * tree_depth) and visibly stall full-range restores.
  fp_qt_rebuild_visibility_node(entry, entry.qtRoot);
}

function fp_qt_intersects(node, extent) {
  return !(node.maxX < extent[0] || node.minX > extent[2] ||
           node.maxY < extent[1] || node.minY > extent[3]);
}

function fp_qt_point_in_extent(entry, i, extent) {
  const x = entry.x[i];
  const y = entry.y[i];
  return x >= extent[0] && x <= extent[2] && y >= extent[1] && y <= extent[3];
}

function fp_qt_is_drawable_representative(entry, i, skipSelected, extent) {
  return i >= 0 &&
    !entry.deleted[i] &&
    !entry.hidden[i] &&
    fp_qt_point_in_extent(entry, i, extent) &&
    (!skipSelected || !entry.selectedIds.has(entry.ids[i]));
}

function fp_qt_pick_representative(entry, node, skipSelected, extent) {
  // Collapsed nodes can straddle a viewport edge.  Pick a representative that
  // is itself inside the current extent; otherwise a partially visible node
  // could collapse to an off-screen point and hide on-screen children.
  if (!node || node.visibleCount <= 0) return -1;
  const first = node.firstIndex;
  if (fp_qt_is_drawable_representative(entry, first, skipSelected, extent)) {
    return first;
  }
  if (node.children) {
    for (let c = 0; c < 4; c++) {
      const child = node.children[c];
      if (!fp_qt_intersects(child, extent)) continue;
      const idx = fp_qt_pick_representative(entry, child, skipSelected, extent);
      if (idx >= 0) return idx;
    }
    return -1;
  }
  for (let k = 0; k < node.items.length; k++) {
    const i = node.items[k];
    if (fp_qt_is_drawable_representative(entry, i, skipSelected, extent)) return i;
  }
  return -1;
}

function fp_query_extent(entry, extent) {
  const cs = entry.cellSize;
  const min_ix = Math.floor(extent[0] / cs);
  const max_ix = Math.floor(extent[2] / cs);
  const min_iy = Math.floor(extent[1] / cs);
  const max_iy = Math.floor(extent[3] / cs);
  
  // Performance optimization: limit cell iteration for zoomed-out views
  // If extent covers too many cells, just return all points
  const cellsX = max_ix - min_ix + 1;
  const cellsY = max_iy - min_iy + 1;
  const totalCells = cellsX * cellsY;
  
  // If we'd check more than 1000 cells, it's faster to just iterate all points
  if (totalCells > 1000) {
    const out = [];
    for (let i = 0; i < entry.x.length; i++) {
      if (entry.deleted[i]) continue;
      const x = entry.x[i];
      const y = entry.y[i];
      if (x >= extent[0] && x <= extent[2] && y >= extent[1] && y <= extent[3]) {
        out.push(i);
      }
    }
    return out;
  }
  
  // Normal grid query for zoomed-in views
  const out = [];
  for (let ix = min_ix; ix <= max_ix; ix++) {
    for (let iy = min_iy; iy <= max_iy; iy++) {
      const arr = entry.grid.get(fp_cell_key(ix, iy));
      if (!arr) continue;
      for (let j = 0; j < arr.length; j++) out.push(arr[j]);
    }
  }
  return out;
}

function fp_pick_nearest(entry, coord3857, radius_m) {
  const r = radius_m;
  const ext = [coord3857[0]-r, coord3857[1]-r, coord3857[0]+r, coord3857[1]+r];
  const cand = fp_query_extent(entry, ext);
  let best = -1;
  let bestd2 = r*r;
  for (let k = 0; k < cand.length; k++) {
    const i = cand[k];
    if (entry.deleted[i] || entry.hidden[i]) continue;
    const dx = entry.x[i] - coord3857[0];
    const dy = entry.y[i] - coord3857[1];
    const d2 = dx*dx + dy*dy;
    if (d2 <= bestd2) { bestd2 = d2; best = i; }
  }
  return best;
}

function fp_emit_selection(entry) {
  const perfStart = performance.now();
  const featureIds = Array.from(entry.selectedIds);
  const arrayMs = performance.now() - perfStart;
  emitToPython("selection", {
    layer_id: entry.layer_id,
    feature_ids: featureIds,
  });
  if (featureIds.length > 100 || window.PYOLQT_SELECTION_PERF) {
    emitPerf({
      side: "javascript",
      layer_id: entry.layer_id,
      operation: "fast_points_emit_selection",
      selection_count: featureIds.length,
      times: {
        array_ms: arrayMs.toFixed(2),
        total_ms: (performance.now() - perfStart).toFixed(2)
      }
    });
  }
}

function fp_emit_singleclick(entry, ctrl_key, meta_key, shift_key, alt_key) {
  emitToPython("singleclick", {
    coord: entry,
    ctrl_key: ctrl_key,
    meta_key: meta_key,
    shift_key: shift_key,
    alt_key: alt_key
  });
}

function fp_redraw(entry) {
  if (entry.source) entry.source.changed();
  if (entry.layer) entry.layer.changed();
  if (state.map) state.map.render();
}

function fp_make_canvas_layer(entry) {
  const source = new ol.source.ImageCanvas({
    projection: state.map.getView().getProjection(),
    ratio: 1,
    canvasFunction: function(extent, resolution, pixelRatio, size, projection) {
      const perfStart = performance.now();
      
      // Track render calls during interactions
      if (state.viewInteracting) {
        state.renderCount = (state.renderCount || 0) + 1;
      }
      
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.floor(size[0] * pixelRatio));
      canvas.height = Math.max(1, Math.floor(size[1] * pixelRatio));
      const ctx = canvas.getContext("2d", { willReadFrequently: !!window.OL_WILL_READ_FREQUENTLY });
      if (!ctx) return canvas;

      // Fold layer opacity into every rendered color instead of relying on
      // ctx.globalAlpha.  This keeps exact, collapsed-quadtree, and any
      // future direct pixel paths visually consistent.
      ctx.globalAlpha = 1.0;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const scaleX = canvas.width / (extent[2] - extent[0]);
      const scaleY = canvas.height / (extent[3] - extent[1]);

      const queryStart = performance.now();
      const root = entry.qtRoot || null;
      const visiblePointCount = root ? root.visibleCount : entry.x.length;
      const queryTime = performance.now() - queryStart;

      const defCss = rgba_to_css_with_opacity(
        entry.style.default_rgba,
        entry.opacity
      );
      const selCss = rgba_to_css_with_opacity(
        entry.style.selected_rgba,
        entry.opacity
      );

      // Render algorithm:
      //
      // - Traverse the quadtree for the current extent rather than scanning
      //   every point.
      // - Collapse dense nodes to one representative when the node is smaller
      //   than the configured pixel threshold.
      // - Batch point draws by color/radius and skip duplicate pixel locations.
      // - Draw unselected points first, then selected points on top.
      const batchStart = performance.now();
      const unselectedBatches = new Map(); // key: "color|radius" -> array of {x, y}
      const selectedBatches = new Map(); // key: "color|radius" -> array of {x, y}
      const seenDrawPixels = new Set(); // key: "color|radius|px|py"
      let skippedDuplicatePixels = 0;
      let drawPointCount = 0;
      let visitedNodeCount = 0;
      let collapsedNodeCount = 0;
      let scannedLeafPointCount = 0;

      function addPointToBatch(i, selectedOverride) {
        if (entry.deleted[i] || entry.hidden[i]) return;
        const mercX = entry.x[i];
        const mercY = entry.y[i];
        if (!Number.isFinite(mercX) || !Number.isFinite(mercY)) return;
        if (mercX < extent[0] || mercX > extent[2] || mercY < extent[1] || mercY > extent[3]) return;
        const x = (mercX - extent[0]) * scaleX;
        const y = (extent[3] - mercY) * scaleY;
        const fid = entry.ids[i];
        const isSel = selectedOverride || entry.selectedIds.has(fid);
        if (!selectedOverride && isSel) return;
        const radius = (isSel ? entry.style.selected_radius : entry.style.radius) * pixelRatio;

        let fill = defCss;
        const u = entry.color_u32[i];
        if (u !== 0) fill = rgba_to_css_with_opacity(
          rgba_from_u32(u),
          entry.opacity
        );
        if (isSel) fill = selCss;

        const key = fill + "|" + radius;
        const pixelKey = key + "|" + Math.round(x) + "|" + Math.round(y);
        if (seenDrawPixels.has(pixelKey)) {
          skippedDuplicatePixels++;
          return;
        }
        seenDrawPixels.add(pixelKey);
        drawPointCount++;

        const batches = isSel ? selectedBatches : unselectedBatches;
        let batch = batches.get(key);
        if (!batch) {
          batch = { fill, radius, points: [] };
          batches.set(key, batch);
        }
        batch.points.push({ x, y });
      }

      function renderLeafItems(node) {
        for (let k = 0; k < node.items.length; k++) {
          scannedLeafPointCount++;
          addPointToBatch(node.items[k], false);
        }
      }

      function traverseNode(node) {
        if (!node || node.visibleCount <= 0 || !fp_qt_intersects(node, extent)) return;
        visitedNodeCount++;
        const pxW = (node.maxX - node.minX) * scaleX;
        const pxH = (node.maxY - node.minY) * scaleY;
        if (pxW <= 1.0 && pxH <= 1.0) {
          const i = fp_qt_pick_representative(entry, node, true, extent);
          if (i >= 0) {
            collapsedNodeCount++;
            addPointToBatch(i, false);
          }
          return;
        }
        if (node.children) {
          for (let c = 0; c < 4; c++) traverseNode(node.children[c]);
          return;
        }
        renderLeafItems(node);
      }

      if (root) {
        traverseNode(root);
      } else {
        const cand = fp_query_extent(entry, extent);
        for (let k = 0; k < cand.length; k++) {
          scannedLeafPointCount++;
          addPointToBatch(cand[k], false);
        }
      }

      if (entry.selectedIds.size > 0) {
        for (const fid of entry.selectedIds) {
          const i = entry.idIndex.get(String(fid));
          if (i == null || entry.deleted[i] || entry.hidden[i]) continue;
          const x = entry.x[i], y = entry.y[i];
          if (x < extent[0] || x > extent[2] || y < extent[1] || y > extent[3]) continue;
          addPointToBatch(i, true);
        }
      }
      const batchTime = performance.now() - batchStart;

      // Draw unselected batches first
      const drawStart = performance.now();
      for (const batch of unselectedBatches.values()) {
        ctx.fillStyle = batch.fill;
        ctx.beginPath();
        for (const pt of batch.points) {
          ctx.moveTo(pt.x + batch.radius, pt.y);
          ctx.arc(pt.x, pt.y, batch.radius, 0, Math.PI * 2);
        }
        ctx.fill();
      }
      
      // Draw selected batches on top
      for (const batch of selectedBatches.values()) {
        ctx.fillStyle = batch.fill;
        ctx.beginPath();
        for (const pt of batch.points) {
          ctx.moveTo(pt.x + batch.radius, pt.y);
          ctx.arc(pt.x, pt.y, batch.radius, 0, Math.PI * 2);
        }
        ctx.fill();
      }
      const drawTime = performance.now() - drawStart;
      
      const totalTime = performance.now() - perfStart;
      
      // Emit performance data to Python side
      if (visiblePointCount > 100) {  // Only log when there are significant points
        emitPerf({
          layer_id: entry.layer_id,
          operation: "fast_points_render",
          point_count: visiblePointCount,
          visited_node_count: visitedNodeCount,
          collapsed_node_count: collapsedNodeCount,
          scanned_leaf_point_count: scannedLeafPointCount,
          draw_point_count: drawPointCount,
          skipped_duplicate_pixels: skippedDuplicatePixels,
          batch_count: unselectedBatches.size + selectedBatches.size,
          times: {
            query_ms: queryTime.toFixed(2),
            batch_ms: batchTime.toFixed(2),
            draw_ms: drawTime.toFixed(2),
            total_ms: totalTime.toFixed(2)
          }
        });
      }
      
      return canvas;
    },
  });

  const layer = new ol.layer.Image({ source, visible: entry.visible });
  entry.source = source;
  entry.layer = layer;
}

function cmd_fast_points_add_layer(msg) {
  const perfStart = performance.now();
  const layer_id = msg.layer_id;
  const entry = {
    type: "fast_points",
    layer_id,
    name: msg.name || layer_id,
    visible: (msg.visible !== false),
    opacity: (msg.opacity == null ? 1.0 : msg.opacity),
    selectable: (msg.selectable === true),
    x: [],
    y: [],
    ids: [],
    color_u32: [],
    deleted: [],
    hidden: [],
    grid: new Map(),
    qtRoot: null,
    cellSize: (msg.cell_size_m || 1000.0),
    selectedIds: new Set(),
    idIndex: new Map(),
    style: msg.style || { radius: 3, default_rgba: [255,51,51,204], selected_radius: 6, selected_rgba: [0,255,255,255] },
    source: null,
    layer: null,
  };
  fp_qt_init(entry);

  fp_make_canvas_layer(entry);
  state.map.addLayer(entry.layer);
  state.layers.set(layer_id, entry);
  state.layerByObj.set(entry.layer, layer_id);
  emitPerf({
    side: "javascript",
    layer_id,
    operation: "fast_points_add_layer",
    elapsed_ms: (performance.now() - perfStart).toFixed(2)
  });
}

function cmd_fast_points_add_points(msg) {
  const perfStart = performance.now();
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  const pointData = pyolqt_points_from_msg(msg);
  const coords = pointData.coords || null;
  const coordsFlat = pointData.flat || null;
  const pointCount = pointData.count;
  const ids = msg.ids_b64 ? pyolqt_b64_to_strings(msg.ids_b64) : (msg.ids || null);
  const colors = msg.colors_b64 ? pyolqt_b64_to_uint32(msg.colors_b64) : (msg.colors || null);
  const startIndex = entry.x.length;
  let skippedInvalidCount = 0;
  const convertStart = performance.now();
  for (let i = 0; i < pointCount; i++) {
    const lon = coordsFlat ? coordsFlat[i * 2] : coords[i][0];
    const lat = coordsFlat ? coordsFlat[i * 2 + 1] : coords[i][1];
    const p = lonlat_to_3857(lon, lat);
    if (!Number.isFinite(p[0]) || !Number.isFinite(p[1])) {
      skippedInvalidCount++;
      continue;
    }
    const idx = entry.x.length;
    entry.x.push(p[0]);
    entry.y.push(p[1]);
    const fid = (ids ? ids[i] : String(idx));
    entry.ids.push(fid);
    entry.idIndex.set(String(fid), idx);
    entry.deleted.push(false);
    entry.hidden.push(false);
    entry.color_u32.push(colors ? (colors[i] >>> 0) : 0);
    fp_index_insert(entry, idx);
    fp_qt_insert(entry, idx);
  }
  const convertIndexMs = performance.now() - convertStart;
  const redrawStart = performance.now();
  const shouldRedraw = (msg.redraw !== false);
  if (shouldRedraw) fp_redraw(entry);
  const redrawMs = performance.now() - redrawStart;
  emitPerf({
    side: "javascript",
    layer_id: entry.layer_id,
    operation: "fast_points_add_points",
    point_count: pointCount,
    accepted_point_count: pointCount - skippedInvalidCount,
    skipped_invalid_count: skippedInvalidCount,
    start_index: startIndex,
    total_points: entry.x.length,
    times: {
      convert_index_ms: convertIndexMs.toFixed(2),
      redraw_requested: shouldRedraw,
      redraw_request_ms: redrawMs.toFixed(2),
      total_ms: (performance.now() - perfStart).toFixed(2)
    }
  });
}

function cmd_fast_points_redraw(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  fp_redraw(entry);
}

function cmd_fast_points_clear(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  entry.x = []; entry.y = []; entry.ids = []; entry.color_u32 = []; entry.deleted = []; entry.hidden = [];
  entry.grid = new Map();
  fp_qt_init(entry);
  entry.idIndex = new Map();
  entry.selectedIds = new Set();
  fp_redraw(entry);
  fp_emit_selection(entry);
}

function cmd_fast_points_remove_ids(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  const raw = pyolqt_ids_from_msg(msg);
  const ids = new Set(raw.map(x => String(x)));
  if (ids.size === 0) return;
  for (const id of ids) {
    const i = entry.idIndex.get(id);
    if (i == null || entry.deleted[i]) continue;
    if (!entry.hidden[i]) fp_qt_update_visibility(entry, i, -1);
    entry.deleted[i] = true;
    entry.selectedIds.delete(entry.ids[i]);
  }
  fp_redraw(entry);
  fp_emit_selection(entry);
}


function cmd_fast_points_set_opacity(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  entry.opacity = msg.opacity;
  fp_redraw(entry);
}

function cmd_base_set_opacity(msg) {
  if (!state.base_layer) return;
  const op = (msg.opacity == null) ? 1.0 : msg.opacity;
  state.base_layer.setOpacity(op);
}


function cmd_base_set_visible(msg) {
  if (!state.base_layer) return;
  state.base_layer.setVisible(!!msg.visible);
}

function parseOsmUrlOverride() {
  const params = new URLSearchParams(window.location.search || "");
  const raw = params.get("pyolqt_osm_url");
  if (!raw) return null;
  const url = String(raw).trim();
  return url || null;
}

function cmd_map_set_background(msg) {
  const el = document.getElementById('map');
  if (!el) return;
  const color = (msg && msg.color != null) ? String(msg.color) : '#ffffff';
  el.style.background = color;
}


function cmd_fast_points_set_visible(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  entry.visible = !!msg.visible;
  entry.layer.setVisible(entry.visible);
}

function cmd_fast_points_set_selectable(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  entry.selectable = !!msg.selectable;
}

function cmd_fast_points_select_set(msg) {
    const perfStart = performance.now();
    const entry = getLayerEntry(msg.layer_id);
    if (entry.type !== "fast_points") return;
    const ids = msg.feature_ids || [];
    const setStart = performance.now();
    entry.selectedIds = new Set(ids);
    const setMs = performance.now() - setStart;
    const redrawStart = performance.now();
    fp_redraw(entry);
    const redrawMs = performance.now() - redrawStart;
    let emitMs = 0.0;
    if (msg.emit !== false) {
      const emitStart = performance.now();
      fp_emit_selection(entry);
      emitMs = performance.now() - emitStart;
    }
    if (ids.length > 100 || window.PYOLQT_SELECTION_PERF) {
      emitPerf({
        side: "javascript",
        layer_id: entry.layer_id,
        operation: "fast_points_select_set",
        selection_count: ids.length,
        emit_requested: msg.emit !== false,
        times: {
          set_ms: setMs.toFixed(2),
          redraw_request_ms: redrawMs.toFixed(2),
          emit_ms: emitMs.toFixed(2),
          total_ms: (performance.now() - perfStart).toFixed(2)
        }
      });
    }
}

function cmd_fast_points_hide_ids(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  const raw = pyolqt_ids_from_msg(msg);
  const ids = new Set(raw.map(x => String(x)));
  if (ids.size === 0) return;
  for (const id of ids) {
    const i = entry.idIndex.get(id);
    if (i == null || entry.deleted[i] || entry.hidden[i]) continue;
    entry.hidden[i] = true;
    fp_qt_update_visibility(entry, i, -1);
  }
  fp_redraw(entry);
}

function cmd_fast_points_show_ids(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  const raw = pyolqt_ids_from_msg(msg);
  const ids = new Set(raw.map(x => String(x)));
  if (ids.size === 0) return;
  for (const id of ids) {
    const i = entry.idIndex.get(id);
    if (i == null || entry.deleted[i] || !entry.hidden[i]) continue;
    entry.hidden[i] = false;
    fp_qt_update_visibility(entry, i, 1);
  }
  fp_redraw(entry);
}

function cmd_fast_points_show_all(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  entry.hidden.fill(false);
  fp_qt_rebuild_visibility(entry);
  fp_redraw(entry);
}

function cmd_fast_points_hide_indices(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  const indices = pyolqt_indices_from_msg(msg);
  for (let k = 0; k < indices.length; k++) {
    const i = indices[k];
    if (i == null || i >= entry.hidden.length || entry.deleted[i] || entry.hidden[i]) continue;
    entry.hidden[i] = true;
    fp_qt_update_visibility(entry, i, -1);
  }
  fp_redraw(entry);
}

function cmd_fast_points_show_indices(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  const indices = pyolqt_indices_from_msg(msg);
  for (let k = 0; k < indices.length; k++) {
    const i = indices[k];
    if (i == null || i >= entry.hidden.length || entry.deleted[i] || !entry.hidden[i]) continue;
    entry.hidden[i] = false;
    fp_qt_update_visibility(entry, i, 1);
  }
  fp_redraw(entry);
}

function cmd_fast_points_show_only_indices(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  const indices = pyolqt_indices_from_msg(msg);
  entry.hidden = new Array(entry.hidden.length).fill(true);
  fp_qt_clear_visibility(entry.qtRoot);
  for (let k = 0; k < indices.length; k++) {
    const i = indices[k];
    if (i == null || i >= entry.hidden.length || entry.deleted[i]) continue;
    if (!entry.hidden[i]) continue;
    entry.hidden[i] = false;
    fp_qt_update_visibility(entry, i, 1);
  }
  fp_redraw(entry);
}

function cmd_fast_points_show_only_index_ranges(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  const ranges = msg.ranges_b64 ? pyolqt_b64_to_uint32(msg.ranges_b64) : (msg.ranges || []);
  entry.hidden.fill(true);
  for (let k = 0; k + 1 < ranges.length; k += 2) {
    const start = Math.min(ranges[k], entry.hidden.length);
    const end = Math.min(ranges[k + 1], entry.hidden.length - 1);
    for (let i = start; i <= end; i++) {
      if (!entry.deleted[i]) entry.hidden[i] = false;
    }
  }
  fp_qt_rebuild_visibility(entry);
  fp_redraw(entry);
}

function cmd_fast_points_set_colors(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  const fids = msg.feature_ids_b64 ? pyolqt_b64_to_strings(msg.feature_ids_b64) : (msg.feature_ids || []);
  const colors = msg.colors_b64 ? pyolqt_b64_to_uint32(msg.colors_b64) : (msg.colors || []);
  if (fids.length !== colors.length) return;
  
  // Update colors for the specified features
  for (let k = 0; k < fids.length; k++) {
    const idx = entry.idIndex.get(String(fids[k]));
    if (idx != null) {
      entry.color_u32[idx] = colors[k] >>> 0;
    }
  }
  
  fp_redraw(entry);
}

function cmd_fast_points_clear_colors(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  entry.color_u32.fill(0);
  fp_redraw(entry);
}

// --- FastGeoPoints (points + uncertainty ellipses; index-backed canvas layer) ---
const _FGP_EARTH_R = 6378137.0;
function _fgp_lat_from_y(y3857) {
  // inverse WebMercator (spherical) latitude
  return Math.atan(Math.sinh(y3857 / _FGP_EARTH_R));
}
function _fgp_sec(lat) {
  const c = Math.cos(lat);
  return c === 0 ? 1e9 : (1.0 / c);
}

function fgp_redraw(entry) {
  entry.renderVersion = (entry.renderVersion || 0) + 1;
  entry.renderCache = null;
  if (entry.source) entry.source.changed();
}
function fgp_emit_selection(entry) {
  emitToPython('selection', { layer_id: entry.layer_id, feature_ids: Array.from(entry.selectedIds) });
}

function fgp_make_canvas_layer(entry) {
  const source = new ol.source.ImageCanvas({
    projection: state.map.getView().getProjection(),
    ratio: 1,
    canvasFunction: function(extent, resolution, pixelRatio, size, projection) {
      const perfStart = performance.now();
      // FastGeoPoints uses the same quadtree traversal as FastPoints, but it
      // also caches the rendered canvas for identical extent/resolution/style
      // inputs.  Panning/zooming invalidates the key; selection/color/filter
      // changes bump `renderVersion` from Python or command handlers.
      const cacheKey = [
        entry.renderVersion || 0,
        state.viewInteracting ? 1 : 0,
        resolution.toPrecision(12),
        pixelRatio,
        size[0],
        size[1],
        extent.map((v) => v.toFixed(2)).join(',')
      ].join('|');
      if (entry.renderCache && entry.renderCache.key === cacheKey) {
        if (window.PYOLQT_RENDER_PERF) {
          emitPerf({
            layer_id: entry.layer_id,
            operation: "fast_geopoints_render_cache_hit",
            elapsed_ms: (performance.now() - perfStart).toFixed(2)
          });
        }
        return entry.renderCache.canvas;
      }
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.floor(size[0] * pixelRatio));
      canvas.height = Math.max(1, Math.floor(size[1] * pixelRatio));
      const ctx = canvas.getContext('2d', { willReadFrequently: !!window.OL_WILL_READ_FREQUENTLY });
      if (!ctx) return canvas;

      // Keep FastGeoPoints opacity consistent with FastPoints by folding the
      // layer opacity into stroke/fill colors.  This avoids special cases for
      // cached or quadtree-collapsed renders.
      ctx.globalAlpha = 1.0;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const scaleX = canvas.width / (extent[2] - extent[0]);
      const scaleY = canvas.height / (extent[3] - extent[1]);
      const TAU = Math.PI * 2;
      const st = entry.style || {};
      const selectedSet = entry.selectedIds || new Set();

      const queryStart = performance.now();
      const root = entry.qtRoot;
      const queryTime = performance.now() - queryStart;

      let visitedNodeCount = 0;
      let collapsedNodeCount = 0;
      let scannedLeafPointCount = 0;
      let skippedDuplicatePixels = 0;
      let representativeCount = 0;
      let ellipseDrawCount = 0;
      let pointDrawCount = 0;

      function inExtent(i) {
        return entry.x[i] >= extent[0] && entry.x[i] <= extent[2] &&
               entry.y[i] >= extent[1] && entry.y[i] <= extent[3];
      }

      function nodePixelSize(node) {
        return {
          w: ((node.maxX - node.minX) / resolution) * pixelRatio,
          h: ((node.maxY - node.minY) / resolution) * pixelRatio,
        };
      }

      // Dense views are handled by quadtree traversal/collapse at render time,
      // not by a separate pre-aggregation or raw ImageData branch.
      const collapsePx = Math.max(
        1.0,
        Number(st.collapse_pixel_size || st.point_radius || 3.0) * pixelRatio
      );
      const drawIndices = [];
      const seenCenterPixels = new Set();

      function addUnselectedDrawIndex(i, fromCollapsedNode) {
        if (entry.deleted[i] || entry.hidden[i] || selectedSet.has(entry.ids[i]) || !inExtent(i)) return;
        const x = (entry.x[i] - extent[0]) * scaleX;
        const y = (extent[3] - entry.y[i]) * scaleY;
        const pixelKey = Math.round(x) + ',' + Math.round(y);
        if (seenCenterPixels.has(pixelKey)) {
          skippedDuplicatePixels++;
          return;
        }
        seenCenterPixels.add(pixelKey);
        drawIndices.push(i);
        if (fromCollapsedNode) representativeCount++;
      }

      function collectDrawIndices() {
        if (!root) return;
        const stack = [root];
        while (stack.length) {
          const node = stack.pop();
          if (!node || node.visibleCount <= 0 || !fp_qt_intersects(node, extent)) continue;
          visitedNodeCount++;
          const px = nodePixelSize(node);
          if (px.w <= collapsePx && px.h <= collapsePx) {
            const rep = fp_qt_pick_representative(entry, node, true, extent);
            if (rep >= 0) {
              collapsedNodeCount++;
              addUnselectedDrawIndex(rep, true);
            }
            continue;
          }
          if (node.children) {
            for (let c = 0; c < 4; c++) stack.push(node.children[c]);
            continue;
          }
          for (let k = 0; k < node.items.length; k++) {
            scannedLeafPointCount++;
            addUnselectedDrawIndex(node.items[k], false);
          }
        }
      }

      collectDrawIndices();

      // ---- Ellipses (batched, quadtree-collapsed for unselected points) ----
      const unselectedEllipsesVisible = entry.ellipsesVisible && st.ellipses_visible !== false;
      const selectedEllipsesVisible = entry.selectedEllipsesVisible && st.selected_ellipses_visible !== false;
      const skipWhileInteracting = (st.skip_ellipses_while_interacting !== false);
      const canDrawEllipses = (unselectedEllipsesVisible || selectedEllipsesVisible) && !(skipWhileInteracting && state.viewInteracting);

      const ellipseStart = performance.now();
      if (canDrawEllipses) {
        const minPx = Math.max(0.0, Number(st.min_ellipse_px || 0.0));
        const maxPerPath = Math.max(250, (st.max_ellipses_per_path | 0) || 2000);

        function addEllipsePath(i, selected) {
          const rx = (entry.a[i] / resolution) * pixelRatio;
          const ry = (entry.b[i] / resolution) * pixelRatio;
          if (rx < minPx && ry < minPx) return false;
          const x = (entry.x[i] - extent[0]) * scaleX;
          const y = (extent[3] - entry.y[i]) * scaleY;
          const rot = entry.rot[i];
          ctx.moveTo(x + rx * Math.cos(rot), y + rx * Math.sin(rot));
          ctx.ellipse(x, y, rx, ry, rot, 0, TAU);
          ellipseDrawCount++;
          return true;
        }

        if (unselectedEllipsesVisible) {
          ctx.lineWidth = (Number(st.ellipse_stroke_width || 1.5) * pixelRatio);
          ctx.strokeStyle = rgba_to_css_with_opacity(
            st.ellipse_stroke_rgba || [255,204,0,180],
            entry.opacity
          );
          const fillEll = !!st.fill_ellipses;
          if (fillEll) {
            ctx.fillStyle = rgba_to_css_with_opacity(
              st.ellipse_fill_rgba || [255,204,0,40],
              entry.opacity
            );
          }
          let nInPath = 0;
          ctx.beginPath();
          for (let k = 0; k < drawIndices.length; k++) {
            if (!addEllipsePath(drawIndices[k], false)) continue;
            nInPath++;
            if (nInPath >= maxPerPath) {
              if (fillEll) ctx.fill();
              ctx.stroke();
              ctx.beginPath();
              nInPath = 0;
            }
          }
          if (nInPath > 0) {
            if (fillEll) ctx.fill();
            ctx.stroke();
          }
        }

        if (selectedEllipsesVisible) {
          ctx.lineWidth = (Number(st.selected_ellipse_stroke_width || (st.ellipse_stroke_width || 1.5) * 1.8) * pixelRatio);
          ctx.strokeStyle = rgba_to_css_with_opacity(
            st.selected_ellipse_stroke_rgba || [0,255,255,255],
            entry.opacity
          );
          let nInPath = 0;
          ctx.beginPath();
          for (const fid of selectedSet) {
            const i = entry.idIndex.get(String(fid));
            if (i == null || entry.deleted[i] || entry.hidden[i] || !inExtent(i)) continue;
            if (!addEllipsePath(i, true)) continue;
            nInPath++;
            if (nInPath >= maxPerPath) {
              ctx.stroke();
              ctx.beginPath();
              nInPath = 0;
            }
          }
          if (nInPath > 0) ctx.stroke();
        }
      }
      const ellipseTime = performance.now() - ellipseStart;

      // ---- Points (batched, quadtree-collapsed for unselected points) ----
      const pointStart = performance.now();
      const batches = new Map();

      function addPointToBatch(i, selectedOverride) {
        const fid = entry.ids[i];
        const selected = selectedOverride === true || selectedSet.has(fid);
        if (!selectedOverride && selected) return;
        const x = (entry.x[i] - extent[0]) * scaleX;
        const y = (extent[3] - entry.y[i]) * scaleY;
        const px = Math.round(x);
        const py = Math.round(y);
        const radius = (selected ? (st.selected_point_radius || 6.0) : (st.point_radius || 3.0)) * pixelRatio;
        let colorKey;
        if (selected) {
          colorKey = rgba_to_css_with_opacity(
            st.selected_point_rgba || [0,255,255,255],
            entry.opacity
          );
        } else {
          const u = entry.color_u32[i];
          colorKey = u !== 0
            ? rgba_to_css_with_opacity(rgba_from_u32(u), entry.opacity)
            : rgba_to_css_with_opacity(
              st.default_point_rgba || [255,51,51,204],
              entry.opacity
            );
        }
        const batchKey = colorKey + '|' + radius;
        let batch = batches.get(batchKey);
        if (!batch) {
          batch = { color: colorKey, radius: radius, points: [] };
          batches.set(batchKey, batch);
        }
        batch.points.push([x, y]);
        pointDrawCount++;
      }

      for (let k = 0; k < drawIndices.length; k++) addPointToBatch(drawIndices[k], false);
      for (const fid of selectedSet) {
        const i = entry.idIndex.get(String(fid));
        if (i == null || entry.deleted[i] || entry.hidden[i] || !inExtent(i)) continue;
        addPointToBatch(i, true);
      }

      for (const batch of batches.values()) {
        ctx.fillStyle = batch.color;
        ctx.beginPath();
        for (let k = 0; k < batch.points.length; k++) {
          const pt = batch.points[k];
          ctx.moveTo(pt[0] + batch.radius, pt[1]);
          ctx.arc(pt[0], pt[1], batch.radius, 0, TAU);
        }
        ctx.fill();
      }
      const pointTime = performance.now() - pointStart;
      const totalTime = performance.now() - perfStart;

      if ((entry.x.length > 100) || window.PYOLQT_RENDER_PERF) {
        emitPerf({
          layer_id: entry.layer_id,
          operation: "fast_geopoints_render",
          point_count: entry.x.length,
          visited_node_count: visitedNodeCount,
          collapsed_node_count: collapsedNodeCount,
          scanned_leaf_point_count: scannedLeafPointCount,
          representative_count: representativeCount,
          quadtree_draw_candidate_count: drawIndices.length,
          collapse_pixel_threshold: collapsePx.toFixed(2),
          ellipse_draw_count: ellipseDrawCount,
          point_draw_count: pointDrawCount,
          skipped_duplicate_pixels: skippedDuplicatePixels,
          batch_count: batches.size,
          ellipses_visible: !!entry.ellipsesVisible,
          selected_ellipses_visible: !!entry.selectedEllipsesVisible,
          times: {
            query_ms: queryTime.toFixed(2),
            ellipse_ms: ellipseTime.toFixed(2),
            point_ms: pointTime.toFixed(2),
            total_ms: totalTime.toFixed(2)
          }
        });
      }

      entry.renderCache = { key: cacheKey, canvas: canvas };
      return canvas;
    },
  });

  const layer = new ol.layer.Image({ source, visible: entry.visible });
  entry.source = source;
  entry.layer = layer;
}

function cmd_fast_geopoints_add_layer(msg) {
  const layer_id = msg.layer_id;
  const style = msg.style || {};
  const entry = {
    type: 'fast_geopoints',
    layer_id,
    name: msg.name || layer_id,
    visible: (msg.visible !== false),
    opacity: (msg.opacity == null ? 1.0 : msg.opacity),
    selectable: (msg.selectable === true),
    ellipsesVisible: (msg.ellipses_visible != null ? !!msg.ellipses_visible : (style.ellipses_visible !== false)),
    selectedEllipsesVisible: (msg.selected_ellipses_visible != null ? !!msg.selected_ellipses_visible : (style.selected_ellipses_visible !== false)),
    x: [],
    y: [],
    ids: [],
    color_u32: [],
    deleted: [],
    hidden: [],
    a: [],
    b: [],
    rot: [],
    grid: new Map(),
    qtRoot: null,
    cellSize: (msg.cell_size_m || 1000.0),
    selectedIds: new Set(),
    idIndex: new Map(),
    style,
    source: null,
    layer: null,
    renderVersion: 0,
    renderCache: null,
  };

  fp_qt_init(entry);
  fgp_make_canvas_layer(entry);
  state.map.addLayer(entry.layer);
  state.layers.set(layer_id, entry);
  state.layerByObj.set(entry.layer, layer_id);
}

function cmd_fast_geopoints_add_points(msg) {
  const perfStart = performance.now();
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  const pointData = pyolqt_points_from_msg(msg);
  const coords = pointData.coords || null;
  const coordsFlat = pointData.flat || null;
  const pointCount = pointData.count;
  const sma_m = msg.sma_m_b64 ? pyolqt_b64_to_float64(msg.sma_m_b64) : (msg.sma_m || []);
  const smi_m = msg.smi_m_b64 ? pyolqt_b64_to_float64(msg.smi_m_b64) : (msg.smi_m || []);
  const tilt_deg = msg.tilt_deg_b64 ? pyolqt_b64_to_float64(msg.tilt_deg_b64) : (msg.tilt_deg || []);
  const ids = msg.ids_b64 ? pyolqt_b64_to_strings(msg.ids_b64) : (msg.ids || null);
  const colors = msg.colors_b64 ? pyolqt_b64_to_uint32(msg.colors_b64) : (msg.colors || null);

  const startIndex = entry.x.length;
  const convertStart = performance.now();
  for (let i = 0; i < pointCount; i++) {
    const lon = coordsFlat ? coordsFlat[i * 2] : coords[i][0];
    const lat = coordsFlat ? coordsFlat[i * 2 + 1] : coords[i][1];
    const p = lonlat_to_3857(lon, lat);
    if (!Number.isFinite(p[0]) || !Number.isFinite(p[1])) continue;
    const idx = entry.x.length;
    entry.x.push(p[0]);
    entry.y.push(p[1]);
    const fid = (ids ? ids[i] : String(idx));
    entry.ids.push(fid);
    entry.idIndex.set(String(fid), idx);
    entry.deleted.push(false);
    entry.hidden.push(false);
    entry.color_u32.push(colors ? (colors[i] >>> 0) : 0);

    // Convert meters to local WebMercator meters using sec(lat)
    const latRad = _fgp_lat_from_y(p[1]);
    const k = _fgp_sec(latRad);
    entry.a.push((Number(sma_m[i] || 0.0)) * k);
    entry.b.push((Number(smi_m[i] || 0.0)) * k);

    // tilt_deg is bearing clockwise from TRUE NORTH.
    // Convert to canvas rotation (radians from +X east): rot = (90 - tilt) deg
    entry.rot.push((90.0 - Number(tilt_deg[i] || 0.0)) * Math.PI / 180.0);

    fp_index_insert(entry, idx);
    fp_qt_insert(entry, idx);
  }
  const convertIndexMs = performance.now() - convertStart;
  const shouldRedraw = (msg.redraw !== false);
  const redrawStart = performance.now();
  if (shouldRedraw) fgp_redraw(entry);
  const redrawMs = performance.now() - redrawStart;
  emitPerf({
    side: "javascript",
    layer_id: entry.layer_id,
    operation: "fast_geopoints_add_points",
    point_count: pointCount,
    start_index: startIndex,
    total_points: entry.x.length,
    times: {
      convert_index_ms: convertIndexMs.toFixed(2),
      redraw_requested: shouldRedraw,
      redraw_request_ms: redrawMs.toFixed(2),
      total_ms: (performance.now() - perfStart).toFixed(2)
    }
  });
}

function cmd_fast_geopoints_redraw(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  fgp_redraw(entry);
}

function cmd_fast_geopoints_clear(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  entry.x = []; entry.y = []; entry.ids = []; entry.color_u32 = []; entry.deleted = []; entry.hidden = [];
  entry.a = []; entry.b = []; entry.rot = [];
  entry.grid = new Map();
  fp_qt_init(entry);
  entry.idIndex = new Map();
  entry.selectedIds = new Set();
  fgp_redraw(entry);
  if (msg.emit !== false) fgp_emit_selection(entry);
}

function cmd_fast_geopoints_remove_ids(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  const raw = pyolqt_ids_from_msg(msg);
  const ids = new Set(raw.map(x => String(x)));
  if (ids.size === 0) return;
  for (const id of ids) {
    const i = entry.idIndex.get(id);
    if (i == null || entry.deleted[i]) continue;
    if (!entry.hidden[i]) fp_qt_update_visibility(entry, i, -1);
    entry.deleted[i] = true;
    entry.selectedIds.delete(entry.ids[i]);
  }
  fgp_redraw(entry);
  fgp_emit_selection(entry);
}

function cmd_fast_geopoints_set_opacity(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  entry.opacity = msg.opacity;
  fgp_redraw(entry);
}

function cmd_fast_geopoints_set_visible(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  entry.visible = !!msg.visible;
  entry.layer.setVisible(entry.visible);
}

function cmd_fast_geopoints_set_selectable(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  entry.selectable = !!msg.selectable;
}

function cmd_fast_geopoints_set_ellipses_visible(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  entry.ellipsesVisible = !!msg.visible;
  fgp_redraw(entry);
}

function cmd_fast_geopoints_set_selected_ellipses_visible(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  entry.selectedEllipsesVisible = !!msg.visible;
  fgp_redraw(entry);
}

function cmd_fast_geopoints_select_set(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  entry.selectedIds = new Set(pyolqt_ids_from_msg(msg));
  fgp_redraw(entry);
  if (msg.emit !== false) fgp_emit_selection(entry);
}

function cmd_fast_geopoints_hide_ids(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  const raw = pyolqt_ids_from_msg(msg);
  const ids = new Set(raw.map(x => String(x)));
  if (ids.size === 0) return;
  for (const id of ids) {
    const i = entry.idIndex.get(id);
    if (i == null || entry.deleted[i] || entry.hidden[i]) continue;
    entry.hidden[i] = true;
    fp_qt_update_visibility(entry, i, -1);
  }
  fgp_redraw(entry);
}

function cmd_fast_geopoints_show_ids(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  const raw = pyolqt_ids_from_msg(msg);
  const ids = new Set(raw.map(x => String(x)));
  if (ids.size === 0) return;
  for (const id of ids) {
    const i = entry.idIndex.get(id);
    if (i == null || entry.deleted[i] || !entry.hidden[i]) continue;
    entry.hidden[i] = false;
    fp_qt_update_visibility(entry, i, 1);
  }
  fgp_redraw(entry);
}

function cmd_fast_geopoints_show_all(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  for (let i = 0; i < entry.hidden.length; i++) {
    if (entry.hidden[i] && !entry.deleted[i]) fp_qt_update_visibility(entry, i, 1);
    entry.hidden[i] = false;
  }
  fgp_redraw(entry);
}

function cmd_fast_geopoints_set_colors(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  const fids = msg.feature_ids_b64 ? pyolqt_b64_to_strings(msg.feature_ids_b64) : (msg.feature_ids || []);
  const colors = msg.colors_b64 ? pyolqt_b64_to_uint32(msg.colors_b64) : (msg.colors || []);
  if (fids.length !== colors.length) return;
  
  // Update colors for the specified features
  for (let k = 0; k < fids.length; k++) {
    const idx = entry.idIndex.get(String(fids[k]));
    if (idx != null) {
      entry.color_u32[idx] = colors[k] >>> 0;
    }
  }
  
  fgp_redraw(entry);
}

function fp_install_interactions() {
  state.map.on("singleclick", function(evt) {
    const orig = evt.originalEvent;
    const mod = orig && (orig.ctrlKey || orig.metaKey);
    const coord = evt.coordinate;
    const ll_coord = p3857_to_lonlat(coord);
    fp_emit_singleclick(
      ll_coord,
      orig.ctrlKey,
      orig.metaKey,
      orig.shiftKey,
      orig.altKey
    );
    if (!mod) return;
    for (const [layer_id, entry] of state.layers.entries()) {
      if ((entry.type !== "fast_points" && entry.type !== "fast_geopoints") || !entry.selectable) continue;
      const perfStart = performance.now();
      const res = state.map.getView().getResolution() || 1.0;
      const radius_m = Math.max(5.0, res * 8.0);
      const pickStart = performance.now();
      const idx = fp_pick_nearest(entry, coord, radius_m);
      const pickMs = performance.now() - pickStart;
      if (idx < 0) continue;
      const fid = entry.ids[idx];
      if (entry.selectedIds.has(fid)) entry.selectedIds.delete(fid);
      else entry.selectedIds.add(fid);
      const redrawStart = performance.now();
      if (entry.type === "fast_geopoints") fgp_redraw(entry);
      else fp_redraw(entry);
      const redrawMs = performance.now() - redrawStart;
      const emitStart = performance.now();
      fp_emit_selection(entry);
      const emitMs = performance.now() - emitStart;
      emitPerf({
        side: "javascript",
        layer_id: entry.layer_id,
        operation: "fast_points_singleclick_selection",
        selection_count: entry.selectedIds.size,
        times: {
          pick_ms: pickMs.toFixed(2),
          redraw_request_ms: redrawMs.toFixed(2),
          emit_ms: emitMs.toFixed(2),
          total_ms: (performance.now() - perfStart).toFixed(2)
        }
      });
      break;
    }
  });

  const dragBox = new ol.interaction.DragBox({
    condition: function(evt) {
      const oe = evt.originalEvent;
      return oe && (oe.ctrlKey || oe.metaKey);
    }
  });
  state.map.addInteraction(dragBox);

  dragBox.on("boxend", function() {
    const perfStart = performance.now();
    const extent = dragBox.getGeometry().getExtent();
    for (const [layer_id, entry] of state.layers.entries()) {
      if ((entry.type !== "fast_points" && entry.type !== "fast_geopoints") || !entry.selectable) continue;
      const queryStart = performance.now();
      const cand = fp_query_extent(entry, extent);
      const queryMs = performance.now() - queryStart;
      const buildStart = performance.now();
      const next = new Set();
      for (let k = 0; k < cand.length; k++) {
        const i = cand[k];
        if (entry.deleted[i]) continue;
        const x = entry.x[i], y = entry.y[i];
        if (x >= extent[0] && x <= extent[2] && y >= extent[1] && y <= extent[3]) next.add(entry.ids[i]);
      }
      const buildMs = performance.now() - buildStart;
      // Only emit selection if something was selected in this layer or if clearing previous selection
      if (next.size > 0 || entry.selectedIds.size > 0) {
        entry.selectedIds = next;
        const redrawStart = performance.now();
        if (entry.type === "fast_geopoints") fgp_redraw(entry);
        else fp_redraw(entry);
        const redrawMs = performance.now() - redrawStart;
        const emitStart = performance.now();
        fp_emit_selection(entry);
        const emitMs = performance.now() - emitStart;
        emitPerf({
          side: "javascript",
          layer_id: entry.layer_id,
          operation: "fast_points_dragbox_selection",
          candidate_count: cand.length,
          selection_count: next.size,
          times: {
            query_ms: queryMs.toFixed(2),
            build_ms: buildMs.toFixed(2),
            redraw_request_ms: redrawMs.toFixed(2),
            emit_ms: emitMs.toFixed(2),
            total_ms: (performance.now() - perfStart).toFixed(2)
          }
        });
      }
    }
  });
}
function lonlat_to_3857(lon, lat) { return ol.proj.fromLonLat([lon, lat]); }
function p3857_to_lonlat(coord) { return ol.proj.toLonLat(coord); }

function _pick_context_feature(pixel) {
  const st = window._pyolqt_state;
  if (!st || !st.map) return null;
  let picked = null;
  st.map.forEachFeatureAtPixel(pixel, function(feature, layer) {
    if (picked) return picked;
    if (!feature) return null;
    const layer_id = feature.get('_layer_id') || st.layerByObj.get(layer) || null;
    const feature_id = feature.getId();
    if (!layer_id || feature_id == null) return null;
    picked = {
      layer_id: String(layer_id),
      feature_id: String(feature_id),
    };
    return feature;
  });
  return picked;
}

function _install_context_menu_bridge() {
  const st = window._pyolqt_state;
  if (!st || !st.map || st.contextMenuInstalled) return;
  const viewport = st.map.getViewport();
  if (!viewport) return;
  viewport.addEventListener('contextmenu', function(evt) {
    evt.preventDefault();
    const pixel = st.map.getEventPixel(evt);
    const coord = st.map.getCoordinateFromPixel(pixel);
    const lonlat = p3857_to_lonlat(coord);
    const picked = _pick_context_feature(pixel) || {};
    emitToPython('contextmenu', {
      lon: lonlat[0],
      lat: lonlat[1],
      client_x: evt.clientX,
      client_y: evt.clientY,
      layer_id: picked.layer_id || null,
      feature_id: picked.feature_id || null,
    });
  });
  st.contextMenuInstalled = true;
}

// ---- Measurement Mode Functions ----

// Calculate geodesic distance using Haversine formula
function geodesicDistance(lon1, lat1, lon2, lat2) {
  const R = 6371000; // Earth's radius in meters
  const phi1 = lat1 * Math.PI / 180;
  const phi2 = lat2 * Math.PI / 180;
  const deltaPhi = (lat2 - lat1) * Math.PI / 180;
  const deltaLambda = (lon2 - lon1) * Math.PI / 180;

  const a = Math.sin(deltaPhi / 2) * Math.sin(deltaPhi / 2) +
            Math.cos(phi1) * Math.cos(phi2) *
            Math.sin(deltaLambda / 2) * Math.sin(deltaLambda / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return R * c; // Distance in meters
}

// Generate intermediate points along a great-circle path
// Returns array of [lon, lat] coordinates including start and end points
function interpolateGeodesicLine(lon1, lat1, lon2, lat2, numSegments = null) {
  // Segment distance threshold for determining number of interpolation segments
  const SEGMENT_DISTANCE_METERS = 100000; // 100 km
  
  // Calculate distance to determine number of segments if not provided
  const distance = geodesicDistance(lon1, lat1, lon2, lat2);
  
  // Handle very short distances - just return start and end points
  if (distance < 1.0) {
    return [[lon1, lat1], [lon2, lat2]];
  }
  
  // Use one segment per ~100km for smooth curves, minimum 1, maximum 100
  if (numSegments === null) {
    numSegments = Math.max(1, Math.min(100, Math.floor(distance / SEGMENT_DISTANCE_METERS)));
  }
  
  const points = [];
  
  // Convert to radians
  const lat1Rad = lat1 * Math.PI / 180;
  const lon1Rad = lon1 * Math.PI / 180;
  const lat2Rad = lat2 * Math.PI / 180;
  const lon2Rad = lon2 * Math.PI / 180;
  
  // Calculate angular distance
  const d = distance / 6371000; // Angular distance in radians
  
  // Handle very small angular distances - just return start and end points
  // This prevents division by zero in slerp calculation
  if (d < 1e-10) {
    return [[lon1, lat1], [lon2, lat2]];
  }
  
  for (let i = 0; i <= numSegments; i++) {
    const f = i / numSegments;
    
    // Spherical linear interpolation (slerp)
    const a = Math.sin((1 - f) * d) / Math.sin(d);
    const b = Math.sin(f * d) / Math.sin(d);
    
    const x = a * Math.cos(lat1Rad) * Math.cos(lon1Rad) + b * Math.cos(lat2Rad) * Math.cos(lon2Rad);
    const y = a * Math.cos(lat1Rad) * Math.sin(lon1Rad) + b * Math.cos(lat2Rad) * Math.sin(lon2Rad);
    const z = a * Math.sin(lat1Rad) + b * Math.sin(lat2Rad);
    
    const latRad = Math.atan2(z, Math.sqrt(x * x + y * y));
    const lonRad = Math.atan2(y, x);
    
    points.push([lonRad * 180 / Math.PI, latRad * 180 / Math.PI]);
  }
  
  return points;
}

// Format distance for display
function formatDistance(meters) {
  if (meters < 1000) {
    return meters.toFixed(1) + ' m';
  } else if (meters < 100000) {
    return (meters / 1000).toFixed(2) + ' km';
  } else {
    return (meters / 1000).toFixed(0) + ' km';
  }
}

function initMeasurementLayer() {
  if (state.measureSource) return; // Already initialized
  
  state.measureSource = new ol.source.Vector();
  state.measureLayer = new ol.layer.Vector({
    source: state.measureSource,
    style: new ol.style.Style({
      stroke: new ol.style.Stroke({
        color: 'rgba(255, 0, 0, 0.8)',
        width: 2,
        lineDash: [10, 5]
      }),
      fill: new ol.style.Fill({
        color: 'rgba(255, 0, 0, 0.1)'
      }),
      image: new ol.style.Circle({
        radius: 5,
        fill: new ol.style.Fill({
          color: 'rgba(255, 0, 0, 0.8)'
        }),
        stroke: new ol.style.Stroke({
          color: 'rgba(255, 255, 255, 0.8)',
          width: 2
        })
      })
    }),
    zIndex: 1000 // Ensure measurement layer is on top
  });
  
  if (state.map) {
    state.map.addLayer(state.measureLayer);
  }
  
  // Create tooltip overlay
  const tooltipElement = document.createElement('div');
  tooltipElement.className = 'ol-tooltip ol-tooltip-measure';
  tooltipElement.style.cssText = 'position: absolute; background-color: rgba(0, 0, 0, 0.7); color: white; padding: 6px 10px; border-radius: 4px; font-size: 12px; white-space: nowrap; pointer-events: none;';
  
  state.measureOverlay = new ol.Overlay({
    element: tooltipElement,
    offset: [0, -15],
    positioning: 'bottom-center',
    stopEvent: false
  });
  
  if (state.map) {
    state.map.addOverlay(state.measureOverlay);
  }
}

function updateMeasurementTooltip(coord3857, segmentDistance, cumulativeDistance) {
  if (!state.measureOverlay) return;
  
  const element = state.measureOverlay.getElement();
  if (!element) return;
  
  let html = '';
  if (segmentDistance !== null) {
    html += '<div>Segment: ' + formatDistance(segmentDistance) + '</div>';
  }
  if (cumulativeDistance !== null) {
    html += '<div>Total: ' + formatDistance(cumulativeDistance) + '</div>';
  }
  
  element.innerHTML = html;
  state.measureOverlay.setPosition(coord3857);
}

function calculateMeasurementDistances(mouseCoord) {
  if (state.measurePoints.length === 0) {
    return { segment: null, cumulative: null };
  }
  
  const lastPoint = state.measurePoints[state.measurePoints.length - 1];
  const segmentDistance = geodesicDistance(
    lastPoint[0], lastPoint[1],
    mouseCoord[0], mouseCoord[1]
  );
  
  let cumulativeDistance = 0;
  for (let i = 0; i < state.measurePoints.length - 1; i++) {
    cumulativeDistance += geodesicDistance(
      state.measurePoints[i][0], state.measurePoints[i][1],
      state.measurePoints[i + 1][0], state.measurePoints[i + 1][1]
    );
  }
  cumulativeDistance += segmentDistance;
  
  return { segment: segmentDistance, cumulative: cumulativeDistance };
}

function updateMeasurementGeometry(mouseCoord3857) {
  if (!state.measureSource) return;

  // Clear previous temp geometry without scanning all features.
  if (state.measureTempFeature) {
    state.measureSource.removeFeature(state.measureTempFeature);
    state.measureTempFeature = null;
  }
  
  if (state.measurePoints.length === 0) return;
  
  // Draw great-circle line from last point to mouse cursor
  const lastPoint = state.measurePoints[state.measurePoints.length - 1];
  const mouseCoord = ol.proj.toLonLat(mouseCoord3857);
  
  // Generate intermediate points along the great-circle path
  const geodesicPoints = interpolateGeodesicLine(
    lastPoint[0], lastPoint[1],
    mouseCoord[0], mouseCoord[1]
  );
  
  // Convert all points to Web Mercator projection
  const coords3857 = geodesicPoints.map(pt => lonlat_to_3857(pt[0], pt[1]));
  
  const lineFeature = new ol.Feature({
    geometry: new ol.geom.LineString(coords3857),
    _temp: true
  });

  state.measureTempFeature = lineFeature;
  state.measureSource.addFeature(lineFeature);
}

function onMeasurementPointerMove(evt) {
  if (!state.measureMode) return;
  
  const coord3857 = evt.coordinate;
  const coord = ol.proj.toLonLat(coord3857);
  
  updateMeasurementGeometry(coord3857);
  
  const distances = calculateMeasurementDistances(coord);
  updateMeasurementTooltip(coord3857, distances.segment, distances.cumulative);
}

function onMeasurementClick(evt) {
  if (!state.measureMode) return;
  
  const coord3857 = evt.coordinate;
  const coord = ol.proj.toLonLat(coord3857); // [lon, lat]
  
  // Add point marker
  const pointFeature = new ol.Feature({
    geometry: new ol.geom.Point(coord3857),
    _permanent: true
  });
  state.measureSource.addFeature(pointFeature);
  
  // Calculate distances
  let segmentDistance = null;
  let cumulativeDistance = 0;
  
  if (state.measurePoints.length > 0) {
    const lastPoint = state.measurePoints[state.measurePoints.length - 1];
    segmentDistance = geodesicDistance(
      lastPoint[0], lastPoint[1],
      coord[0], coord[1]
    );
    
    // Calculate cumulative distance
    for (let i = 0; i < state.measurePoints.length - 1; i++) {
      cumulativeDistance += geodesicDistance(
        state.measurePoints[i][0], state.measurePoints[i][1],
        state.measurePoints[i + 1][0], state.measurePoints[i + 1][1]
      );
    }
    cumulativeDistance += segmentDistance;
    
    // Draw permanent great-circle line from previous point to new point
    const geodesicPoints = interpolateGeodesicLine(
      lastPoint[0], lastPoint[1],
      coord[0], coord[1]
    );
    
    // Convert all points to Web Mercator projection
    const coords3857 = geodesicPoints.map(pt => lonlat_to_3857(pt[0], pt[1]));
    
    const lineFeature = new ol.Feature({
      geometry: new ol.geom.LineString(coords3857),
      _permanent: true
    });
    state.measureSource.addFeature(lineFeature);
  }
  
  // Add point to measurement
  state.measurePoints.push(coord);
  
  // Emit event to Python
  emitToPython('measurement', {
    segment_distance_m: segmentDistance,
    cumulative_distance_m: cumulativeDistance,
    lon: coord[0],
    lat: coord[1],
    point_index: state.measurePoints.length - 1
  });
}

function onMeasurementKeyDown(evt) {
  if (!state.measureMode) return;
  
  // Exit measurement mode on Escape key
  if (evt.key === 'Escape' || evt.keyCode === 27) {
    setMeasureMode(false);
    evt.preventDefault();
  }
}

function setMeasureMode(enabled) {
  if (!state.map) return;
  
  // Initialize measurement layer if needed
  if (enabled && !state.measureSource) {
    initMeasurementLayer();
  }
  
  state.measureMode = enabled;
  
  if (enabled) {
    // Reset measurement state
    state.measurePoints = [];
    state.measureTempFeature = null;
    
    // Hide tooltip initially
    if (state.measureOverlay) {
      state.measureOverlay.setPosition(undefined);
    }
    
    // Add event listeners
    state.measurePointerMoveKey = state.map.on('pointermove', onMeasurementPointerMove);
    state.measureClickKey = state.map.on('singleclick', onMeasurementClick);
    // For keydown, just set a flag since addEventListener returns undefined
    document.addEventListener('keydown', onMeasurementKeyDown);
    state.measureKeyDownKey = true; // Flag to track if listener is active
    
    // Disable selection interactions while measuring
    if (state.selectInteraction) {
      state.selectInteraction.setActive(false);
    }
    if (state.dragBox) {
      state.dragBox.setActive(false);
    }
    
    // Change cursor
    if (state.map.getTargetElement()) {
      state.map.getTargetElement().style.cursor = 'crosshair';
    }
  } else {
    // Remove event listeners
    if (state.measurePointerMoveKey) {
      ol.Observable.unByKey(state.measurePointerMoveKey);
      state.measurePointerMoveKey = null;
    }
    if (state.measureClickKey) {
      ol.Observable.unByKey(state.measureClickKey);
      state.measureClickKey = null;
    }
    if (state.measureKeyDownKey) {
      document.removeEventListener('keydown', onMeasurementKeyDown);
      state.measureKeyDownKey = null;
    }
    
    // Re-enable selection interactions
    if (state.selectInteraction) {
      state.selectInteraction.setActive(true);
    }
    if (state.dragBox) {
      state.dragBox.setActive(true);
    }
    
    // Reset cursor
    if (state.map.getTargetElement()) {
      state.map.getTargetElement().style.cursor = '';
    }
    
    // Hide tooltip
    if (state.measureOverlay) {
      state.measureOverlay.setPosition(undefined);
    }
    
    // Remove temp feature
    if (state.measureSource && state.measureTempFeature) {
      state.measureSource.removeFeature(state.measureTempFeature);
      state.measureTempFeature = null;
    }
  }
}

function clearMeasurements() {
  state.measurePoints = [];
  state.measureTempFeature = null;
  
  if (state.measureSource) {
    state.measureSource.clear();
  }
  
  if (state.measureOverlay) {
    state.measureOverlay.setPosition(undefined);
  }
}

function cmd_measure_set_mode(msg) {
  setMeasureMode(!!msg.enabled);
}

function cmd_measure_clear(msg) {
  clearMeasurements();
}

// ---- End Measurement Mode Functions ----


  function extent_from_bounds(boundsLonLat) {
    const a = boundsLonLat[0], b = boundsLonLat[1];
    const minLon = Math.min(a[0], b[0]);
    const minLat = Math.min(a[1], b[1]);
    const maxLon = Math.max(a[0], b[0]);
    const maxLat = Math.max(a[1], b[1]);
    const bl = lonlat_to_3857(minLon, minLat);
    const tr = lonlat_to_3857(maxLon, maxLat);
    return [bl[0], bl[1], tr[0], tr[1]];
  }

  const VECTOR_SELECTION_RGBA = [0, 255, 255, 255];
  const VECTOR_SELECTION_CSS = rgba_to_css(VECTOR_SELECTION_RGBA);

  function can_tint_icon_src(src, crossOrigin) {
    const lowerSrc = String(src).toLowerCase();
    if (crossOrigin != null) return true;
    if (lowerSrc.startsWith("data:") || lowerSrc.startsWith("blob:")) return true;
    try {
      return new URL(src, window.location.href).origin === window.location.origin;
    } catch (e) {
      return false;
    }
  }

  function style_from_simple(s, selected) {
    selected = !!selected;
    if (typeof s.icon_src === "string" && s.icon_src.length > 0) {
      const baseScale = (typeof s.scale === "number" ? s.scale : 1.0);
      const selectedIconSrc = (
        typeof s.selected_icon_src === "string" && s.selected_icon_src.length > 0
      ) ? s.selected_icon_src : null;
      const iconSrc = (selected && selectedIconSrc) ? selectedIconSrc : s.icon_src;
      const crossOrigin = s.cross_origin;
      const hasSelectedIcon = selected && !!selectedIconSrc;
      const canTint = selected && !hasSelectedIcon && can_tint_icon_src(iconSrc, crossOrigin);
      const iconOptions = {
        src: iconSrc,
        scale: selected ? baseScale * 1.15 : baseScale,
        opacity: (typeof s.opacity === "number" ? s.opacity : 1.0),
        anchor: (Array.isArray(s.anchor) && s.anchor.length === 2)
          ? s.anchor
          : [0.5, 1.0],
        anchorXUnits: s.anchor_x_units || "fraction",
        anchorYUnits: s.anchor_y_units || "fraction",
        rotation: (typeof s.rotation_deg === "number"
          ? s.rotation_deg * Math.PI / 180.0
          : 0.0),
        rotateWithView: !!s.rotate_with_view,
      };
      if (canTint) iconOptions.color = VECTOR_SELECTION_CSS;
      if (crossOrigin != null) iconOptions.crossOrigin = crossOrigin;
      const iconStyle = new ol.style.Style({
        image: new ol.style.Icon(iconOptions),
      });
      if (!selected || canTint) return iconStyle;
      const haloRadius = Math.max(8, 12 * Math.max(1, baseScale));
      return [
        new ol.style.Style({
          image: new ol.style.Circle({
            radius: haloRadius,
            fill: new ol.style.Fill({ color: "rgba(0,255,255,0.35)" }),
            stroke: new ol.style.Stroke({ color: VECTOR_SELECTION_CSS, width: 2 }),
          }),
        }),
        iconStyle,
      ];
    }

    const stroke = new ol.style.Stroke({
      color: selected ? VECTOR_SELECTION_CSS : (s.stroke || "rgba(0,0,0,1)"),
      width: selected
        ? Math.max(2, (s.stroke_width || 1) + 1)
        : (s.stroke_width || 1),
    });
    const fill = new ol.style.Fill({
      color: selected ? "rgba(0,255,255,0.35)" : (s.fill || "rgba(0,0,0,0)"),
    });

    if (typeof s.radius === "number") {
      return new ol.style.Style({
        image: new ol.style.Circle({
          radius: selected ? s.radius + 2 : s.radius,
          fill,
          stroke,
        }),
      });
    }
    return new ol.style.Style({ stroke, fill });
  }

  function selected_style_for_feature(feature) {
    const styleSpec = feature && feature.get ? feature.get("_pyolqt_style") : null;
    if (styleSpec) return style_from_simple(styleSpec, true);
    return style_from_simple({}, true);
  }

  function circle_polygon_lonlat(centerLonLat, radius_m, segments) {
    const center = lonlat_to_3857(centerLonLat[0], centerLonLat[1]);
    const coords = [];
    const n = Math.max(12, segments | 0);
    for (let i = 0; i <= n; i++) {
      const t = (i / n) * 2 * Math.PI;
      coords.push([center[0] + radius_m * Math.cos(t), center[1] + radius_m * Math.sin(t)]);
    }
    return new ol.geom.Polygon([coords]);
  }
 function ellipse_polygon_lonlat(centerLonLat, sma_m, smi_m, tilt_deg, segments) {
   const center = lonlat_to_3857(centerLonLat[0], centerLonLat[1]);
   // tilt_deg is bearing clockwise from TRUE NORTH.
   // Convert to math angle from +X (EAST):
   const tilt = (90.0 - (tilt_deg || 0)) * Math.PI / 180.0;
   const n = Math.max(24, segments | 0);
   const coords = [];
   const c = Math.cos(tilt), s = Math.sin(tilt);
   for (let i = 0; i <= n; i++) {
     const t = (i / n) * 2 * Math.PI;
     const ex = sma_m * Math.cos(t);
     const ey = smi_m * Math.sin(t);
     const rx = ex * c - ey * s;
     const ry = ex * s + ey * c;
     coords.push([center[0] + rx, center[1] + ry]);
   }
   return new ol.geom.Polygon([coords]);
 }


// ---- Coordinate Display ----
function initCoordinateDisplay() {
  if (state.coordinateOverlay) return; // Already initialized
  
  // Create coordinate overlay element
  const coordElement = document.createElement('div');
  coordElement.className = 'ol-coordinate-display';
  coordElement.style.cssText = 
    'position: absolute; ' +
    'bottom: 8px; ' +
    'right: 8px; ' +
    'background-color: rgba(255, 255, 255, 0.9); ' +
    'color: #333; ' +
    'padding: 6px 10px; ' +
    'border-radius: 4px; ' +
    'font-size: 12px; ' +
    'font-family: monospace; ' +
    'white-space: nowrap; ' +
    'pointer-events: none; ' +
    'box-shadow: 0 1px 4px rgba(0,0,0,0.3); ' +
    'z-index: 1000; ' +
    'display: none; ' +
    'min-width: 270px; ' +
    'box-sizing: border-box;';
  
  state.coordinateOverlay = coordElement;
  
  if (state.map) {
    state.map.getTargetElement().appendChild(coordElement);
  }
}

function updateCoordinateDisplay(pixel) {
  if (!state.coordinateOverlay || !state.map) return;
  
  const coord3857 = state.map.getCoordinateFromPixel(pixel);
  if (!coord3857) {
    state.coordinateOverlay.style.display = 'none';
    return;
  }
  
  const lonlat = ol.proj.toLonLat(coord3857);
  const lon = lonlat[0].toFixed(6);
  const lat = lonlat[1].toFixed(6);
  
  state.coordinateOverlay.textContent = 'Lat: ' + lat + ', Lon: ' + lon;
  state.coordinateOverlay.style.display = 'block';
}

function setCoordinateDisplayVisible(visible) {
  initCoordinateDisplay(); // Ensure it's initialized
  
  if (!state.map || !state.coordinateOverlay) return;
  
  if (visible) {
    // Add pointer move listener with throttling for better performance
    if (!state.coordinatePointerMoveKey) {
      let lastUpdate = 0;
      const throttleMs = 50; // Update at most every 50ms (20fps)
      
      state.coordinatePointerMoveKey = state.map.on('pointermove', function(evt) {
        const now = Date.now();
        if (now - lastUpdate >= throttleMs) {
          lastUpdate = now;
          updateCoordinateDisplay(evt.pixel);
        }
      });
    }
  } else {
    // Remove pointer move listener
    if (state.coordinatePointerMoveKey) {
      ol.Observable.unByKey(state.coordinatePointerMoveKey);
      state.coordinatePointerMoveKey = null;
    }
    // Hide the overlay
    if (state.coordinateOverlay) {
      state.coordinateOverlay.style.display = 'none';
    }
  }
}

function cmd_coordinates_set_visible(msg) {
  setCoordinateDisplayVisible(!!msg.visible);
}

function countryBoundariesStyle(strokeColorOverride) {
  const strokeColor = strokeColorOverride || '#334155';
  const strokeWidth = 1.0;
  return new ol.style.Style({
    fill: new ol.style.Fill({ color: 'rgba(0, 0, 0, 0.0)' }),
    stroke: new ol.style.Stroke({ color: strokeColor, width: strokeWidth }),
  });
}

function createCountryBoundariesLayer() {
  if (state.countryBoundariesLayer) return state.countryBoundariesLayer;

  const source = new ol.source.Vector();
  const layer = new ol.layer.Vector({
    source,
    visible: false,
    style: countryBoundariesStyle(state.countryBoundariesStrokeColor),
  });
  layer.set('id', '_country_boundaries');
  layer.setZIndex(50);
  state.countryBoundariesLayer = layer;
  return layer;
}

function hydrologyStyle(feature) {
  const featureClass = (feature.get('featurecla') || '').toLowerCase();
  const geometry = feature.getGeometry();
  const geometryType = geometry ? geometry.getType() : '';
  const isRiver = featureClass.includes('river');
  const isPolygon = geometryType === 'Polygon' || geometryType === 'MultiPolygon';

  if (isRiver) {
    return new ol.style.Style({
      stroke: new ol.style.Stroke({ color: '#1d4ed8', width: 1.5 }),
    });
  }

  if (isPolygon) {
    return new ol.style.Style({
      fill: new ol.style.Fill({ color: 'rgba(59, 130, 246, 0.35)' }),
      stroke: new ol.style.Stroke({ color: '#2563eb', width: 1.0 }),
    });
  }

  return new ol.style.Style({
    stroke: new ol.style.Stroke({ color: '#2563eb', width: 2.5 }),
  });
}

function createHydrologyLayer() {
  if (state.hydrologyLayer) return state.hydrologyLayer;

  const source = new ol.source.Vector();
  const layer = new ol.layer.Vector({
    source,
    visible: false,
    style: hydrologyStyle,
  });
  layer.set('id', '_hydrology');
  layer.setZIndex(51);
  state.hydrologyLayer = layer;
  return layer;
}

async function fetchGeoJSONText(resourceName) {
  const gzResp = await fetch(`/resources/${resourceName}.geojson.gz`);
  if (!gzResp.ok) {
    throw new Error(resourceName + '.geojson.gz not available');
  }

  if (typeof DecompressionStream !== 'undefined' && gzResp.body) {
    const stream = gzResp.body.pipeThrough(new DecompressionStream('gzip'));
    return await new Response(stream).text();
  }

  const fallbackResp = await fetch(`/resources/${resourceName}.geojson`);
  if (!fallbackResp.ok) {
    throw new Error(resourceName + '.geojson fallback not available');
  }
  return await fallbackResp.text();
}

function setCountryBoundariesVisible(visible) {
  if (!state.map) return;

  const countryLayer = createCountryBoundariesLayer();
  const hydrologyLayer = createHydrologyLayer();
  countryLayer.setVisible(!!visible);
  hydrologyLayer.setVisible(!!visible);

  if (!visible) return;

  if (!state.countryBoundariesLoaded && !state.countryBoundariesLoadPromise) {
    state.countryBoundariesLoadPromise = fetchGeoJSONText('countries')
      .then((geojsonText) => {
        const geojson = JSON.parse(geojsonText);
        const fmt = new ol.format.GeoJSON();
        const features = fmt.readFeatures(geojson, {
          featureProjection: 'EPSG:3857',
        });

        countryLayer.getSource().clear(true);
        countryLayer.getSource().addFeatures(features);
        state.countryBoundariesLoaded = true;
        log('countries layer loaded (' + features.length + ' features)');
      })
      .catch((err) => {
        console.warn('[pyopenlayersqt]', 'unable to load country boundaries', err);
      })
      .finally(() => {
        state.countryBoundariesLoadPromise = null;
      });
  }

  if (!state.hydrologyLoaded && !state.hydrologyLoadPromise) {
    state.hydrologyLoadPromise = fetchGeoJSONText('lakes')
      .then((geojsonText) => {
        const geojson = JSON.parse(geojsonText);
        const fmt = new ol.format.GeoJSON();
        const features = fmt.readFeatures(geojson, {
          featureProjection: 'EPSG:3857',
        });

        hydrologyLayer.getSource().clear(true);
        hydrologyLayer.getSource().addFeatures(features);
        state.hydrologyLoaded = true;
        log('hydrology layer loaded (' + features.length + ' features)');
      })
      .catch((err) => {
        console.warn('[pyopenlayersqt]', 'unable to load hydrology data', err);
      })
      .finally(() => {
        state.hydrologyLoadPromise = null;
      });
  }
}
function cmd_countries_set_visible(msg) {
  if (Object.prototype.hasOwnProperty.call(msg, 'stroke_color')) {
    state.countryBoundariesStrokeColor = msg.stroke_color || null;
    const layer = createCountryBoundariesLayer();
    layer.setStyle(countryBoundariesStyle(state.countryBoundariesStrokeColor));
  }
  setCountryBoundariesVisible(!!msg.visible);
}




  function initMap() {
    if (state.map) {
      emitReadyIfNeeded();
      return;
    }

    // Disable tile transition for better pan/zoom performance
    const countryBoundaries = createCountryBoundariesLayer();
    const hydrology = createHydrologyLayer();
    const osmUrl = parseOsmUrlOverride();
    const baseSource = osmUrl
      ? new ol.source.OSM({ transition: 0, url: osmUrl })
      : new ol.source.OSM({ transition: 0 });
    const base = new ol.layer.Tile({ source: baseSource });


    state.base_layer = base;
    base.setZIndex(0);

    state.map = new ol.Map({
      target: "map",
      layers: [countryBoundaries, hydrology, base],
      view: new ol.View({
        center: lonlat_to_3857(0, 0),
        zoom: 2,
      }),
    });


    // Select: Ctrl/Cmd toggles; plain click replaces.
    state.selectInteraction = new ol.interaction.Select({
      condition: (evt) => ol.events.condition.singleClick(evt),
      toggleCondition: (evt) => ol.events.condition.platformModifierKeyOnly(evt),
      multi: true,
      style: selected_style_for_feature,
      layers: (layer) => {
        const layer_id = state.layerByObj.get(layer);
        if (!layer_id) return false;
        const e = state.layers.get(layer_id);
        return !!(e && e.type === "vector" && e.selectable);
      },
    });
    state.map.addInteraction(state.selectInteraction);

    state.selectInteraction.on("select", function () {
      const features = state.selectInteraction.getFeatures().getArray();
      const outByLayer = new Map();
      for (const f of features) {
        const layer_id = f.get("_layer_id") || "";
        const fid = vector_logical_feature_id(f);
        if (!layer_id || !fid) continue;
        if (!outByLayer.has(layer_id)) outByLayer.set(layer_id, []);
        outByLayer.get(layer_id).push(String(fid));
      }
      for (const [layer_id, feature_ids] of outByLayer.entries()) {
        const logical = Array.from(new Set(feature_ids));
        emitToPython("selection", { layer_id, feature_ids: logical, count: logical.length });
      }
    });

    // DragBox: Ctrl/Cmd + drag selects intersecting features.
    state.dragBox = new ol.interaction.DragBox({
      condition: (evt) => ol.events.condition.platformModifierKeyOnly(evt) && ol.events.condition.primaryAction(evt),
    });
    state.map.addInteraction(state.dragBox);

    state.dragBox.on("boxend", function () {
      const extent = state.dragBox.getGeometry().getExtent();
      const selected = state.selectInteraction.getFeatures();
      for (const [layer_id, entry] of state.layers.entries()) {
        if (entry.type !== "vector" || !entry.selectable) continue;
        entry.source.forEachFeatureIntersectingExtent(extent, function (feature) {
          if (selected.getArray().indexOf(feature) === -1) selected.push(feature);
        });
      }
      // trigger emission
      const features = state.selectInteraction.getFeatures().getArray();
      const outByLayer = new Map();
      for (const f of features) {
        const lid = f.get("_layer_id") || "";
        const fid = vector_logical_feature_id(f);
        if (!lid || !fid) continue;
        if (!outByLayer.has(lid)) outByLayer.set(lid, []);
        outByLayer.get(lid).push(String(fid));
      }
      for (const [lid, fids] of outByLayer.entries()) {
        const logical = Array.from(new Set(fids));
        emitToPython("selection", { layer_id: lid, feature_ids: logical, count: logical.length });
      }
    });

    log("OpenLayers map initialized");
    state.viewInteracting = false;
    state.interactionStartTime = null;
    state.renderCount = 0;
    
    state.map.on("movestart", function(){ 
      state.viewInteracting = true; 
      state.interactionStartTime = performance.now();
      state.renderCount = 0;
    });
    
    state.map.on("moveend", function(){ 
      const interactionTime = performance.now() - state.interactionStartTime;
      
      emitPerf({
        operation: "map_interaction",
        interaction_time_ms: interactionTime.toFixed(2),
        render_calls: state.renderCount,
        avg_render_ms: state.renderCount > 0 ? (interactionTime / state.renderCount).toFixed(2) : 0
      });
      
      state.viewInteracting = false;
      // Redraw FastGeoPoints ellipses after interaction settles. During movement,
      // the render path skips ellipses for responsiveness; debouncing avoids
      // immediately starting an expensive ellipse redraw if another pan/zoom begins.
      if (state.fastGeoPointsIdleRedrawTimer) {
        clearTimeout(state.fastGeoPointsIdleRedrawTimer);
      }
      state.fastGeoPointsIdleRedrawTimer = setTimeout(function() {
        state.fastGeoPointsIdleRedrawTimer = null;
        if (state.viewInteracting) return;
        for (const [lid, e] of state.layers.entries()) {
          if (e.type === 'fast_geopoints' && e.ellipsesVisible) fgp_redraw(e);
        }
      }, 120);
    });
    fp_install_interactions();
    _install_context_menu_bridge();
    emitReadyIfNeeded();
  }

  function getLayerEntry(layer_id) {
    const e = state.layers.get(layer_id);
    if (!e) throw new Error("Unknown layer_id: " + layer_id);
    return e;
  }

  function cmd_add_vector(msg) {
    const source = new ol.source.Vector();
    const layer = new ol.layer.Vector({ source });
    layer.setOpacity(1.0);
    state.map.addLayer(layer);
    state.layers.set(msg.layer_id, { type: "vector", layer, source, selectable: !!msg.selectable });
    state.layerByObj.set(layer, msg.layer_id);
  }

  function cmd_add_wms(msg) {
    const wms = msg.wms || {};
    const source = new ol.source.TileWMS({ url: wms.url, params: wms.params || {}, transition: 0 });
    const layer = new ol.layer.Tile({ source });
    layer.setOpacity(typeof wms.opacity === "number" ? wms.opacity : 1.0);
    state.map.addLayer(layer);
    state.layers.set(msg.layer_id, { type: "wms", layer, source, selectable: false });
    state.layerByObj.set(layer, msg.layer_id);
  }

  function _make_tile_source(tile) {
    const attrs = [];
    if (tile && tile.attribution) attrs.push(String(tile.attribution));
    if (tile && tile.url) {
      return new ol.source.XYZ({ url: String(tile.url), attributions: attrs, transition: 0 });
    }
    return new ol.source.OSM({ attributions: attrs, transition: 0 });
  }

  function cmd_add_tile(msg) {
    const tile = msg.tile || {};
    const source = _make_tile_source(tile);
    const layer = new ol.layer.Tile({ source });
    layer.setOpacity(typeof tile.opacity === "number" ? tile.opacity : 1.0);
    state.map.addLayer(layer);
    state.layers.set(msg.layer_id, {
      type: "tile",
      layer,
      source,
      selectable: false,
      attribution: tile.attribution || null,
    });
    state.layerByObj.set(layer, msg.layer_id);
  }

  function cmd_add_raster(msg) {
    const extent = extent_from_bounds(msg.bounds);
    const source = new ol.source.ImageStatic({
      url: msg.url,
      imageExtent: extent,
      projection: state.map.getView().getProjection(),
    });
    const layer = new ol.layer.Image({ source });
    const op = msg.style && typeof msg.style.opacity === "number" ? msg.style.opacity : 0.6;
    layer.setOpacity(op);
    state.map.addLayer(layer);
    state.layers.set(msg.layer_id, { type: "raster", layer, source, selectable: false });
    state.layerByObj.set(layer, msg.layer_id);
  }

  function cmd_layer_remove(msg) {
    const e = state.layers.get(msg.layer_id);
    if (!e) return;
    state.map.removeLayer(e.layer);
    state.layerByObj.delete(e.layer);
    state.layers.delete(msg.layer_id);
  }

  function cmd_layer_opacity(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (typeof msg.opacity === "number") e.layer.setOpacity(msg.opacity);
  }

  function cmd_map_base_opacity(msg) {
    if (!state.base_layer) return;
    const op = Number(msg.opacity);
    if (Number.isFinite(op)) state.base_layer.setOpacity(op);
  }

  function cmd_vector_clear(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "vector") return;
    e.source.clear();
    if (state.selectInteraction) state.selectInteraction.getFeatures().clear();
  }

  function cmd_wms_set_opacity(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "wms") return;
    if (typeof msg.opacity === "number") e.layer.setOpacity(msg.opacity);
  }

  function cmd_wms_set_visible(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "wms") return;
    e.layer.setVisible(!!msg.visible);
  }

  function cmd_tile_set_url(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "tile") return;
    const old = e.layer.getOpacity();
    const attribution = (msg.attribution != null) ? msg.attribution : e.attribution;
    const src = _make_tile_source({ url: msg.url, attribution });
    e.layer.setSource(src);
    e.layer.setOpacity(old);
    e.source = src;
    e.attribution = attribution;
  }

  function cmd_tile_set_opacity(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "tile") return;
    if (typeof msg.opacity === "number") e.layer.setOpacity(msg.opacity);
  }

  function cmd_tile_set_visible(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "tile") return;
    e.layer.setVisible(!!msg.visible);
  }

  function cmd_vector_add_points(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "vector") return;
    const style = style_from_simple(msg.style || {});
    const coords = msg.coords || [];
    const ids = msg.ids || [];
    const props = msg.properties || [];
    for (let i = 0; i < coords.length; i++) {
      const lon = coords[i][0], lat = coords[i][1];
      const f = new ol.Feature({ geometry: new ol.geom.Point(lonlat_to_3857(lon, lat)) });
      f.setId(ids[i] || ("pt" + i));
      f.set("_layer_id", msg.layer_id);
      if (props[i]) for (const [k, v] of Object.entries(props[i])) f.set(k, v);
      f.set("_pyolqt_style", msg.style || {});
      f.setStyle(style);
      e.source.addFeature(f);
    }
  }

  function cmd_vector_add_polygon(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "vector") return;
    const ring = msg.ring || [];
    const coords = ring.map((p) => lonlat_to_3857(p[0], p[1]));
    if (coords.length > 0) coords.push(coords[0]);
    const f = new ol.Feature({ geometry: new ol.geom.Polygon([coords]) });
    f.setId(msg.id || "poly0");
    f.set("_layer_id", msg.layer_id);
    if (msg.properties) for (const [k, v] of Object.entries(msg.properties)) f.set(k, v);
    f.set("_pyolqt_style", msg.style || {});
    f.setStyle(style_from_simple(msg.style || {}));
    e.source.addFeature(f);
  }

  function cmd_vector_add_circle(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "vector") return;
    const geom = circle_polygon_lonlat(msg.center, msg.radius_m, msg.segments || 72);
    const f = new ol.Feature({ geometry: geom });
    f.setId(msg.id || "circle0");
    f.set("_layer_id", msg.layer_id);
    if (msg.properties) for (const [k, v] of Object.entries(msg.properties)) f.set(k, v);
    f.set("_pyolqt_style", msg.style || {});
    f.setStyle(style_from_simple(msg.style || {}));
    e.source.addFeature(f);
  }

  function cmd_vector_add_line(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "vector") return;
    const coords = (msg.coords || []).map(function(c) {
      return lonlat_to_3857(c[0], c[1]);
    });
    const geom = new ol.geom.LineString(coords);
    const f = new ol.Feature({ geometry: geom });
    f.setId(msg.id || "line0");
    f.set("_layer_id", msg.layer_id);
    if (msg.properties) for (const [k, v] of Object.entries(msg.properties)) f.set(k, v);
    f.set("_pyolqt_style", msg.style || {});
    f.setStyle(style_from_simple(msg.style || {}));
    e.source.addFeature(f);
  }


  function cmd_vector_add_gradient_line(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "vector") return;

    const coords = msg.coords || [];
    const packed = msg.segment_colors || [];
    const baseStyle = msg.style || {};
    const strokeWidth = Number(baseStyle.stroke_width || 3.0);
    const baseProps = msg.properties || {};
    const baseId = msg.id || "gradient_line0";

    // Respect base stroke opacity encoded in style.stroke (e.g. rgba(..., alpha)).
    let baseStrokeAlpha = 1.0;
    if (typeof baseStyle.stroke === "string") {
      const m = baseStyle.stroke.match(/^rgba?\(([^)]+)\)$/i);
      if (m) {
        const parts = m[1].split(",").map((x) => x.trim());
        if (parts.length >= 4) {
          const a = Number(parts[3]);
          if (Number.isFinite(a)) baseStrokeAlpha = Math.max(0, Math.min(1, a));
        }
      }
    }

    for (let i = 0; i < coords.length - 1; i++) {
      const c0 = coords[i], c1 = coords[i + 1];
      const segGeom = new ol.geom.LineString([
        lonlat_to_3857(c0[0], c0[1]),
        lonlat_to_3857(c1[0], c1[1])
      ]);
      const segFeature = new ol.Feature({ geometry: segGeom });
      segFeature.setId(`${baseId}__seg_${i}`);
      segFeature.set("_layer_id", msg.layer_id);
      for (const [k, v] of Object.entries(baseProps)) segFeature.set(k, v);
      segFeature.set("_gradient_parent", baseId);
      segFeature.set("_gradient_segment_index", i);
      if (msg.values && i < msg.values.length) segFeature.set("_gradient_value", msg.values[i]);

      const packedColor = (packed[i] ?? 0xff3333ff);
      const rgba = rgba_from_u32(packedColor);
      rgba[3] = Math.round(rgba[3] * baseStrokeAlpha);
      const color = rgba_to_css(rgba);
      segFeature.setStyle(new ol.style.Style({
        stroke: new ol.style.Stroke({ color: color, width: strokeWidth })
      }));
      e.source.addFeature(segFeature);
    }
  }

  function cmd_vector_add_ellipse(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "vector") return;
    const geom = ellipse_polygon_lonlat(msg.center, msg.sma_m, msg.smi_m, msg.tilt_deg || 0, msg.segments || 96);
    const f = new ol.Feature({ geometry: geom });
    f.setId(msg.id || "ell0");
    f.set("_layer_id", msg.layer_id);
    if (msg.properties) for (const [k, v] of Object.entries(msg.properties)) f.set(k, v);
    f.set("_pyolqt_style", msg.style || {});
    f.setStyle(style_from_simple(msg.style || {}));
    e.source.addFeature(f);
  }

  function cmd_vector_set_opacity(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "vector") return;
    if (typeof msg.opacity === "number") e.layer.setOpacity(msg.opacity);
  }

  function cmd_vector_set_visible(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "vector") return;
    e.layer.setVisible(!!msg.visible);
  }

  function cmd_vector_set_selectable(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "vector") return;
    e.selectable = !!msg.selectable;
  }

  function cmd_wms_set_params(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "wms") return;
    e.source.updateParams(msg.params || {});
  }

  function cmd_raster_set_image(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "raster") return;

    // Avoid flicker: preload the new image first, then swap source atomically.
    e._swapSeq = (e._swapSeq || 0) + 1;
    const seq = e._swapSeq;
    const extent = extent_from_bounds(msg.bounds);
    const projection = state.map.getView().getProjection();

    const swapToNewSource = function() {
      if ((e._swapSeq || 0) !== seq) return; // stale request
      const source = new ol.source.ImageStatic({
        url: msg.url,
        imageExtent: extent,
        projection: projection,
      });
      e.source = source;
      e.layer.setSource(source);
      e.layer.changed();
    };

    const img = new Image();
    img.onload = swapToNewSource;
    img.onerror = swapToNewSource; // still swap so failures are visible
    img.src = msg.url;
  }


  function vector_features_for_id(source, featureId) {
    const target = String(featureId);
    const direct = source.getFeatureById(target);
    if (direct) return [direct];

    const out = [];
    source.forEachFeature(function(f) {
      if (String(f.get("_gradient_parent") || "") === target) out.push(f);
    });
    return out;
  }

  function vector_logical_feature_id(f) {
    const parent = f.get("_gradient_parent");
    if (parent != null && parent !== "") return String(parent);
    const fid = f.getId();
    return fid == null ? "" : String(fid);
  }

  function cmd_select_set(msg) {
    if (!state.selectInteraction) return;
    const selected = state.selectInteraction.getFeatures();
    selected.clear();

    const layer_id = msg.layer_id || "";
    const ids = msg.feature_ids || [];
    if (!layer_id) return;

    const e = state.layers.get(layer_id);
    if (!e || e.type !== "vector") return;

    for (const fid of ids) {
      const features = vector_features_for_id(e.source, String(fid));
      for (const f of features) selected.push(f);
    }
    if (msg.emit !== false) {
      const features = selected.getArray();
      const logical = Array.from(
        new Set(features.map(vector_logical_feature_id).filter(Boolean))
      );
      emitToPython("selection", { layer_id, feature_ids: logical, count: logical.length });
    }
  }

  function dispatch(msg) {
    const perfStart = performance.now();
    const t = msg.type;
    try {
    switch (t) {
      case "perf.set_enabled": return cmd_perf_set_enabled(msg);
      case "layer.add_vector": return cmd_add_vector(msg);
      case "layer.add_wms": return cmd_add_wms(msg);
      case "layer.add_tile": return cmd_add_tile(msg);
      case "layer.add_raster": return cmd_add_raster(msg);
      case "layer.remove": return cmd_layer_remove(msg);
      case "layer.opacity": return cmd_layer_opacity(msg);

      case "vector.clear": return cmd_vector_clear(msg);
      case "vector.add_points": return cmd_vector_add_points(msg);
      case "vector.add_polygon": return cmd_vector_add_polygon(msg);
      case "vector.add_circle": return cmd_vector_add_circle(msg);
      case "vector.add_ellipse": return cmd_vector_add_ellipse(msg);
      case "vector.add_line": return cmd_vector_add_line(msg);
      case "vector.add_gradient_line": return cmd_vector_add_gradient_line(msg);
      case "vector.set_opacity": return cmd_vector_set_opacity(msg);
      case "vector.set_visible": return cmd_vector_set_visible(msg);
      case "vector.set_selectable": return cmd_vector_set_selectable(msg);

      case "wms.set_params": return cmd_wms_set_params(msg);
      case "wms.set_opacity": return cmd_wms_set_opacity(msg);
      case "wms.set_visible": return cmd_wms_set_visible(msg);
      case "tile.set_url": return cmd_tile_set_url(msg);
      case "tile.set_opacity": return cmd_tile_set_opacity(msg);
      case "tile.set_visible": return cmd_tile_set_visible(msg);
      case "raster.set_image": return cmd_raster_set_image(msg);

      case "select.set": return cmd_select_set(msg);
    case "map.get_view_extent": return cmd_map_get_view_extent(msg);
    case "map.set_view": return cmd_map_set_view(msg);
    case "map.fit_bounds": return cmd_map_fit_bounds(msg);
    case "map.fit_to_data": return cmd_map_fit_to_data(msg);
      case "map.base.opacity": return cmd_map_base_opacity(msg);
    case "map.set_extent_watch": return cmd_map_set_extent_watch(msg);
    case "map.set_background": return cmd_map_set_background(msg);

    // --- Coordinate Display ---
    case "coordinates.set_visible": return cmd_coordinates_set_visible(msg);
    case "countries.set_visible": return cmd_countries_set_visible(msg);

    // --- Measurement Mode ---
    case "measure.set_mode": return cmd_measure_set_mode(msg);
    case "measure.clear": return cmd_measure_clear(msg);

    // --- FastPoints ---
    case "fast_points.add_layer": return cmd_fast_points_add_layer(msg);
    case "fast_points.add_points": return cmd_fast_points_add_points(msg);
    case "fast_points.redraw": return cmd_fast_points_redraw(msg);
    case "fast_points.clear": return cmd_fast_points_clear(msg);
    case "fast_points.set_opacity": return cmd_fast_points_set_opacity(msg);
    case "fast_points.set_visible": return cmd_fast_points_set_visible(msg);
    case "fast_points.set_selectable": return cmd_fast_points_set_selectable(msg);
    case "fast_points.select.set": return cmd_fast_points_select_set(msg);
    case "fast_points.remove_ids": return cmd_fast_points_remove_ids(msg);
    case "fast_points.hide_ids": return cmd_fast_points_hide_ids(msg);
    case "fast_points.show_ids": return cmd_fast_points_show_ids(msg);
    case "fast_points.hide_indices": return cmd_fast_points_hide_indices(msg);
    case "fast_points.show_indices": return cmd_fast_points_show_indices(msg);
    case "fast_points.show_only_indices": return cmd_fast_points_show_only_indices(msg);
    case "fast_points.show_only_index_ranges": return cmd_fast_points_show_only_index_ranges(msg);
    case "fast_points.show_all": return cmd_fast_points_show_all(msg);
    case "fast_points.set_colors": return cmd_fast_points_set_colors(msg);
    case "fast_points.clear_colors": return cmd_fast_points_clear_colors(msg);
      case "base.set_opacity": return cmd_base_set_opacity(msg);
      case "base.set_visible": return cmd_base_set_visible(msg);
      case "vector.remove_features": return cmd_vector_remove_features(msg);
      case "vector.update_styles": return cmd_vector_update_styles(msg);

    // --- FastGeoPoints ---
    case "fast_geopoints.add_layer": return cmd_fast_geopoints_add_layer(msg);
    case "fast_geopoints.add_points": return cmd_fast_geopoints_add_points(msg);
    case "fast_geopoints.redraw": return cmd_fast_geopoints_redraw(msg);
    case "fast_geopoints.clear": return cmd_fast_geopoints_clear(msg);
    case "fast_geopoints.remove_ids": return cmd_fast_geopoints_remove_ids(msg);
    case "fast_geopoints.set_opacity": return cmd_fast_geopoints_set_opacity(msg);
    case "fast_geopoints.set_visible": return cmd_fast_geopoints_set_visible(msg);
    case "fast_geopoints.set_selectable": return cmd_fast_geopoints_set_selectable(msg);
    case "fast_geopoints.set_ellipses_visible": return cmd_fast_geopoints_set_ellipses_visible(msg);
    case "fast_geopoints.set_selected_ellipses_visible": return cmd_fast_geopoints_set_selected_ellipses_visible(msg);
    case "fast_geopoints.select.set": return cmd_fast_geopoints_select_set(msg);
    case "fast_geopoints.hide_ids": return cmd_fast_geopoints_hide_ids(msg);
    case "fast_geopoints.show_ids": return cmd_fast_geopoints_show_ids(msg);
    case "fast_geopoints.show_all": return cmd_fast_geopoints_show_all(msg);
    case "fast_geopoints.set_colors": return cmd_fast_geopoints_set_colors(msg);

      default:
        jsError("Unknown command:", t, msg);
    }
    } finally {
      if (t && (t.indexOf("fast_points.") === 0 || t === "fast_points.add_layer")) {
        emitPerf({
          side: "javascript",
          operation: "dispatch",
          type: t,
          layer_id: msg.layer_id || null,
          elapsed_ms: (performance.now() - perfStart).toFixed(2)
        });
      }
    }
  }

  window.pyolqt_send = function (jsonOrObj) {
    try {
      ensureMap();
      const obj = (typeof jsonOrObj === "string") ? JSON.parse(jsonOrObj) : jsonOrObj;
      dispatch(obj);
    } catch (e) {
      jsError("pyolqt_send failed:", e);
    }
  };

  window.pyolqt_is_ready = function () {
    return !!(state.map && state.qtBridge && state.readyEmitted);
  };

  function connectQWebChannel() {
    if (!window.qt || !qt.webChannelTransport) return false;
    if (typeof QWebChannel !== "function") return false;

    new QWebChannel(qt.webChannelTransport, function (channel) {
      state.qtBridge = channel.objects.qtBridge || null;
      if (state.map) {
        emitReadyIfNeeded();
      } else {
        initMap();
      }
    });
    return true;
  }

  // Bootstrap: try until available.
  (function boot() {
    let tries = 0;
    const timer = setInterval(() => {
      tries++;
      if (connectQWebChannel()) {
        clearInterval(timer);
      } else if (tries > 40) {
        clearInterval(timer);
        initMap();
      }
    }, 50);
  })();

function cmd_vector_remove_features(msg) {
  const e = getLayerEntry(msg.layer_id);
  if (e.type !== "vector") return;
  const ids = msg.feature_ids || msg.ids || [];
  for (let i = 0; i < ids.length; i++) {
    const features = vector_features_for_id(e.source, ids[i]);
    for (const f of features) e.source.removeFeature(f);
  }
}

function cmd_vector_update_styles(msg) {
  const e = getLayerEntry(msg.layer_id);
  if (!e || e.type !== "vector") return;
  const ids = msg.feature_ids || [];
  const styles = msg.styles || [];
  if (ids.length !== styles.length) return;
  
  for (let i = 0; i < ids.length; i++) {
    const features = vector_features_for_id(e.source, String(ids[i]));
    const styleSpec = styles[i] || {};
    const style = style_from_simple(styleSpec);
    for (const f of features) {
      f.set("_pyolqt_style", styleSpec);
      f.setStyle(style);
    }
  }
}
})();
