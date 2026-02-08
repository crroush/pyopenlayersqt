#!/usr/bin/env python3
"""Basic Map with Markers

This example demonstrates the most basic usage of pyopenlayersqt:
- Creating a map widget with custom center and zoom
- Adding a vector layer
- Adding markers (points) with QColor styling
- Displaying the map

This is the recommended starting point for new users.
"""

import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, PointStyle


def main():
    """Run the basic map example."""
    app = QtWidgets.QApplication(sys.argv)

    # Create the map widget centered on the US West Coast
    # center is (latitude, longitude), zoom is 2-18 (2=world, 18=street)
    map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)

    # Add a vector layer for drawing markers
    vector_layer = map_widget.add_vector_layer("cities", selectable=True)

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
                stroke_width=2.0
            )
        )

    # Show the map window
    map_widget.setWindowTitle("Basic Map with Markers")
    map_widget.resize(1024, 768)
    map_widget.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
