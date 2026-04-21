#!/usr/bin/env python3
"""WMS + OSM + Terrain layers together, with URL/opacity controls.

This example demonstrates:
- Adding WMS (Web Map Service) layers to overlay data
- Keeping OpenStreetMap and WMS enabled while adding terrain tiles as another layer
- Changing OSM base URL and terrain URL from the GUI
- Layer visibility and opacity controls
- Using public WMS endpoints

WMS allows you to overlay external map data sources onto your map.
"""

import sys

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, WMSOptions, XYZTileOptions, PointStyle


class WMSExample(QtWidgets.QMainWindow):
    """WMS and base layer opacity example window."""

    DEFAULT_OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    ALT_OSM_URL = "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
    AWS_TERRAIN_URL = "https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("WMS Layer, Base Layer Opacity, and Tile URL Override")
        self.resize(1200, 800)

        self.map_widget = None
        self.wms_layer = None
        self.terrain_layer = None

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

        # Base tile URL controls
        osm_group = QtWidgets.QGroupBox("OSM Base URL Override")
        osm_layout = QtWidgets.QHBoxLayout(osm_group)
        osm_layout.addWidget(QtWidgets.QLabel("URL:"))

        self.osm_url_input = QtWidgets.QLineEdit(self.DEFAULT_OSM_URL)
        self.osm_url_input.setMinimumWidth(420)
        self.osm_url_input.setPlaceholderText(self.DEFAULT_OSM_URL)
        osm_layout.addWidget(self.osm_url_input)

        use_alt_btn = QtWidgets.QPushButton("Use Alt OSM URL")
        use_alt_btn.clicked.connect(lambda: self.osm_url_input.setText(self.ALT_OSM_URL))
        osm_layout.addWidget(use_alt_btn)

        apply_btn = QtWidgets.QPushButton("Apply URL")
        apply_btn.clicked.connect(self._on_apply_osm_url)
        osm_layout.addWidget(apply_btn)

        layout.addWidget(osm_group)

        # Terrain controls
        terrain_group = QtWidgets.QGroupBox("Terrain Tile Layer")
        terrain_layout = QtWidgets.QHBoxLayout(terrain_group)
        self.terrain_enabled = QtWidgets.QCheckBox("Enabled")
        self.terrain_enabled.setChecked(True)
        self.terrain_enabled.toggled.connect(self._on_terrain_enabled_changed)
        terrain_layout.addWidget(self.terrain_enabled)

        terrain_layout.addWidget(QtWidgets.QLabel("URL:"))
        self.terrain_url_input = QtWidgets.QLineEdit(self.AWS_TERRAIN_URL)
        self.terrain_url_input.setMinimumWidth(420)
        terrain_layout.addWidget(self.terrain_url_input)

        apply_terrain_btn = QtWidgets.QPushButton("Apply Terrain URL")
        apply_terrain_btn.clicked.connect(self._on_apply_terrain_url)
        terrain_layout.addWidget(apply_terrain_btn)
        layout.addWidget(terrain_group)

        # WMS opacity control
        wms_group = QtWidgets.QGroupBox("WMS Layer Opacity")
        wms_layout = QtWidgets.QHBoxLayout(wms_group)
        wms_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        self.wms_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.wms_slider.setRange(0, 100)
        self.wms_slider.setValue(70)
        self.wms_slider.valueChanged.connect(self._on_wms_opacity_changed)
        wms_layout.addWidget(self.wms_slider)
        self.wms_label = QtWidgets.QLabel("0.70")
        wms_layout.addWidget(self.wms_label)
        layout.addWidget(wms_group)

        # Base layer opacity control
        base_group = QtWidgets.QGroupBox("OpenStreetMap Base Layer Opacity")
        base_layout = QtWidgets.QHBoxLayout(base_group)
        base_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        self.base_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.base_slider.setRange(0, 100)
        self.base_slider.setValue(100)
        self.base_slider.valueChanged.connect(self._on_base_opacity_changed)
        base_layout.addWidget(self.base_slider)
        self.base_label = QtWidgets.QLabel("1.00")
        base_layout.addWidget(self.base_label)
        layout.addWidget(base_group)

        terrain_opacity_group = QtWidgets.QGroupBox("Terrain Layer Opacity")
        terrain_opacity_layout = QtWidgets.QHBoxLayout(terrain_opacity_group)
        terrain_opacity_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        self.terrain_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.terrain_slider.setRange(0, 100)
        self.terrain_slider.setValue(70)
        self.terrain_slider.valueChanged.connect(self._on_terrain_opacity_changed)
        terrain_opacity_layout.addWidget(self.terrain_slider)
        self.terrain_label = QtWidgets.QLabel("0.70")
        terrain_opacity_layout.addWidget(self.terrain_label)
        layout.addWidget(terrain_opacity_group)

        layout.addStretch(1)
        return panel


    def _create_map_widget(self, osm_url: str):
        """Create (or recreate) the map widget with an OSM URL."""
        if self.map_widget is not None:
            self.layout.removeWidget(self.map_widget)
            self.map_widget.deleteLater()
            self.map_widget = None
            self.wms_layer = None
            self.terrain_layer = None

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
        self._add_or_replace_terrain_layer()

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

    def _on_apply_osm_url(self):
        """Apply OSM URL by recreating the map widget."""
        osm_url = self.osm_url_input.text().strip() or self.DEFAULT_OSM_URL
        self._create_map_widget(osm_url=osm_url)

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

    def _add_or_replace_terrain_layer(self):
        if self.terrain_layer:
            self.terrain_layer.remove()
            self.terrain_layer = None
        if not self.terrain_enabled.isChecked():
            return

        terrain_url = self.terrain_url_input.text().strip() or self.AWS_TERRAIN_URL
        terrain_opt = XYZTileOptions(
            url=terrain_url,
            opacity=self.terrain_slider.value() / 100.0,
            min_zoom=0,
            max_zoom=15,
            attribution="Mapzen terrain tiles (AWS Open Data)",
        )
        self.terrain_layer = self.map_widget.add_xyz_tiles(terrain_opt, name="terrain")

    def _on_apply_terrain_url(self):
        self._add_or_replace_terrain_layer()

    def _on_terrain_enabled_changed(self, _checked: bool):
        self._add_or_replace_terrain_layer()

    def _on_terrain_opacity_changed(self, value: int):
        opacity = value / 100.0
        self.terrain_label.setText(f"{opacity:.2f}")
        if self.terrain_layer:
            self.terrain_layer.set_opacity(opacity)


def main():
    """Run the WMS and base layer opacity example."""
    app = QtWidgets.QApplication(sys.argv)
    window = WMSExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
