#!/usr/bin/env python3
"""Quick Start Example

This example shows the most basic usage of pyopenlayersqt:
- Creating a map widget
- Adding a vector layer
- Adding points with custom styling
- Displaying the map
"""

import sys

from PySide6 import QtWidgets

from pyopenlayersqt import OLMapWidget, PointStyle

def main():
    """Run the quick start example."""
    app = QtWidgets.QApplication(sys.argv)

    # Create the map widget centered on the US West Coast
    map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)

    # Add a vector layer
    vector_layer = map_widget.add_vector_layer("my_layer", selectable=True)

    # Add some points (latitude, longitude)
    coords = [(37.7749, -122.4194), (34.0522, -118.2437)]  # SF, LA
    vector_layer.add_points(
        coords,
        ids=["sf", "la"],
        style=PointStyle(radius=8.0, fill_color="#ff3333")
    )

    # Show the map
    map_widget.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
