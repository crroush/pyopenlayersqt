#!/usr/bin/env python3
"""Geolocation with Uncertainty Ellipses

This example demonstrates FastGeoPointsLayer:
- Points with associated uncertainty ellipses
- Semi-major/semi-minor axes for ellipse dimensions
- Tilt angle for ellipse orientation
- QColor styling for both points and ellipses
- Toggle ellipse visibility on/off
- Useful for GPS/geolocation uncertainty visualization

FastGeoPointsLayer is optimized for rendering thousands of points with
uncertainty ellipses efficiently.
"""

import sys

import numpy as np
from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, FastGeoPointsStyle


class EllipseExample(QtWidgets.QMainWindow):
    """Geolocation ellipse example window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Geolocation with Uncertainty Ellipses")
        self.resize(1200, 800)

        # Create map centered on San Francisco
        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=11)

        # Create FastGeoPointsLayer with QColor styling
        self.geo_layer = self.map_widget.add_fast_geopoints_layer(
            "geolocation_points",
            selectable=True,
            style=FastGeoPointsStyle(
                # Point styling
                point_radius=4.0,
                default_color=QColor("steelblue"),
                selected_point_radius=7.0,
                selected_color=QColor("#d81b60"),

                # Ellipse styling
                ellipse_stroke_color=QColor("steelblue"),
                selected_ellipse_stroke_color=QColor("#d81b60"),
                ellipse_stroke_width=1.5,
                fill_ellipses=True,
                ellipse_fill_color=QColor(70, 130, 180, 60),  # Semi-transparent blue

                # Behavior
                ellipses_visible=True,
                min_ellipse_px=2.0,  # Don't draw very small ellipses
                skip_ellipses_while_interacting=True  # Performance optimization
            ),
            cell_size_m=500.0
        )

        # Add sample data
        self._add_sample_points()

        # Create controls
        controls = self._create_controls()

        # Layout
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(controls)
        layout.addWidget(self.map_widget, stretch=1)
        self.setCentralWidget(container)

    def _add_sample_points(self):
        """Add sample geolocation points with varying uncertainty."""
        # Generate sample geolocation points with varying uncertainty
        rng = np.random.default_rng(seed=42)
        n_points = 50

        # Points scattered around San Francisco
        center_lat, center_lon = 37.7749, -122.4194
        lats = center_lat + (rng.random(n_points) - 0.5) * 0.1
        lons = center_lon + (rng.random(n_points) - 0.5) * 0.1
        coords = list(zip(lats.tolist(), lons.tolist()))

        # Uncertainty ellipses with varying sizes and orientations
        # Semi-major axis (meters) - represents primary uncertainty direction
        sma_m = (50 + rng.random(n_points) * 500).tolist()

        # Semi-minor axis (meters) - represents secondary uncertainty direction
        smi_m = (30 + rng.random(n_points) * 200).tolist()

        # Tilt (degrees from north) - ellipse rotation
        tilt_deg = (rng.random(n_points) * 360).tolist()

        # Generate IDs
        ids = [f"geo_{i}" for i in range(n_points)]

        # Add points with ellipses
        self.geo_layer.add_points_with_ellipses(
            coords=coords,
            sma_m=sma_m,
            smi_m=smi_m,
            tilt_deg=tilt_deg,
            ids=ids
        )

        print(f"Added {n_points} geolocation points with uncertainty ellipses")
        print("Ellipse size represents position uncertainty")
        print("Larger ellipses = more uncertain position")

    def _create_controls(self):
        """Create control panel."""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(panel)

        # Instructions
        instructions = QtWidgets.QLabel(
            "Click points to select them. Use the toggle to show/hide uncertainty ellipses."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions, stretch=1)

        # Ellipse visibility toggle
        self.ellipse_toggle = QtWidgets.QPushButton("Hide Ellipses")
        self.ellipse_toggle.setCheckable(True)
        self.ellipse_toggle.setFixedWidth(150)
        self.ellipse_toggle.clicked.connect(self._toggle_ellipses)
        layout.addWidget(self.ellipse_toggle)

        return panel

    def _toggle_ellipses(self, checked):
        """Toggle ellipse visibility."""
        if checked:
            self.geo_layer.set_ellipses_visible(False)
            self.ellipse_toggle.setText("Show Ellipses")
            self.ellipse_toggle.setStyleSheet("background-color: #ff6b6b; color: white;")
        else:
            self.geo_layer.set_ellipses_visible(True)
            self.ellipse_toggle.setText("Hide Ellipses")
            self.ellipse_toggle.setStyleSheet("")


def main():
    """Run the geo uncertainty ellipses example."""
    app = QtWidgets.QApplication(sys.argv)
    window = EllipseExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
