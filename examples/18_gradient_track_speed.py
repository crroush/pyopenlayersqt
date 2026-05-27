#!/usr/bin/env python3
"""Gradient polyline example: color a road track by speed.

Demonstrates VectorLayer.add_gradient_line(...) by drawing a route-like polyline
through San Francisco and coloring each segment using a matplotlib colormap.
"""

import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, PointStyle, PolygonStyle


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)

    map_widget = OLMapWidget(center=(37.7795, -122.4241), zoom=13)
    layer = map_widget.add_vector_layer("speed_track", selectable=True)

    # Approximate route along major roads (SF downtown-ish)
    track_coords = [
        (37.8078, -122.4177),  # Fisherman's Wharf
        (37.8034, -122.4109),
        (37.7986, -122.4072),
        (37.7924, -122.4019),
        (37.7873, -122.4052),
        (37.7831, -122.4090),
        (37.7791, -122.4148),
        (37.7750, -122.4195),
        (37.7710, -122.4234),
        (37.7680, -122.4260),
    ]

    # Per-segment speed values (mph), one value for each segment
    segment_speeds = [12, 18, 24, 28, 20, 14, 10, 16, 22]

    # Draw gradient line using matplotlib colormap (blue->green->yellow)
    layer.add_gradient_line(
        coords=track_coords,
        values=segment_speeds,
        feature_id="track_speed",
        cmap="viridis",
        style=PolygonStyle(stroke_width=6.0, stroke_color=QColor("white")),
        properties={"metric": "speed_mph"},
    )

    # Add endpoints for context
    layer.add_points(
        [track_coords[0], track_coords[-1]],
        ids=["start", "end"],
        style=PointStyle(radius=7.0, fill_color=QColor("white"), stroke_color=QColor("black"), stroke_width=1.5),
    )

    map_widget.setWindowTitle("Gradient Track Speed Example")
    map_widget.resize(1280, 820)
    map_widget.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
