#!/usr/bin/env python3
"""WMS Layer and Base Layer Opacity

This example demonstrates:
- Adding WMS (Web Map Service) layers to overlay data
- Adjusting OpenStreetMap base layer opacity
- Layer visibility and opacity controls
- Using public WMS endpoints

WMS allows you to overlay external map data sources onto your map.
"""

import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, WMSOptions, PointStyle


class WMSExample(QtWidgets.QMainWindow):
    """WMS and base layer opacity example window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("WMS Layer and Base Layer Opacity")
        self.resize(1200, 800)

        # Create map centered on US (to show WMS layer)
        self.map_widget = OLMapWidget(center=(39.0, -98.0), zoom=4)

        # Add a WMS layer (using a public demo server)
        # This shows US state boundaries
        wms_options = WMSOptions(
            url="https://ahocevar.com/geoserver/wms",
            params={
                "LAYERS": "topp:states",
                "FORMAT": "image/png",
                "TRANSPARENT": "TRUE",
            },
            opacity=0.7
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
                    stroke_width=2.0
                )
            )

        # Create control panel
        controls = self._create_controls()

        # Layout
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(controls)
        layout.addWidget(self.map_widget, stretch=1)
        self.setCentralWidget(container)

    def _create_controls(self):
        """Create control panel for WMS and base layer."""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(panel)

        # WMS opacity control
        wms_group = QtWidgets.QGroupBox("WMS Layer Opacity")
        wms_layout = QtWidgets.QHBoxLayout(wms_group)
        wms_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        self.wms_slider = QtWidgets.QSlider(QtWidgets.Qt.Horizontal)
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
        self.base_slider = QtWidgets.QSlider(QtWidgets.Qt.Horizontal)
        self.base_slider.setRange(0, 100)
        self.base_slider.setValue(100)
        self.base_slider.valueChanged.connect(self._on_base_opacity_changed)
        base_layout.addWidget(self.base_slider)
        self.base_label = QtWidgets.QLabel("1.00")
        base_layout.addWidget(self.base_label)
        layout.addWidget(base_group)

        layout.addStretch(1)
        return panel

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


def main():
    """Run the WMS and base layer opacity example."""
    app = QtWidgets.QApplication(sys.argv)
    window = WMSExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
