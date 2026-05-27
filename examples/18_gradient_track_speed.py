#!/usr/bin/env python3
"""Gradient polyline example covering all add_gradient_line use-cases.

Demonstrates three gradient-line modes:
1) colormap + per-segment values
2) colormap + per-vertex values (smooth interpolation)
3) explicit segment_colors (color-only path; no values)
"""

import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, PointStyle, PolygonStyle


def _offset_track(coords, dlat=0.0, dlon=0.0):
    return [(lat + dlat, lon + dlon) for lat, lon in coords]


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)

    map_widget = OLMapWidget(center=(37.7795, -122.4241), zoom=13)
    layer = map_widget.add_vector_layer("gradient_tracks", selectable=True)

    base_track = [
        (37.8078, -122.4177),
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

    # Use-case 1: per-segment values + colormap
    track_segment = _offset_track(base_track, dlat=0.0018)
    segment_speeds = [12, 18, 24, 28, 20, 14, 10, 16, 22]
    layer.add_gradient_line(
        coords=track_segment,
        values=segment_speeds,
        feature_id="track_segment_values",
        cmap="turbo",
        style=PolygonStyle(stroke_width=6.0, stroke_opacity=0.85),
        properties={"kind": "segment_values", "metric": "speed_mph"},
        interpolate_steps=96,
    )

    # Use-case 2: per-vertex values + colormap (continuous through vertices)
    track_vertex = _offset_track(base_track, dlat=-0.0018)
    vertex_speeds = [10, 14, 18, 24, 30, 26, 20, 14, 12, 9]
    layer.add_gradient_line(
        coords=track_vertex,
        values=vertex_speeds,
        feature_id="track_vertex_values",
        cmap="turbo",
        vmin=0,
        vmax=35,
        style=PolygonStyle(stroke_width=6.0, stroke_opacity=0.85),
        properties={"kind": "vertex_values", "metric": "speed_mph"},
        interpolate_steps=96,
    )

    # Use-case 3: explicit segment colors only (no scalar values required)
    track_explicit = _offset_track(base_track, dlon=-0.006)
    explicit_colors = [
        "#2b83ba", "#2b83ba", "#abdda4", "#ffffbf", "#fdae61",
        "#f46d43", "#d7191c", "#f46d43", "#abdda4"
    ]
    layer.add_gradient_line(
        coords=track_explicit,
        segment_colors=explicit_colors,
        feature_id="track_explicit_colors",
        style=PolygonStyle(stroke_width=6.0, stroke_opacity=0.85),
        properties={"kind": "explicit_colors"},
        interpolate_steps=96,
    )

    # Endpoints for context
    layer.add_points(
        [track_segment[0], track_segment[-1], track_vertex[0], track_explicit[0]],
        ids=["seg_start", "seg_end", "vertex_start", "explicit_start"],
        style=PointStyle(
            radius=6.0,
            fill_color=QColor("white"),
            stroke_color=QColor("black"),
            stroke_width=1.2,
        ),
    )

    map_widget.setWindowTitle("Gradient Track Speed Example (All Use Cases)")
    map_widget.resize(1280, 820)
    map_widget.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
