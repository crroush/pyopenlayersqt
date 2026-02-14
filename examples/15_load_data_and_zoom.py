#!/usr/bin/env python3
"""Load Data and Zoom Example

This example demonstrates the one-call auto-zoom workflow:
1. Load data into map layers
2. Click a button to zoom to all loaded data via ``fit_to_data()``

Use this to quickly validate the feature-driven auto-zoom behavior.
"""

import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, PointStyle


class FitToDataExample(QtWidgets.QMainWindow):
    """Example window for testing fit_to_data()."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Load Data and Zoom Example")
        self.resize(1200, 800)

        self.map_widget = OLMapWidget(center=(20.0, 0.0), zoom=2)
        self.vector_layer = self.map_widget.add_vector_layer("loaded_features", selectable=True)

        self._loaded = False
        self._build_ui()

    def _build_ui(self) -> None:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)

        controls = QtWidgets.QHBoxLayout()

        load_btn = QtWidgets.QPushButton("Load Sample Data")
        load_btn.clicked.connect(self._load_data)
        controls.addWidget(load_btn)

        zoom_btn = QtWidgets.QPushButton("Zoom to Loaded Data")
        zoom_btn.clicked.connect(self._zoom_to_data)
        controls.addWidget(zoom_btn)

        reset_btn = QtWidgets.QPushButton("Reset to World View")
        reset_btn.clicked.connect(lambda: self.map_widget.set_view(center=(20.0, 0.0), zoom=2))
        controls.addWidget(reset_btn)

        controls.addStretch()

        self.status = QtWidgets.QLabel("Click 'Load Sample Data', then 'Zoom to Loaded Data'.")
        controls.addWidget(self.status)

        layout.addLayout(controls)
        layout.addWidget(self.map_widget, stretch=1)
        self.setCentralWidget(container)

    def _load_data(self) -> None:
        """Load two distant clusters so fit behavior is obvious."""
        self.vector_layer.clear()

        # US West cluster
        west_points = [
            (37.7749, -122.4194),  # San Francisco
            (34.0522, -118.2437),  # Los Angeles
            (47.6062, -122.3321),  # Seattle
        ]

        # Europe cluster
        europe_points = [
            (51.5074, -0.1278),    # London
            (48.8566, 2.3522),     # Paris
            (52.5200, 13.4050),    # Berlin
        ]

        self.vector_layer.add_points(
            west_points,
            ids=["sf", "la", "sea"],
            style=PointStyle(
                radius=8.0,
                fill_color=QColor("tomato"),
                stroke_color=QColor("black"),
                stroke_width=1.5,
            ),
        )

        self.vector_layer.add_points(
            europe_points,
            ids=["lon", "par", "ber"],
            style=PointStyle(
                radius=8.0,
                fill_color=QColor("royalblue"),
                stroke_color=QColor("black"),
                stroke_width=1.5,
            ),
        )

        self._loaded = True
        self.status.setText("Data loaded: 6 points across two regions.")

    def _zoom_to_data(self) -> None:
        """Fit map to all loaded layer data."""
        if not self._loaded:
            self.status.setText("Load data first.")
            return

        self.map_widget.fit_to_data(padding_px=48, max_zoom=6, duration_ms=250)
        self.status.setText("Applied fit_to_data() across loaded map layers.")


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = FitToDataExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
