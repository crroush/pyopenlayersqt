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

import sys

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from pyopenlayersqt import (
    OLMapWidget,
    WMSOptions,
    TileLayerOptions,
    PointStyle,
)


class WMSExample(QtWidgets.QMainWindow):
    """WMS + tile layer management example window."""

    DEFAULT_OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    ALT_OSM_URL = "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
    AWS_TERRAIN_URL = "https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("WMS + Managed Tile Layers (OSM/AWS Terrain)")
        self.resize(1200, 800)

        self.map_widget = None
        self.wms_layer = None
        self.tile_layer = None

        # Layout
        container = QtWidgets.QWidget()
        self.layout = QtWidgets.QVBoxLayout(container)
        self.controls = self._create_controls()
        self.layout.addWidget(self.controls)
        self.setCentralWidget(container)

        # Create map centered on US (to show WMS layer)
        self._create_map_widget(osm_url=self.DEFAULT_OSM_URL)

    def _create_controls(self):
        """Create control panel for WMS and base layer."""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(panel)

        # Generic tile layer controls
        osm_group = QtWidgets.QGroupBox("Generic Tile Layer URL")
        osm_layout = QtWidgets.QHBoxLayout(osm_group)
        osm_layout.addWidget(QtWidgets.QLabel("URL:"))

        self.osm_url_input = QtWidgets.QLineEdit(self.DEFAULT_OSM_URL)
        self.osm_url_input.setMinimumWidth(420)
        self.osm_url_input.setPlaceholderText(self.DEFAULT_OSM_URL)
        osm_layout.addWidget(self.osm_url_input)

        use_alt_btn = QtWidgets.QPushButton("Use Alt OSM URL")
        use_alt_btn.clicked.connect(lambda: self.osm_url_input.setText(self.ALT_OSM_URL))
        osm_layout.addWidget(use_alt_btn)

        use_aws_btn = QtWidgets.QPushButton("Use AWS Terrain Template")
        use_aws_btn.clicked.connect(
            lambda: self.osm_url_input.setText(self.AWS_TERRAIN_URL)
        )
        osm_layout.addWidget(use_aws_btn)

        apply_btn = QtWidgets.QPushButton("Apply to Generic Tile Layer")
        apply_btn.clicked.connect(self._on_apply_tile_url)
        osm_layout.addWidget(apply_btn)

        self.tile_visible_cb = QtWidgets.QCheckBox("Visible")
        self.tile_visible_cb.setChecked(True)
        self.tile_visible_cb.toggled.connect(self._on_tile_visible_changed)
        osm_layout.addWidget(self.tile_visible_cb)

        layout.addWidget(osm_group)

        # WMS controls
        wms_group = QtWidgets.QGroupBox("WMS Controls")
        wms_layout = QtWidgets.QHBoxLayout(wms_group)
        wms_layout.addWidget(QtWidgets.QLabel("Layer:"))
        self.wms_combo = QtWidgets.QComboBox()
        self.wms_combo.addItem("US States (topp:states)", "topp:states")
        self.wms_combo.addItem("Tasmania Water Bodies (topp:tasmania_water_bodies)", "topp:tasmania_water_bodies")
        self.wms_combo.currentIndexChanged.connect(self._on_wms_layer_changed)
        wms_layout.addWidget(self.wms_combo)

        self.wms_visible_cb = QtWidgets.QCheckBox("Visible")
        self.wms_visible_cb.setChecked(True)
        self.wms_visible_cb.toggled.connect(self._on_wms_visible_changed)
        wms_layout.addWidget(self.wms_visible_cb)

        wms_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        self.wms_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.wms_slider.setRange(0, 100)
        self.wms_slider.setValue(70)
        self.wms_slider.valueChanged.connect(self._on_wms_opacity_changed)
        wms_layout.addWidget(self.wms_slider)
        self.wms_label = QtWidgets.QLabel("0.70")
        wms_layout.addWidget(self.wms_label)
        layout.addWidget(wms_group)

        # Generic tile layer opacity control
        tile_group = QtWidgets.QGroupBox("Generic Tile Layer Opacity")
        tile_layout = QtWidgets.QHBoxLayout(tile_group)
        tile_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        self.tile_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.tile_slider.setRange(0, 100)
        self.tile_slider.setValue(60)
        self.tile_slider.valueChanged.connect(self._on_tile_opacity_changed)
        tile_layout.addWidget(self.tile_slider)
        self.tile_label = QtWidgets.QLabel("0.60")
        tile_layout.addWidget(self.tile_label)
        layout.addWidget(tile_group)

        # Base layer opacity / visibility control
        base_group = QtWidgets.QGroupBox("OpenStreetMap Base Layer Opacity")
        base_layout = QtWidgets.QHBoxLayout(base_group)
        self.base_visible_cb = QtWidgets.QCheckBox("Visible")
        self.base_visible_cb.setChecked(True)
        self.base_visible_cb.toggled.connect(self._on_base_visible_changed)
        base_layout.addWidget(self.base_visible_cb)
        base_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        self.base_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.base_slider.setRange(0, 100)
        self.base_slider.setValue(100)
        self.base_slider.valueChanged.connect(self._on_base_opacity_changed)
        base_layout.addWidget(self.base_slider)
        self.base_label = QtWidgets.QLabel("1.00")
        base_layout.addWidget(self.base_label)
        layout.addWidget(base_group)

        layout.addStretch(1)
        return panel


    def _create_map_widget(self, osm_url: str):
        """Create (or recreate) the map widget with an OSM URL."""
        if self.map_widget is not None:
            self.layout.removeWidget(self.map_widget)
            self.map_widget.deleteLater()
            self.map_widget = None
            self.wms_layer = None

        self.map_widget = OLMapWidget(center=(39.0, -98.0), zoom=4, osm_url=osm_url)
        self.layout.addWidget(self.map_widget, stretch=1)

        # Add a WMS layer (using a public demo server)
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
        # Add a managed generic tile layer (overlays above base OSM)
        self.tile_layer = self.map_widget.add_tile_layer(
            TileLayerOptions(
                url=self.osm_url_input.text().strip() or self.DEFAULT_OSM_URL,
                opacity=self.tile_slider.value() / 100.0,
                attribution="Managed generic tile layer",
            ),
            name="generic_tile",
        )

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
