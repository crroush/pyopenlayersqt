#!/usr/bin/env python3
"""Basic Map with Markers

This example demonstrates the most basic usage of pyopenlayersqt:
- Creating a map widget with custom center and zoom
- Adding a vector layer
- Adding markers (points) with QColor styling
- Toggling built-in country boundaries on/off

This is the recommended starting point for new users.
"""

import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, PointStyle


class BasicMapExample(QtWidgets.QMainWindow):
    """Basic map example window with a country boundaries toggle."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Basic Map with Markers")
        self.resize(1024, 768)

        # Create the map widget centered on the US West Coast
        # center is (latitude, longitude), zoom is 2-18 (2=world, 18=street)
        self.map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)

        # Add a vector layer for drawing markers
        vector_layer = self.map_widget.add_vector_layer("cities", selectable=True)

        # Add some city markers with QColor styling
        # Coordinates are (latitude, longitude)
        cities = [
            (37.7749, -122.4194, "San Francisco", QColor("red")),
            (34.0522, -118.2437, "Los Angeles", QColor("blue")),
            (47.6062, -122.3321, "Seattle", QColor("green")),
            (45.5152, -122.6784, "Portland", QColor("purple")),
        ]

        for lat, lon, city_id, color in cities:
            vector_layer.add_points(
                [(lat, lon)],
                ids=[city_id],
                style=PointStyle(
                    radius=10.0,
                    fill_color=color,
                    fill_opacity=0.85,
                    stroke_color=QColor("black"),
                    stroke_width=2.0,
                ),
            )

        # Top controls
        controls = QtWidgets.QWidget()
        controls_layout = QtWidgets.QHBoxLayout(controls)
        controls_layout.setContentsMargins(8, 8, 8, 8)

        self.countries_checkbox = QtWidgets.QCheckBox("Show country boundaries")
        self.countries_checkbox.setChecked(False)
        self.countries_checkbox.toggled.connect(
            self.map_widget.set_country_boundaries_visible
        )
        controls_layout.addWidget(self.countries_checkbox)
        controls_layout.addStretch(1)

        # Main layout
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(controls)
        layout.addWidget(self.map_widget, stretch=1)
        self.setCentralWidget(container)


def main():
    """Run the basic map example."""
    app = QtWidgets.QApplication(sys.argv)
    window = BasicMapExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
