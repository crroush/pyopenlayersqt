/* global ol, QWebChannel, qt */
(function () {
  const state = {
    bridge: null,
    map: null,
    layers: new Map(),         // name -> ol.layer.*
    vectorSources: new Map(),  // name -> ol.source.Vector
    select: null,
    selectedStyleByLayer: new Map(), // name -> {defaultStyle, selectedStyle}
  };

  function jsLog(msg) {
    try { if (state.bridge && state.bridge.log) state.bridge.log(String(msg)); } catch (e) {}
  }

  function ensureOl() {
    if (typeof ol === "undefined") throw new Error("OpenLayers (ol) is not defined");
  }

  function to3857ExtentFromLonLat(extLonLat) {
    const [minLon, minLat, maxLon, maxLat] = extLonLat;
    const bl = ol.proj.fromLonLat([minLon, minLat]);
    const tr = ol.proj.fromLonLat([maxLon, maxLat]);
    return [bl[0], bl[1], tr[0], tr[1]];
  }

  function rgba(arr) {
    // arr [r,g,b,a]
    return `rgba(${arr[0]},${arr[1]},${arr[2]},${(arr[3] ?? 255) / 255})`;
  }

  function makePointStyles(style) {
    const def = new ol.style.Style({
      image: new ol.style.Circle({
        radius: style.radius ?? 5,
        fill: new ol.style.Fill({ color: rgba(style.fill ?? [0,120,255,170]) }),
        stroke: new ol.style.Stroke({ color: rgba(style.stroke ?? [0,0,0,80]), width: style.stroke_width ?? 1 })
      })
    });

    const sel = new ol.style.Style({
      image: new ol.style.Circle({
        radius: style.selected_radius ?? 7,
        fill: new ol.style.Fill({ color: rgba(style.selected_fill ?? [255,50,50,220]) }),
        stroke: new ol.style.Stroke({ color: rgba(style.selected_stroke ?? [0,0,0,120]), width: style.selected_stroke_width ?? 1 })
      })
    });

    return { def, sel };
  }

  function refreshVectorLayerStyle(layerName) {
    const vectorLayer = state.layers.get(layerName);
    if (!vectorLayer) return;

    const styles = state.selectedStyleByLayer.get(layerName);
    if (!styles) return;

    const selectedIds = new Set(
      state.select.getFeatures().getArray()
        .filter(f => f.get("__layer") === layerName)
        .map(f => String(f.getId()))
    );

    vectorLayer.setStyle((feature) => {
      const fid = String(feature.getId());
      return selectedIds.has(fid) ? styles.sel : styles.def;
    });
  }

  function emitSelection() {
    if (!state.bridge || !state.bridge.emitEvent) return;

    // Group selected features by layer
    const byLayer = new Map();
    const feats = state.select.getFeatures().getArray();

    for (const f of feats) {
      const layer = f.get("__layer") || "";
      if (!byLayer.has(layer)) byLayer.set(layer, []);
      byLayer.get(layer).push(f);
    }

    // Emit events for layers that have selections
    for (const [layerName, features] of byLayer.entries()) {
      const payload = {
        type: "select",
        layer: layerName,
        ids: features.map(f => f.getId()),
        features: features.map(f => ({
          id: f.getId(),
          lon: f.get("lon"),
          lat: f.get("lat"),
          z: f.get("z"),
          props: f.getProperties(),
        }))
      };
      state.bridge.emitEvent(JSON.stringify(payload));
    }

    // ALSO emit empty selection for vector layers with no selection
    for (const layerName of state.vectorSources.keys()) {
      if (!byLayer.has(layerName)) {
        state.bridge.emitEvent(JSON.stringify({
          type: "select",
          layer: layerName,
          ids: [],
          features: []
        }));
      }
    }
  }

  function setupSelectionInteraction() {
    state.select = new ol.interaction.Select({ layers: () => true });
    state.map.addInteraction(state.select);

    // Ctrl-click toggle / click single-select.
    state.map.on("click", (evt) => {
      const ctrl = evt.originalEvent.ctrlKey || evt.originalEvent.metaKey;
      const feature = state.map.forEachFeatureAtPixel(evt.pixel, f => f);

      if (!feature) {
        if (!ctrl) state.select.getFeatures().clear();
        // refresh styles for all vector layers
        for (const name of state.vectorSources.keys()) refreshVectorLayerStyle(name);
        emitSelection();
        return;
      }

      const selected = state.select.getFeatures();
      const arr = selected.getArray();
      const already = arr.includes(feature);

      if (!ctrl) {
        selected.clear();
        selected.push(feature);
      } else {
        if (already) selected.remove(feature);
        else selected.push(feature);
      }

      for (const name of state.vectorSources.keys()) refreshVectorLayerStyle(name);
      emitSelection();
    });

    // Ctrl-drag box add selection
    const dragBox = new ol.interaction.DragBox({
      condition: (evt) => (evt.originalEvent.ctrlKey || evt.originalEvent.metaKey)
    });
    state.map.addInteraction(dragBox);

    dragBox.on("boxend", () => {
      const extent = dragBox.getGeometry().getExtent();
      for (const [name, src] of state.vectorSources.entries()) {
        const hits = src.getFeaturesInExtent(extent);
        const selected = state.select.getFeatures();
        const current = new Set(selected.getArray());
        for (const f of hits) {
          if (!current.has(f)) selected.push(f);
        }
        refreshVectorLayerStyle(name);
      }
      emitSelection();
    });
  }

  function initMap() {
    ensureOl();

    const osmLayer = new ol.layer.Tile({ source: new ol.source.OSM() });

    state.map = new ol.Map({
      target: "map",
      layers: [osmLayer],
      view: new ol.View({
        center: ol.proj.fromLonLat([-104.9903, 39.7392]),
        zoom: 10
      })
    });

    setupSelectionInteraction();
    jsLog("OpenLayers map initialized");
  }

  function addPoints(cmd) {
    const name = cmd.layer;
    const data = cmd.data || [];
    const style = cmd.style || {};

    // Create vector source/layer if not exists
    let src = state.vectorSources.get(name);
    let layer = state.layers.get(name);
    if (!src) {
      src = new ol.source.Vector();
      layer = new ol.layer.Vector({ source: src });
      state.vectorSources.set(name, src);
      state.layers.set(name, layer);
      state.map.addLayer(layer);
    }

    const styles = makePointStyles(style);
    state.selectedStyleByLayer.set(name, styles);
    layer.setStyle(styles.def);

    for (const p of data) {
      const id = p.id;
      const f = new ol.Feature({
        geometry: new ol.geom.Point(ol.proj.fromLonLat([p.lon, p.lat])),
        lon: p.lon,
        lat: p.lat,
        z: p.z,
        __layer: name
      });
      f.setId(id);
      src.addFeature(f);
    }

    refreshVectorLayerStyle(name);
  }
  function makePolygonStyles(style) {
    const def = new ol.style.Style({
      fill: new ol.style.Fill({ color: rgba(style.fill ?? [0,120,255,80]) }),
      stroke: new ol.style.Stroke({ color: rgba(style.stroke ?? [0,120,255,200]), width: style.stroke_width ?? 2 })
    });

    const sel = new ol.style.Style({
      fill: new ol.style.Fill({ color: rgba(style.selected_fill ?? [255,50,50,90]) }),
      stroke: new ol.style.Stroke({ color: rgba(style.selected_stroke ?? [255,50,50,230]), width: style.selected_stroke_width ?? 2 })
    });

    return { def, sel };
  }

  function addGeoJSON(cmd) {
    const name = cmd.layer;
    const geojson = cmd.geojson;
    const style = cmd.style || {};
    const geomType = cmd.geom_type || "polygon"; // "polygon"|"line"|"point"
    const replace = cmd.replace ?? true;

    // Create vector source/layer if not exists
    let src = state.vectorSources.get(name);
    let layer = state.layers.get(name);
    if (!src) {
      src = new ol.source.Vector();
      layer = new ol.layer.Vector({ source: src });
      state.vectorSources.set(name, src);
      state.layers.set(name, layer);
      state.map.addLayer(layer);
    } else if (replace) {
      src.clear();
    }

    let styles;
    if (geomType === "polygon") styles = makePolygonStyles(style);
    else styles = makePointStyles(style); // fallback, ok for point/line MVP

    state.selectedStyleByLayer.set(name, styles);
    layer.setStyle(styles.def);

    const fmt = new ol.format.GeoJSON();
    const features = fmt.readFeatures(geojson, {
      featureProjection: state.map.getView().getProjection(),
      dataProjection: "EPSG:4326"
    });

    // attach layer name and ensure IDs are set
    for (const f of features) {
      f.set("__layer", name);
      // if id absent, try property "id"
      if (f.getId() == null && f.get("id") != null) f.setId(f.get("id"));
      src.addFeature(f);
    }

    refreshVectorLayerStyle(name);
  }


  function clearLayer(cmd) {
    const name = cmd.layer;
    const src = state.vectorSources.get(name);
    if (src) src.clear();
    // also clear selection for that layer
    const sel = state.select.getFeatures();
    const remaining = sel.getArray().filter(f => f.get("__layer") !== name);
    sel.clear();
    for (const f of remaining) sel.push(f);
    refreshVectorLayerStyle(name);
    emitSelection();
  }

  function removeLayer(cmd) {
    const name = cmd.layer;
    const layer = state.layers.get(name);
    if (layer) {
      state.map.removeLayer(layer);
      state.layers.delete(name);
    }
    state.vectorSources.delete(name);
    state.selectedStyleByLayer.delete(name);

    // clear selection for that layer
    const sel = state.select.getFeatures();
    const remaining = sel.getArray().filter(f => f.get("__layer") !== name);
    sel.clear();
    for (const f of remaining) sel.push(f);
    emitSelection();
  }

  function addWMS(cmd) {
    const name = cmd.layer;
    const url = cmd.url;
    const layers = cmd.layers;
    const opacity = cmd.opacity ?? 0.6;
    const visible = cmd.visible ?? true;
    const params = Object.assign({ "LAYERS": layers, "TILED": true }, cmd.params || {});

    const source = new ol.source.TileWMS({
      url,
      params,
      crossOrigin: "anonymous"
    });

    const wmsLayer = new ol.layer.Tile({
      source,
      opacity,
      visible
    });

    state.layers.set(name, wmsLayer);
    state.map.addLayer(wmsLayer);
  }

  function addImageOverlay(cmd) {
    const name = cmd.layer;
    const url = cmd.url;
    const extentLonLat = cmd.extent_lonlat; // [minlon,minlat,maxlon,maxlat]
    const opacity = cmd.opacity ?? 0.55;
    const visible = cmd.visible ?? true;

    const imageExtent = to3857ExtentFromLonLat(extentLonLat);

    const src = new ol.source.ImageStatic({
      url,
      imageExtent,
      projection: state.map.getView().getProjection()
    });

    const layer = new ol.layer.Image({
      source: src,
      opacity,
      visible
    });

    state.layers.set(name, layer);
    state.map.addLayer(layer);
  }

  function setOpacity(cmd) {
    const layer = state.layers.get(cmd.layer);
    if (layer) layer.setOpacity(cmd.opacity);
  }

  function setVisible(cmd) {
    const layer = state.layers.get(cmd.layer);
    if (layer) layer.setVisible(!!cmd.visible);
  }

  function fitToExtent(cmd) {
    const extLonLat = cmd.extent_lonlat;
    const ext3857 = to3857ExtentFromLonLat(extLonLat);
    state.map.getView().fit(ext3857, { padding: [30, 30, 30, 30], duration: 200 });
  }

  function setSelectedIds(cmd) {
    const layerName = cmd.layer;
    const ids = (cmd.ids || []).map(x => String(x));
    const idSet = new Set(ids);

    const sel = state.select.getFeatures();
    // remove existing from that layer
    const keep = sel.getArray().filter(f => f.get("__layer") !== layerName);
    sel.clear();
    for (const f of keep) sel.push(f);

    const src = state.vectorSources.get(layerName);
    if (src) {
      for (const f of src.getFeatures()) {
        if (idSet.has(String(f.getId()))) sel.push(f);
      }
    }

    refreshVectorLayerStyle(layerName);
    emitSelection();
  }

  function apply(cmd) {
    try {
      switch (cmd.op) {
        case "add_points": return addPoints(cmd);
        case "clear_layer": return clearLayer(cmd);
        case "remove_layer": return removeLayer(cmd);
        case "add_wms": return addWMS(cmd);
        case "add_image_overlay": return addImageOverlay(cmd);
        case "set_opacity": return setOpacity(cmd);
        case "set_visible": return setVisible(cmd);
        case "fit_to_extent": return fitToExtent(cmd);
        case "set_selected_ids": return setSelectedIds(cmd);
        case "add_geojson": return addGeoJSON(cmd);
        default:
          jsLog("Unknown op: " + cmd.op);
      }
    } catch (e) {
      console.error(e);
      jsLog("ERROR: " + e.message);
      if (state.bridge && state.bridge.emitEvent) {
        state.bridge.emitEvent(JSON.stringify({ type: "error", message: e.message, detail: String(e) }));
      }
    }
  }

  // Expose one API
  window.__ol_bridge = { apply };

  // Connect QWebChannel then init map
  new QWebChannel(qt.webChannelTransport, function (channel) {
    state.bridge = channel.objects.bridge;
    jsLog("QWebChannel connected (JS side)");
    initMap();
  });
})();

