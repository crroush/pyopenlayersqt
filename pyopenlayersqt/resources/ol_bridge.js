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
    measurePointerMoveKey: null,  // Event listener key for map event
    measureClickKey: null,   // Event listener key for map event
    measureKeyDownKey: null, // Flag for keydown event listener (true/false)
    // Coordinate display state
    coordinateOverlay: null,      // Overlay element for coordinates
    coordinatePointerMoveKey: null, // Event listener key for coordinate display
  };




  window._pyolqt_state = state;

// ---- Map extent API (one-shot + debounced watch) ----
function _pyolqt_view_extent_obj() {
  const st = window._pyolqt_state;
  if (!st || !st.map) return null;
  const map = st.map;
  const view = map.getView();
  const extent3857 = view.calculateExtent(map.getSize());
  const bl = ol.proj.toLonLat([extent3857[0], extent3857[1]]);
  const tr = ol.proj.toLonLat([extent3857[2], extent3857[3]]);
  return {
    lon_min: bl[0],
    lat_min: bl[1],
    lon_max: tr[0],
    lat_max: tr[1],
    zoom: view.getZoom(),
    resolution: view.getResolution(),
  };
}

function cmd_map_get_view_extent(msg) {
  const obj = _pyolqt_view_extent_obj();
  if (!obj) return;
  emitToPython("view_extent", obj);
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
  emitToPython("selection", {
    layer_id: entry.layer_id,
    feature_ids: Array.from(entry.selectedIds),
  });
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

      ctx.globalAlpha = entry.opacity;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const scaleX = canvas.width / (extent[2] - extent[0]);
      const scaleY = canvas.height / (extent[3] - extent[1]);

      const queryStart = performance.now();
      const cand = fp_query_extent(entry, extent);
      const queryTime = performance.now() - queryStart;

      const defCss = rgba_to_css(entry.style.default_rgba);
      const selCss = rgba_to_css(entry.style.selected_rgba);

      // Performance optimization: batch points by color to reduce canvas API calls
      // Group points by their fill color and radius to draw them together
      // Draw unselected points first, then selected points on top for visibility
      const batchStart = performance.now();
      const unselectedBatches = new Map(); // key: "color|radius" -> array of {x, y}
      const selectedBatches = new Map(); // key: "color|radius" -> array of {x, y}
      
      for (let k = 0; k < cand.length; k++) {
        const i = cand[k];
        if (entry.deleted[i] || entry.hidden[i]) continue;
        const x = (entry.x[i] - extent[0]) * scaleX;
        const y = (extent[3] - entry.y[i]) * scaleY;
        const fid = entry.ids[i];
        const isSel = entry.selectedIds.has(fid);
        const radius = (isSel ? entry.style.selected_radius : entry.style.radius) * pixelRatio;

        let fill = defCss;
        const u = entry.color_u32[i];
        if (u !== 0) fill = rgba_to_css(rgba_from_u32(u));
        if (isSel) fill = selCss;

        const key = fill + "|" + radius;
        const batches = isSel ? selectedBatches : unselectedBatches;
        let batch = batches.get(key);
        if (!batch) {
          batch = { fill, radius, points: [] };
          batches.set(key, batch);
        }
        batch.points.push({ x, y });
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
      if (cand.length > 100) {  // Only log when there are significant points
        emitToPython("perf", {
          layer_id: entry.layer_id,
          operation: "fast_points_render",
          point_count: cand.length,
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
    cellSize: (msg.cell_size_m || 1000.0),
    selectedIds: new Set(),
    idIndex: new Map(),
    style: msg.style || { radius: 3, default_rgba: [255,51,51,204], selected_radius: 6, selected_rgba: [0,255,255,255] },
    source: null,
    layer: null,
  };

  fp_make_canvas_layer(entry);
  state.map.addLayer(entry.layer);
  state.layers.set(layer_id, entry);
  state.layerByObj.set(entry.layer, layer_id);
}

function cmd_fast_points_add_points(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  const coords = msg.coords || [];
  const ids = msg.ids || null;
  const colors = msg.colors || null;
  const startIndex = entry.x.length;
  for (let i = 0; i < coords.length; i++) {
    const lon = coords[i][0], lat = coords[i][1];
    const p = lonlat_to_3857(lon, lat);
    entry.x.push(p[0]);
    entry.y.push(p[1]);
    const fid = (ids ? ids[i] : String(startIndex + i));
    entry.ids.push(fid);
    entry.idIndex.set(String(fid), startIndex + i);
    entry.deleted.push(false);
    entry.hidden.push(false);
    entry.color_u32.push(colors ? (colors[i] >>> 0) : 0);
    fp_index_insert(entry, startIndex + i);
  }
  fp_redraw(entry);
}

function cmd_fast_points_clear(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  entry.x = []; entry.y = []; entry.ids = []; entry.color_u32 = []; entry.deleted = []; entry.hidden = [];
  entry.grid = new Map();
  entry.idIndex = new Map();
  entry.selectedIds = new Set();
  fp_redraw(entry);
  fp_emit_selection(entry);
}

function cmd_fast_points_remove_ids(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  const raw = (msg.feature_ids || msg.ids || []);
  const ids = new Set(raw.map(x => String(x)));
  if (ids.size === 0) return;
  for (const id of ids) {
    const i = entry.idIndex.get(id);
    if (i == null || entry.deleted[i]) continue;
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
    const entry = getLayerEntry(msg.layer_id);
    if (entry.type !== "fast_points") return;
    entry.selectedIds = new Set(msg.feature_ids || []);
    fp_redraw(entry);
    fp_emit_selection(entry);
}

function cmd_fast_points_hide_ids(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  const raw = (msg.feature_ids || msg.ids || []);
  const ids = new Set(raw.map(x => String(x)));
  if (ids.size === 0) return;
  for (const id of ids) {
    const i = entry.idIndex.get(id);
    if (i == null || entry.deleted[i]) continue;
    entry.hidden[i] = true;
  }
  fp_redraw(entry);
}

function cmd_fast_points_show_ids(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  const raw = (msg.feature_ids || msg.ids || []);
  const ids = new Set(raw.map(x => String(x)));
  if (ids.size === 0) return;
  for (const id of ids) {
    const i = entry.idIndex.get(id);
    if (i == null || entry.deleted[i]) continue;
    entry.hidden[i] = false;
  }
  fp_redraw(entry);
}

function cmd_fast_points_show_all(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  for (let i = 0; i < entry.hidden.length; i++) {
    entry.hidden[i] = false;
  }
  fp_redraw(entry);
}

function cmd_fast_points_set_colors(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== "fast_points") return;
  const fids = msg.feature_ids || [];
  const colors = msg.colors || [];
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

function fgp_redraw(entry) { if (entry.source) entry.source.changed(); }
function fgp_emit_selection(entry) {
  emitToPython('selection', { layer_id: entry.layer_id, feature_ids: Array.from(entry.selectedIds) });
}

function fgp_make_canvas_layer(entry) {
  const source = new ol.source.ImageCanvas({
    projection: state.map.getView().getProjection(),
    ratio: 1,
    canvasFunction: function(extent, resolution, pixelRatio, size, projection) {
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.floor(size[0] * pixelRatio));
      canvas.height = Math.max(1, Math.floor(size[1] * pixelRatio));
      const ctx = canvas.getContext('2d', { willReadFrequently: !!window.OL_WILL_READ_FREQUENTLY });
      if (!ctx) return canvas;

      ctx.globalAlpha = entry.opacity;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const scaleX = canvas.width / (extent[2] - extent[0]);
      const scaleY = canvas.height / (extent[3] - extent[1]);

      const cand = fp_query_extent(entry, extent);

      const TAU = Math.PI * 2;

      // ---- Ellipses (batched) ----
      const st = entry.style || {};
      const ellipsesVisible = entry.ellipsesVisible && st.ellipses_visible !== false;
      const skipWhileInteracting = (st.skip_ellipses_while_interacting !== false);
      const canDrawEllipses = ellipsesVisible && !(skipWhileInteracting && state.viewInteracting);

      if (canDrawEllipses) {
        const minPx = Math.max(0.0, Number(st.min_ellipse_px || 0.0));
        const maxPerPath = Math.max(250, (st.max_ellipses_per_path | 0) || 2000);
        const strokeCss = rgba_to_css(st.ellipse_stroke_rgba || [255,204,0,180]);
        const strokeW = (Number(st.ellipse_stroke_width || 1.5) * pixelRatio);
        const fillEll = !!st.fill_ellipses;
        const fillCss = rgba_to_css(st.ellipse_fill_rgba || [255,204,0,40]);

        // Unselected first
        ctx.lineWidth = strokeW;
        ctx.strokeStyle = strokeCss;
        if (fillEll) ctx.fillStyle = fillCss;
        let nInPath = 0;
        ctx.beginPath();
        for (let k = 0; k < cand.length; k++) {
          const i = cand[k];
          if (entry.deleted[i] || entry.hidden[i]) continue;
          const fid = entry.ids[i];
          if (entry.selectedIds.has(fid)) continue;
          const rx = (entry.a[i] / resolution) * pixelRatio;
          const ry = (entry.b[i] / resolution) * pixelRatio;
          if (rx < minPx && ry < minPx) continue;
          const x = (entry.x[i] - extent[0]) * scaleX;
          const y = (extent[3] - entry.y[i]) * scaleY;
          // IMPORTANT: moveTo prevents stray connecting lines between ellipses
          const rot = entry.rot[i];
          ctx.moveTo(x + rx * Math.cos(rot), y + rx * Math.sin(rot));
          ctx.ellipse(x, y, rx, ry, rot, 0, TAU);

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

        // Selected ellipses on top
        const selStrokeCss = rgba_to_css(st.selected_ellipse_stroke_rgba || [0,255,255,255]);
        const selStrokeW = (Number(st.selected_ellipse_stroke_width || (st.ellipse_stroke_width || 1.5) * 1.8) * pixelRatio);
        ctx.lineWidth = selStrokeW;
        ctx.strokeStyle = selStrokeCss;
        nInPath = 0;
        ctx.beginPath();
        for (let k = 0; k < cand.length; k++) {
          const i = cand[k];
          if (entry.deleted[i] || entry.hidden[i]) continue;
          const fid = entry.ids[i];
          if (!entry.selectedIds.has(fid)) continue;
          const rx = (entry.a[i] / resolution) * pixelRatio;
          const ry = (entry.b[i] / resolution) * pixelRatio;
          if (rx < minPx && ry < minPx) continue;
          const x = (entry.x[i] - extent[0]) * scaleX;
          const y = (extent[3] - entry.y[i]) * scaleY;
          const rot = entry.rot[i];
          ctx.moveTo(x + rx * Math.cos(rot), y + rx * Math.sin(rot));
          ctx.ellipse(x, y, rx, ry, rot, 0, TAU);
          nInPath++;
          if (nInPath >= maxPerPath) {
            ctx.stroke();
            ctx.beginPath();
            nInPath = 0;
          }
        }
        if (nInPath > 0) ctx.stroke();
      }

      // ---- Points ----
      // Draw unselected points first, then selected points on top
      const defCss = rgba_to_css(st.default_point_rgba || [255,51,51,204]);
      const selCss = rgba_to_css(st.selected_point_rgba || [0,255,255,255]);

      // Unselected points first
      for (let k = 0; k < cand.length; k++) {
        const i = cand[k];
        if (entry.deleted[i] || entry.hidden[i]) continue;
        const fid = entry.ids[i];
        if (entry.selectedIds.has(fid)) continue; // Skip selected, draw later
        
        const x = (entry.x[i] - extent[0]) * scaleX;
        const y = (extent[3] - entry.y[i]) * scaleY;
        const radius = (st.point_radius || 3.0) * pixelRatio;

        let fill = defCss;
        const u = entry.color_u32[i];
        if (u !== 0) fill = rgba_to_css(rgba_from_u32(u));

        ctx.beginPath();
        ctx.arc(x, y, radius, 0, TAU);
        ctx.fillStyle = fill;
        ctx.fill();
      }
      
      // Selected points on top
      for (let k = 0; k < cand.length; k++) {
        const i = cand[k];
        if (entry.deleted[i] || entry.hidden[i]) continue;
        const fid = entry.ids[i];
        if (!entry.selectedIds.has(fid)) continue; // Only selected
        
        const x = (entry.x[i] - extent[0]) * scaleX;
        const y = (extent[3] - entry.y[i]) * scaleY;
        const radius = (st.selected_point_radius || 6.0) * pixelRatio;

        ctx.beginPath();
        ctx.arc(x, y, radius, 0, TAU);
        ctx.fillStyle = selCss;
        ctx.fill();
      }

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
    cellSize: (msg.cell_size_m || 1000.0),
    selectedIds: new Set(),
    idIndex: new Map(),
    style,
    source: null,
    layer: null,
  };

  fgp_make_canvas_layer(entry);
  state.map.addLayer(entry.layer);
  state.layers.set(layer_id, entry);
  state.layerByObj.set(entry.layer, layer_id);
}

function cmd_fast_geopoints_add_points(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  const coords = msg.coords || [];
  const sma_m = msg.sma_m || [];
  const smi_m = msg.smi_m || [];
  const tilt_deg = msg.tilt_deg || [];
  const ids = msg.ids || null;
  const colors = msg.colors || null;

  const startIndex = entry.x.length;
  for (let i = 0; i < coords.length; i++) {
    const lon = coords[i][0], lat = coords[i][1];
    const p = lonlat_to_3857(lon, lat);
    entry.x.push(p[0]);
    entry.y.push(p[1]);
    const fid = (ids ? ids[i] : String(startIndex + i));
    entry.ids.push(fid);
    entry.idIndex.set(String(fid), startIndex + i);
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

    fp_index_insert(entry, startIndex + i);
  }
  fgp_redraw(entry);
}

function cmd_fast_geopoints_clear(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  entry.x = []; entry.y = []; entry.ids = []; entry.color_u32 = []; entry.deleted = []; entry.hidden = [];
  entry.a = []; entry.b = []; entry.rot = [];
  entry.grid = new Map();
  entry.idIndex = new Map();
  entry.selectedIds = new Set();
  fgp_redraw(entry);
  fgp_emit_selection(entry);
}

function cmd_fast_geopoints_remove_ids(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  const raw = (msg.feature_ids || msg.ids || []);
  const ids = new Set(raw.map(x => String(x)));
  if (ids.size === 0) return;
  for (const id of ids) {
    const i = entry.idIndex.get(id);
    if (i == null || entry.deleted[i]) continue;
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

function cmd_fast_geopoints_select_set(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  entry.selectedIds = new Set(msg.feature_ids || []);
  fgp_redraw(entry);
  fgp_emit_selection(entry);
}

function cmd_fast_geopoints_hide_ids(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  const raw = (msg.feature_ids || msg.ids || []);
  const ids = new Set(raw.map(x => String(x)));
  if (ids.size === 0) return;
  for (const id of ids) {
    const i = entry.idIndex.get(id);
    if (i == null || entry.deleted[i]) continue;
    entry.hidden[i] = true;
  }
  fgp_redraw(entry);
}

function cmd_fast_geopoints_show_ids(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  const raw = (msg.feature_ids || msg.ids || []);
  const ids = new Set(raw.map(x => String(x)));
  if (ids.size === 0) return;
  for (const id of ids) {
    const i = entry.idIndex.get(id);
    if (i == null || entry.deleted[i]) continue;
    entry.hidden[i] = false;
  }
  fgp_redraw(entry);
}

function cmd_fast_geopoints_show_all(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  for (let i = 0; i < entry.hidden.length; i++) {
    entry.hidden[i] = false;
  }
  fgp_redraw(entry);
}

function cmd_fast_geopoints_set_colors(msg) {
  const entry = getLayerEntry(msg.layer_id);
  if (entry.type !== 'fast_geopoints') return;
  const fids = msg.feature_ids || [];
  const colors = msg.colors || [];
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
      const res = state.map.getView().getResolution() || 1.0;
      const radius_m = Math.max(5.0, res * 8.0);
      const idx = fp_pick_nearest(entry, coord, radius_m);
      if (idx < 0) continue;
      const fid = entry.ids[idx];
      if (entry.selectedIds.has(fid)) entry.selectedIds.delete(fid);
      else entry.selectedIds.add(fid);
      fp_redraw(entry);
      fp_emit_selection(entry);
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
    const extent = dragBox.getGeometry().getExtent();
    for (const [layer_id, entry] of state.layers.entries()) {
      if ((entry.type !== "fast_points" && entry.type !== "fast_geopoints") || !entry.selectable) continue;
      const cand = fp_query_extent(entry, extent);
      const next = new Set();
      for (let k = 0; k < cand.length; k++) {
        const i = cand[k];
        if (entry.deleted[i]) continue;
        const x = entry.x[i], y = entry.y[i];
        if (x >= extent[0] && x <= extent[2] && y >= extent[1] && y <= extent[3]) next.add(entry.ids[i]);
      }
      // Only emit selection if something was selected in this layer or if clearing previous selection
      if (next.size > 0 || entry.selectedIds.size > 0) {
        entry.selectedIds = next;
        fp_redraw(entry);
        fp_emit_selection(entry);
      }
    }
  });
}
function lonlat_to_3857(lon, lat) { return ol.proj.fromLonLat([lon, lat]); }
function p3857_to_lonlat(coord) { return ol.proj.toLonLat(coord); }

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
  
  // Clear previous temp geometry
  state.measureSource.getFeatures().forEach(feature => {
    if (feature.get('_temp')) {
      state.measureSource.removeFeature(feature);
    }
  });
  
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
    
    // Remove temp features
    if (state.measureSource) {
      state.measureSource.getFeatures().forEach(feature => {
        if (feature.get('_temp')) {
          state.measureSource.removeFeature(feature);
        }
      });
    }
  }
}

function clearMeasurements() {
  state.measurePoints = [];
  
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

  function style_from_simple(s) {
    const stroke = new ol.style.Stroke({
      color: s.stroke || "rgba(0,0,0,1)",
      width: s.stroke_width || 1,
    });
    const fill = new ol.style.Fill({
      color: s.fill || "rgba(0,0,0,0)",
    });

    if (typeof s.radius === "number") {
      return new ol.style.Style({
        image: new ol.style.Circle({ radius: s.radius, fill, stroke }),
      });
    }
    return new ol.style.Style({ stroke, fill });
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


  function initMap() {
    // Disable tile transition for better pan/zoom performance
    const base = new ol.layer.Tile({ 
      source: new ol.source.OSM({ transition: 0 })
    });
    state.base_layer = base;

    state.map = new ol.Map({
      target: "map",
      layers: [base],
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
        const fid = f.getId() || "";
        if (!layer_id || !fid) continue;
        if (!outByLayer.has(layer_id)) outByLayer.set(layer_id, []);
        outByLayer.get(layer_id).push(String(fid));
      }
      for (const [layer_id, feature_ids] of outByLayer.entries()) {
        emitToPython("selection", { layer_id, feature_ids, count: feature_ids.length });
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
        const fid = f.getId() || "";
        if (!lid || !fid) continue;
        if (!outByLayer.has(lid)) outByLayer.set(lid, []);
        outByLayer.get(lid).push(String(fid));
      }
      for (const [lid, fids] of outByLayer.entries()) {
        emitToPython("selection", { layer_id: lid, feature_ids: fids, count: fids.length });
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
      
      emitToPython("perf", {
        operation: "map_interaction",
        interaction_time_ms: interactionTime.toFixed(2),
        render_calls: state.renderCount,
        avg_render_ms: state.renderCount > 0 ? (interactionTime / state.renderCount).toFixed(2) : 0
      });
      
      state.viewInteracting = false;
      // redraw fast layers so ellipses appear after interaction ends
      for (const [lid, e] of state.layers.entries()) {
        if (e.type === 'fast_geopoints' && e.ellipsesVisible) fgp_redraw(e);
      }
    });
    fp_install_interactions();
    emitToPython("ready", { ok: true });
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
    const op = Math.max(0, Math.min(1, Number(msg.opacity)));
    state.base_layer.setOpacity(op);
  }

  function cmd_vector_clear(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "vector") return;
    e.source.clear();
    if (state.selectInteraction) state.selectInteraction.getFeatures().clear();
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
    f.setStyle(style_from_simple(msg.style || {}));
    e.source.addFeature(f);
  }

  function cmd_vector_add_ellipse(msg) {
    const e = getLayerEntry(msg.layer_id);
    if (e.type !== "vector") return;
    const geom = ellipse_polygon_lonlat(msg.center, msg.sma_m, msg.smi_m, msg.tilt_deg || 0, msg.segments || 96);
    const f = new ol.Feature({ geometry: geom });
    f.setId(msg.id || "ell0");
    f.set("_layer_id", msg.layer_id);
    if (msg.properties) for (const [k, v] of Object.entries(msg.properties)) f.set(k, v);
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

    // ImageStatic doesn't reliably expose setUrl/setImageExtent across OL builds.
    // Recreate source and swap it.
    const extent = extent_from_bounds(msg.bounds);
    const source = new ol.source.ImageStatic({
      url: msg.url,
      imageExtent: extent,
      projection: state.map.getView().getProjection(),
    });
    e.source = source;
    e.layer.setSource(source);
    e.layer.changed();
  }

  function cmd_select_set(msg) {
    if (!state.selectInteraction) return;
    const selected = state.selectInteraction.getFeatures();
    selected.clear();

    const layer_id = msg.layer_id || "";
    const ids = msg.feature_ids || [];
    if (!layer_id || !ids.length) return;

    const e = state.layers.get(layer_id);
    if (!e || e.type !== "vector") return;

    for (const fid of ids) {
      const f = e.source.getFeatureById(String(fid));
      if (f) selected.push(f);
    }
    // emit selection via select handler
    const features = selected.getArray();
    emitToPython("selection", { layer_id, feature_ids: features.map(f => String(f.getId())), count: features.length });
  }

  function dispatch(msg) {
    const t = msg.type;
    switch (t) {
      case "layer.add_vector": return cmd_add_vector(msg);
      case "layer.add_wms": return cmd_add_wms(msg);
      case "layer.add_raster": return cmd_add_raster(msg);
      case "layer.remove": return cmd_layer_remove(msg);
      case "layer.opacity": return cmd_layer_opacity(msg);

      case "vector.clear": return cmd_vector_clear(msg);
      case "vector.add_points": return cmd_vector_add_points(msg);
      case "vector.add_polygon": return cmd_vector_add_polygon(msg);
      case "vector.add_circle": return cmd_vector_add_circle(msg);
      case "vector.add_ellipse": return cmd_vector_add_ellipse(msg);
      case "vector.add_line": return cmd_vector_add_line(msg);
      case "vector.set_opacity": return cmd_vector_set_opacity(msg);
      case "vector.set_visible": return cmd_vector_set_visible(msg);
      case "vector.set_selectable": return cmd_vector_set_selectable(msg);

      case "wms.set_params": return cmd_wms_set_params(msg);
      case "raster.set_image": return cmd_raster_set_image(msg);

      case "select.set": return cmd_select_set(msg);
    case "map.get_view_extent": return cmd_map_get_view_extent(msg);
    case "map.set_view": return cmd_map_set_view(msg);
      case "map.base.opacity": return cmd_map_base_opacity(msg);
    case "map.set_extent_watch": return cmd_map_set_extent_watch(msg);

    // --- Coordinate Display ---
    case "coordinates.set_visible": return cmd_coordinates_set_visible(msg);

    // --- Measurement Mode ---
    case "measure.set_mode": return cmd_measure_set_mode(msg);
    case "measure.clear": return cmd_measure_clear(msg);

    // --- FastPoints ---
    case "fast_points.add_layer": return cmd_fast_points_add_layer(msg);
    case "fast_points.add_points": return cmd_fast_points_add_points(msg);
    case "fast_points.clear": return cmd_fast_points_clear(msg);
    case "fast_points.set_opacity": return cmd_fast_points_set_opacity(msg);
    case "fast_points.set_visible": return cmd_fast_points_set_visible(msg);
    case "fast_points.set_selectable": return cmd_fast_points_set_selectable(msg);
    case "fast_points.select.set": return cmd_fast_points_select_set(msg);
    case "fast_points.remove_ids": return cmd_fast_points_remove_ids(msg);
    case "fast_points.hide_ids": return cmd_fast_points_hide_ids(msg);
    case "fast_points.show_ids": return cmd_fast_points_show_ids(msg);
    case "fast_points.show_all": return cmd_fast_points_show_all(msg);
    case "fast_points.set_colors": return cmd_fast_points_set_colors(msg);
      case "base.set_opacity": return cmd_base_set_opacity(msg);
      case "vector.remove_features": return cmd_vector_remove_features(msg);
      case "vector.update_styles": return cmd_vector_update_styles(msg);

    // --- FastGeoPoints ---
    case "fast_geopoints.add_layer": return cmd_fast_geopoints_add_layer(msg);
    case "fast_geopoints.add_points": return cmd_fast_geopoints_add_points(msg);
    case "fast_geopoints.clear": return cmd_fast_geopoints_clear(msg);
    case "fast_geopoints.remove_ids": return cmd_fast_geopoints_remove_ids(msg);
    case "fast_geopoints.set_opacity": return cmd_fast_geopoints_set_opacity(msg);
    case "fast_geopoints.set_visible": return cmd_fast_geopoints_set_visible(msg);
    case "fast_geopoints.set_selectable": return cmd_fast_geopoints_set_selectable(msg);
    case "fast_geopoints.set_ellipses_visible": return cmd_fast_geopoints_set_ellipses_visible(msg);
    case "fast_geopoints.select.set": return cmd_fast_geopoints_select_set(msg);
    case "fast_geopoints.hide_ids": return cmd_fast_geopoints_hide_ids(msg);
    case "fast_geopoints.show_ids": return cmd_fast_geopoints_show_ids(msg);
    case "fast_geopoints.show_all": return cmd_fast_geopoints_show_all(msg);
    case "fast_geopoints.set_colors": return cmd_fast_geopoints_set_colors(msg);

      default:
        jsError("Unknown command:", t, msg);
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

  function connectQWebChannel() {
    if (!window.qt || !qt.webChannelTransport) return false;
    if (typeof QWebChannel !== "function") return false;

    new QWebChannel(qt.webChannelTransport, function (channel) {
      state.qtBridge = channel.objects.qtBridge || null;
      initMap();
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
    const f = e.source.getFeatureById(ids[i]);
    if (f) e.source.removeFeature(f);
  }
}

function cmd_vector_update_styles(msg) {
  const e = getLayerEntry(msg.layer_id);
  if (!e || e.type !== "vector") return;
  const ids = msg.feature_ids || [];
  const styles = msg.styles || [];
  if (ids.length !== styles.length) return;
  
  for (let i = 0; i < ids.length; i++) {
    const f = e.source.getFeatureById(String(ids[i]));
    if (f) {
      const style = style_from_simple(styles[i]);
      f.setStyle(style);
    }
  }
}
})();
