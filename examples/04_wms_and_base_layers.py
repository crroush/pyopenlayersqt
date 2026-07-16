#!/usr/bin/env python3
"""WMS + managed tile layers (including OSM/AWS Terrain) example.

This example demonstrates:
- Adding WMS (Web Map Service) layers to overlay data
- Switching between multiple WMS datasets
- Adding and managing a generic tile layer (XYZ/OSM style URLs)
- Adjusting opacity and visibility for base/WMS/generic tile layers
- Using public WMS endpoints

WMS allows you to overlay external map data sources onto your map.
"""

import json
import sys
import urllib.request

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

from pyopenlayersqt import (
    OLMapWidget,
    WMSOptions,
    TileLayerOptions,
    PointStyle,
)


class WMSExample(QtWidgets.QMainWindow):
    """Professional layer manager demo for base OSM + tile + WMS."""

    DEFAULT_OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    ALT_OSM_URL = "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
    # AWS Terrain Tiles publish multiple encodings. Terrarium is raw elevation
    # encoded into RGB channels and is not intended to look like a shaded map
    # without client-side decoding/styling. Normal is the processed PNG variant
    # that OpenLayers can display directly as a terrain-shaded raster layer.
    AWS_TERRAIN_NORMAL_URL = (
        "https://elevation-tiles-prod.s3.amazonaws.com/normal/{z}/{x}/{y}.png"
    )
    AWS_TERRAIN_TERRARIUM_URL = (
        "https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png"
    )

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Layer Manager: OSM + Generic Tile + WMS")
        self.resize(1200, 800)

        self.map_widget = None
        self.wms_layer = None
        self.tile_layer = None
        self.altitude_label = None
        self._terrain_tile_cache = {}

        # Layout
        container = QtWidgets.QWidget()
        self.layout = QtWidgets.QVBoxLayout(container)
        self.controls = self._create_controls()
        self.layout.addWidget(self.controls)
        self.setCentralWidget(container)

        # Create map centered on US (to show WMS layer)
        self._create_map_widget(osm_url=self.DEFAULT_OSM_URL)

    def _create_controls(self):
        """Create a consistent, professional layer manager control panel."""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)

        # Top row: tile URL and presets
        tile_url_group = QtWidgets.QGroupBox("Generic Tile Source")
        tile_url_layout = QtWidgets.QHBoxLayout(tile_url_group)
        tile_url_layout.addWidget(QtWidgets.QLabel("URL:"))

        self.osm_url_input = QtWidgets.QLineEdit(self.DEFAULT_OSM_URL)
        self.osm_url_input.setMinimumWidth(420)
        self.osm_url_input.setPlaceholderText(self.DEFAULT_OSM_URL)
        tile_url_layout.addWidget(self.osm_url_input, stretch=1)

        self.tile_preset_combo = QtWidgets.QComboBox()
        self.tile_preset_combo.addItem("OpenStreetMap", self.DEFAULT_OSM_URL)
        self.tile_preset_combo.addItem("Alt OpenStreetMap", self.ALT_OSM_URL)
        self.tile_preset_combo.addItem(
            "AWS Terrain (normal/display)",
            self.AWS_TERRAIN_NORMAL_URL,
        )
        self.tile_preset_combo.currentIndexChanged.connect(self._on_tile_preset_changed)
        tile_url_layout.addWidget(self.tile_preset_combo)

        apply_btn = QtWidgets.QPushButton("Apply to Generic Tile Layer")
        apply_btn.clicked.connect(self._on_apply_tile_url)
        tile_url_layout.addWidget(apply_btn)
        terrain_note = QtWidgets.QLabel(
            "AWS Terrain: use the normal/display preset for direct rendering. "
            "The cursor altitude readout decodes Terrarium RGB tiles separately."
        )
        terrain_note.setWordWrap(True)
        layout.addWidget(terrain_note)
        layout.addWidget(tile_url_group)

        self.altitude_label = QtWidgets.QLabel(
            "Terrain altitude under cursor: move over the map"
        )
        layout.addWidget(self.altitude_label)

        # Middle row: WMS source
        wms_group = QtWidgets.QGroupBox("WMS Source")
        wms_layout = QtWidgets.QHBoxLayout(wms_group)
        wms_layout.addWidget(QtWidgets.QLabel("Dataset:"))
        self.wms_combo = QtWidgets.QComboBox()
        self.wms_combo.addItem("US States (topp:states)", "topp:states")
        self.wms_combo.addItem(
            "Tasmania Water Bodies (topp:tasmania_water_bodies)",
            "topp:tasmania_water_bodies",
        )
        self.wms_combo.currentIndexChanged.connect(self._on_wms_layer_changed)
        wms_layout.addWidget(self.wms_combo, stretch=1)
        layout.addWidget(wms_group)

        # Bottom row: unified layer list with visibility + per-layer opacity
        layers_group = QtWidgets.QGroupBox("Layers")
        layers_layout = QtWidgets.QGridLayout(layers_group)
        layers_layout.addWidget(QtWidgets.QLabel("Layer"), 0, 0)
        layers_layout.addWidget(QtWidgets.QLabel("Visible"), 0, 1)
        layers_layout.addWidget(QtWidgets.QLabel("Opacity"), 0, 2)
        layers_layout.addWidget(QtWidgets.QLabel("Value"), 0, 3)

        # Base OSM row
        layers_layout.addWidget(QtWidgets.QLabel("Base OSM"), 1, 0)
        self.base_visible_cb = QtWidgets.QCheckBox()
        self.base_visible_cb.setChecked(True)
        self.base_visible_cb.toggled.connect(self._on_base_visible_changed)
        layers_layout.addWidget(self.base_visible_cb, 1, 1)
        self.base_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.base_slider.setRange(0, 100)
        self.base_slider.setValue(100)
        self.base_slider.valueChanged.connect(self._on_base_opacity_changed)
        layers_layout.addWidget(self.base_slider, 1, 2)
        self.base_label = QtWidgets.QLabel("1.00")
        layers_layout.addWidget(self.base_label, 1, 3)

        # Generic tile row
        layers_layout.addWidget(QtWidgets.QLabel("Generic Tile"), 2, 0)
        self.tile_visible_cb = QtWidgets.QCheckBox()
        self.tile_visible_cb.setChecked(True)
        self.tile_visible_cb.toggled.connect(self._on_tile_visible_changed)
        layers_layout.addWidget(self.tile_visible_cb, 2, 1)
        self.tile_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.tile_slider.setRange(0, 100)
        self.tile_slider.setValue(60)
        self.tile_slider.valueChanged.connect(self._on_tile_opacity_changed)
        layers_layout.addWidget(self.tile_slider, 2, 2)
        self.tile_label = QtWidgets.QLabel("0.60")
        layers_layout.addWidget(self.tile_label, 2, 3)

        # WMS row
        layers_layout.addWidget(QtWidgets.QLabel("WMS Overlay"), 3, 0)
        self.wms_visible_cb = QtWidgets.QCheckBox()
        self.wms_visible_cb.setChecked(True)
        self.wms_visible_cb.toggled.connect(self._on_wms_visible_changed)
        layers_layout.addWidget(self.wms_visible_cb, 3, 1)
        self.wms_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.wms_slider.setRange(0, 100)
        self.wms_slider.setValue(70)
        self.wms_slider.valueChanged.connect(self._on_wms_opacity_changed)
        layers_layout.addWidget(self.wms_slider, 3, 2)
        self.wms_label = QtWidgets.QLabel("0.70")
        layers_layout.addWidget(self.wms_label, 3, 3)

        layout.addWidget(layers_group)
        return panel


    def _create_map_widget(self, osm_url: str):
        """Create (or recreate) the map widget with an OSM URL."""
        if self.map_widget is not None:
            self.layout.removeWidget(self.map_widget)
            self.map_widget.deleteLater()
            self.map_widget = None
            self.wms_layer = None

        self.map_widget = OLMapWidget(center=(39.0, -98.0), zoom=4, osm_url=osm_url)
        self.map_widget.ready.connect(self._install_altitude_probe)
        self.map_widget.jsEvent.connect(self._on_map_js_event)
        self.layout.addWidget(self.map_widget, stretch=1)

        # Add managed generic tile layer first so WMS can be rendered above it.
        self.tile_layer = self.map_widget.add_tile_layer(
            TileLayerOptions(
                url=self.osm_url_input.text().strip() or self.DEFAULT_OSM_URL,
                opacity=self.tile_slider.value() / 100.0,
                attribution="Managed generic tile layer",
            ),
            name="generic_tile",
        )
        # Add a WMS layer (using a public demo server) above the generic tile layer.
        wms_options = WMSOptions(
            url="https://ahocevar.com/geoserver/wms",
            params={
                "LAYERS": "topp:states",
                "FORMAT": "image/png",
                "TRANSPARENT": "TRUE",
            },
            opacity=self.wms_slider.value() / 100.0,
        )
        self.wms_layer = self.map_widget.add_wms(wms_options, name="us_states")

        # Add some reference points
        vector_layer = self.map_widget.add_vector_layer("markers", selectable=False)
        capitals = [
            (38.9072, -77.0369, "Washington DC"),
            (33.4484, -112.0740, "Phoenix"),
            (39.7392, -104.9903, "Denver"),
        ]
        for lat, lon, name in capitals:
            vector_layer.add_points(
                [(lat, lon)],
                ids=[name],
                style=PointStyle(
                    radius=8.0,
                    fill_color=QColor("red"),
                    stroke_color=QColor("darkred"),
                    stroke_width=2.0,
                ),
            )

        self.map_widget.set_base_opacity(self.base_slider.value() / 100.0)
        self.map_widget.set_base_visible(self.base_visible_cb.isChecked())
        self.wms_layer.set_visible(self.wms_visible_cb.isChecked())
        self.tile_layer.set_visible(self.tile_visible_cb.isChecked())

    def _install_altitude_probe(self):
        """Install a cursor probe that reports tile/pixel coordinates to Python."""
        if not self.map_widget:
            return
        js = """
(() => {
  const state = window._pyolqt_state;
  if (!state || !state.map || state.awsTerrainAltitudeProbeInstalled) return;
  state.awsTerrainAltitudeProbeInstalled = true;
  const tileSize = 256;

  function lonLatToTile(lon, lat, z) {
    const n = Math.pow(2, z);
    const latRad = lat * Math.PI / 180;
    const xFloat = (lon + 180) / 360 * n;
    const yFloat = (1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2 * n;
    const x = Math.floor(xFloat);
    const y = Math.floor(yFloat);
    return {
      z, x, y,
      px: Math.max(0, Math.min(tileSize - 1, Math.floor((xFloat - x) * tileSize))),
      py: Math.max(0, Math.min(tileSize - 1, Math.floor((yFloat - y) * tileSize))),
    };
  }

  let lastUpdate = 0;
  state.map.on('pointermove', (evt) => {
    const now = Date.now();
    if (now - lastUpdate < 250) return;
    lastUpdate = now;
    const lonLat = ol.proj.toLonLat(evt.coordinate);
    const z = Math.max(0, Math.min(15, Math.round(state.map.getView().getZoom() || 0)));
    const tile = lonLatToTile(lonLat[0], lonLat[1], z);
    if (state.qtBridge && typeof state.qtBridge.emitEvent === 'function') {
      state.qtBridge.emitEvent('terrain_probe_request', JSON.stringify({
        lat: lonLat[1],
        lon: lonLat[0],
        z: tile.z,
        x: tile.x,
        y: tile.y,
        px: tile.px,
        py: tile.py,
      }));
    }
  });
})();
"""
        self.map_widget.page().runJavaScript(js)

    def _terrain_tile_url(self, z, x, y):
        """Build the AWS Terrarium URL used for elevation lookups only."""
        return (
            self.AWS_TERRAIN_TERRARIUM_URL.replace("{z}", str(z))
            .replace("{x}", str(x))
            .replace("{y}", str(y))
        )

    def _get_terrain_tile(self, z, x, y):
        """Fetch and cache a Terrarium tile in Python to avoid browser CORS limits."""
        key = (int(z), int(x), int(y))
        image = self._terrain_tile_cache.get(key)
        if image is not None:
            return image

        request = urllib.request.Request(
            self._terrain_tile_url(*key),
            headers={"User-Agent": "pyopenlayersqt-example/terrain-altitude"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            data = response.read()
        image = QImage.fromData(data, "PNG")
        if image.isNull():
            raise ValueError("AWS Terrarium tile did not decode as PNG")
        self._terrain_tile_cache[key] = image
        if len(self._terrain_tile_cache) > 256:
            self._terrain_tile_cache.pop(next(iter(self._terrain_tile_cache)))
        return image

    def _read_terrain_altitude(self, payload):
        """Decode meters from a Terrarium RGB pixel."""
        image = self._get_terrain_tile(payload["z"], payload["x"], payload["y"])
        color = image.pixelColor(int(payload["px"]), int(payload["py"]))
        return (color.red() * 256 + color.green() + color.blue() / 256.0) - 32768

    def _on_map_js_event(self, event_type, payload_json):
        """Decode AWS Terrain altitude requests from map cursor movement."""
        if event_type != "terrain_probe_request" or not self.altitude_label:
            return
        try:
            payload = json.loads(payload_json or "{}")
            meters = self._read_terrain_altitude(payload)
        except (KeyError, TypeError, ValueError, OSError, TimeoutError) as err:
            self.altitude_label.setText(
                f"Terrain altitude under cursor: unavailable ({err})"
            )
            return

        self.altitude_label.setText(
            "Terrain altitude under cursor: "
            f"{meters:.1f} m at "
            f"{payload['lat']:.5f}, {payload['lon']:.5f}"
        )

    def _on_tile_preset_changed(self, _index):
        """Copy the selected tile preset URL into the editable URL field."""
        self.osm_url_input.setText(self.tile_preset_combo.currentData())

    def _on_apply_tile_url(self):
        """Apply URL to managed generic tile layer."""
        url = self.osm_url_input.text().strip() or self.DEFAULT_OSM_URL
        if self.tile_layer:
            self.tile_layer.set_url(url)

    def _on_wms_layer_changed(self, _index):
        """Switch WMS dataset via set_params."""
        if not self.wms_layer:
            return
        layer_name = self.wms_combo.currentData()
        self.wms_layer.set_params(
            {
                "LAYERS": layer_name,
                "FORMAT": "image/png",
                "TRANSPARENT": "TRUE",
            }
        )

    def _on_wms_opacity_changed(self, value):
        """Update WMS layer opacity."""
        opacity = value / 100.0
        self.wms_label.setText(f"{opacity:.2f}")
        if self.wms_layer:
            self.wms_layer.set_opacity(opacity)

    def _on_base_opacity_changed(self, value):
        """Update base layer opacity."""
        opacity = value / 100.0
        self.base_label.setText(f"{opacity:.2f}")
        self.map_widget.set_base_opacity(opacity)

    def _on_tile_opacity_changed(self, value):
        """Update generic tile layer opacity."""
        opacity = value / 100.0
        self.tile_label.setText(f"{opacity:.2f}")
        if self.tile_layer:
            self.tile_layer.set_opacity(opacity)

    def _on_wms_visible_changed(self, visible):
        if self.wms_layer:
            self.wms_layer.set_visible(bool(visible))

    def _on_base_visible_changed(self, visible):
        self.map_widget.set_base_visible(bool(visible))

    def _on_tile_visible_changed(self, visible):
        if self.tile_layer:
            self.tile_layer.set_visible(bool(visible))


def main():
    """Run the WMS and base layer opacity example."""
    app = QtWidgets.QApplication(sys.argv)
    window = WMSExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
