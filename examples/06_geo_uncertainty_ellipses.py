#!/usr/bin/env python3
"""Geolocation with Uncertainty Ellipses

This example demonstrates FastGeoPointsLayer:
- Points with associated uncertainty ellipses
- Semi-major/semi-minor axes for ellipse dimensions
- Tilt angle for ellipse orientation
- QColor styling for both points and ellipses
- Useful for GPS/geolocation uncertainty visualization

FastGeoPointsLayer is optimized for rendering thousands of points with
uncertainty ellipses efficiently.
"""

import sys

import numpy as np
from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, FastGeoPointsStyle


def main():
    """Run the geo uncertainty ellipses example."""
    app = QtWidgets.QApplication(sys.argv)

    # Create map centered on San Francisco
    map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=11)

    # Create FastGeoPointsLayer with QColor styling
    geo_layer = map_widget.add_fast_geopoints_layer(
        "geolocation_points",
        selectable=True,
        style=FastGeoPointsStyle(
            # Point styling
            point_radius=4.0,
            default_color=QColor("steelblue"),
            selected_point_radius=7.0,
            selected_color=QColor("orange"),
            
            # Ellipse styling
            ellipse_stroke_color=QColor("steelblue"),
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
    geo_layer.add_points_with_ellipses(
        coords=coords,
        sma_m=sma_m,
        smi_m=smi_m,
        tilt_deg=tilt_deg,
        ids=ids
    )

    print(f"Added {n_points} geolocation points with uncertainty ellipses")
    print("Ellipse size represents position uncertainty")
    print("Larger ellipses = more uncertain position")
    print("Click on points to select them")

    # Show the map
    map_widget.setWindowTitle("Geolocation with Uncertainty Ellipses")
    map_widget.resize(1200, 800)
    map_widget.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
