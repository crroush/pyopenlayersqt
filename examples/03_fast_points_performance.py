#!/usr/bin/env python3
"""Fast Points for High-Performance Rendering

This example demonstrates FastPointsLayer for rendering large numbers of points:
- Efficient canvas-based rendering for 10,000+ points
- Spatial indexing for fast selection
- Per-point color customization with QColor
- Custom selected state styling

Use FastPointsLayer instead of VectorLayer when you have > 1000 points for
optimal performance.
"""

import sys

import numpy as np
from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, FastPointsStyle


def main():
    """Run the fast points performance example."""
    app = QtWidgets.QApplication(sys.argv)

    # Create map centered on US West Coast
    map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)

    # Create a FastPointsLayer with QColor styling
    fast_layer = map_widget.add_fast_points_layer(
        "high_performance_points",
        selectable=True,
        style=FastPointsStyle(
            radius=3.0,
            default_color=QColor("green"),
            selected_radius=6.0,
            selected_color=QColor("yellow")
        ),
        cell_size_m=750.0  # Spatial index cell size for fast selection
    )

    # Generate 10,000 random points across western US
    rng = np.random.default_rng(seed=42)
    n_points = 10000

    # Random coordinates (lat, lon)
    lats = 32.0 + rng.random(n_points) * 15.0  # 32°N to 47°N
    lons = -125.0 + rng.random(n_points) * 15.0  # -125°W to -110°W
    coords = list(zip(lats.tolist(), lons.tolist()))
    ids = [f"point_{i}" for i in range(n_points)]

    # Option 1: Use default color for all points
    # fast_layer.add_points(coords, ids=ids)

    # Option 2: Assign per-point colors based on latitude (blue=north, red=south)
    colors = []
    for lat in lats:
        # Interpolate from red (south) to blue (north)
        ratio = (lat - 32.0) / 15.0  # 0 to 1
        red = int(255 * (1 - ratio))
        blue = int(255 * ratio)
        colors.append(QColor(red, 100, blue, 200))

    fast_layer.add_points(coords, ids=ids, colors_rgba=colors)

    print(f"Added {n_points} points to the map")
    print("Click on points to select them (selected points turn yellow)")
    print("FastPointsLayer uses spatial indexing for efficient selection")

    # Show the map
    map_widget.setWindowTitle("Fast Points - High-Performance Rendering")
    map_widget.resize(1200, 800)
    map_widget.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
