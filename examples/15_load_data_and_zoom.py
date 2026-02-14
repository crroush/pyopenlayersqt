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

        self.map_widget = OLMapWidget(center=(36.8, -119.4), zoom=5)
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

        reset_btn = QtWidgets.QPushButton("Reset to California View")
        reset_btn.clicked.connect(lambda: self.map_widget.set_view(center=(36.8, -119.4), zoom=5))
        controls.addWidget(reset_btn)

        controls.addStretch()

        self.status = QtWidgets.QLabel("Click 'Load Sample Data', then 'Zoom to Loaded Data'.")
        controls.addWidget(self.status)

        layout.addLayout(controls)
        layout.addWidget(self.map_widget, stretch=1)
        self.setCentralWidget(container)

    def _load_data(self) -> None:
        """Load California-only points so fit behavior is easy to verify."""
        self.vector_layer.clear()

        # Northern/Central California
        north_central_points = [
            (37.7749, -122.4194),  # San Francisco
            (38.5816, -121.4944),  # Sacramento
            (36.7378, -119.7871),  # Fresno
        ]

        # Southern California
        south_points = [
            (34.0522, -118.2437),  # Los Angeles
            (32.7157, -117.1611),  # San Diego
            (33.7455, -117.8677),  # Anaheim
        ]

        self.vector_layer.add_points(
            north_central_points,
            ids=["sf", "sac", "fre"],
            style=PointStyle(
                radius=8.0,
                fill_color=QColor("tomato"),
                stroke_color=QColor("black"),
                stroke_width=1.5,
            ),
        )

        self.vector_layer.add_points(
            south_points,
            ids=["la", "sd", "ana"],
            style=PointStyle(
                radius=8.0,
                fill_color=QColor("royalblue"),
                stroke_color=QColor("black"),
                stroke_width=1.5,
            ),
        )

        self._loaded = True
        self.status.setText("Data loaded: 6 points across California.")

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
