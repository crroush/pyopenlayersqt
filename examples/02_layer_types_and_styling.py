#!/usr/bin/env python3
"""Layer Types and Styling with QColor

This example demonstrates different layer types and styling options:
- VectorLayer for points, custom icon markers, circles, lines, polygons, and ellipses
- Comprehensive QColor-based styling for all geometry types
- Different stroke and fill options

Features demonstrated:
- Points with custom radius and colors
- Custom icon markers from Path, string path, bytes, bytearray, memoryview,
  QByteArray, data URI, and remote URL inputs
- Circles with geodesic radius
- Lines/Polylines (non-closed paths)
- Polygons with custom fill and stroke
- Ellipses with custom dimensions
"""

import base64
import sys
from pathlib import Path

from PySide6 import QtCore, QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import (
    OLMapWidget,
    PointStyle,
    CircleStyle,
    PolygonStyle,
    EllipseStyle,
)


def main():
    """Run the layer types and styling example."""
    app = QtWidgets.QApplication(sys.argv)

    # Create map centered on San Francisco Bay Area
    map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=10)

    # Add a vector layer for all geometry types
    layer = map_widget.add_vector_layer("styled_features", selectable=True)

    # 1. Points with different styles
    layer.add_points(
        [(37.7749, -122.4194)],  # San Francisco
        ids=["point1"],
        style=PointStyle(
            radius=12.0,
            fill_color=QColor("crimson"),
            fill_opacity=0.9,
            stroke_color=QColor("darkred"),
            stroke_width=2.0,
            stroke_opacity=1.0
        )
    )

    # 2. Custom icon markers: every supported icon input form
    assets_dir = Path(__file__).with_name("assets")
    icon_path = assets_dir / "orange_pin.svg"
    selected_icon_path = assets_dir / "selected_pin.svg"
    icon_bytes = icon_path.read_bytes()
    icon_bytearray = bytearray(icon_bytes)
    icon_memoryview = memoryview(icon_bytes)
    icon_qbytearray = QtCore.QByteArray(icon_bytes)
    icon_data_uri = (
        "data:image/svg+xml;base64,"
        + base64.b64encode(icon_bytes).decode("ascii")
    )
    remote_icon_url = (
        "https://upload.wikimedia.org/wikipedia/commons/8/88/Map_marker.svg"
    )

    # pathlib.Path / os.PathLike; selected_icon accepts the same input forms.
    layer.add_icon_points(
        [(37.8044, -122.2712)],  # Oakland
        icon=icon_path,
        selected_icon=selected_icon_path,
        ids=["icon_path_object"],
        scale=0.9,
        properties=[{"name": "Icon from pathlib.Path with selected icon"}],
    )

    # Local path supplied as a normal string.
    layer.add_icon_points(
        [(37.8715, -122.2730)],  # Berkeley
        icon=str(icon_path),
        ids=["icon_path_string"],
        scale=0.75,
        properties=[{"name": "Icon from local path string"}],
    )

    # Immutable bytes.
    layer.add_icon_points(
        [(37.6879, -122.4702)],  # Daly City
        icon=icon_bytes,
        ids=["icon_bytes"],
        scale=0.75,
        rotation_deg=30.0,
        properties=[{"name": "Icon from bytes"}],
    )

    # Mutable bytearray. It is normalized to bytes before being cached.
    layer.add_icon_points(
        [(37.6391, -122.4111)],  # South San Francisco
        icon=icon_bytearray,
        ids=["icon_bytearray"],
        scale=0.75,
        properties=[{"name": "Icon from bytearray"}],
    )

    # memoryview of image bytes.
    layer.add_icon_points(
        [(37.6547, -122.4077)],  # San Bruno
        icon=icon_memoryview,
        ids=["icon_memoryview"],
        scale=0.75,
        properties=[{"name": "Icon from memoryview"}],
    )

    # Qt QByteArray, useful when icon data comes from Qt APIs/resources.
    layer.add_icon_points(
        [(37.6138, -122.4869)],  # Pacifica
        icon=icon_qbytearray,
        ids=["icon_qbytearray"],
        scale=0.75,
        properties=[{"name": "Icon from QByteArray"}],
    )

    # Browser-ready data URI.
    layer.add_icon_points(
        [(37.5630, -122.3255)],  # San Mateo
        icon=icon_data_uri,
        ids=["icon_data_uri"],
        scale=0.75,
        rotation_deg=-30.0,
        properties=[{"name": "Icon from data URI"}],
    )

    # Remote HTTP(S) URL. This example server permits anonymous CORS.
    layer.add_icon_points(
        [(37.4852, -122.2364)],  # Redwood City
        icon=remote_icon_url,
        ids=["icon_remote_url"],
        scale=0.08,
        cross_origin="anonymous",
        properties=[{"name": "Icon from remote URL"}],
    )

    # 3. Circle with geodesic radius (5km)
    layer.add_circle(
        center=(37.8044, -122.2712),  # Oakland
        radius_m=5000,  # 5 kilometers
        feature_id="circle1",
        style=CircleStyle(
            stroke_color=QColor("steelblue"),
            stroke_width=3.0,
            stroke_opacity=0.9,
            fill_color=QColor("lightblue"),
            fill_opacity=0.3,
            fill=True
        )
    )

    # 4. Line/Polyline (non-closed path)
    line_coords = [
        (37.7749, -122.4194),  # San Francisco
        (37.8044, -122.2712),  # Oakland
        (37.7500, -122.2000),  # East Bay
    ]
    layer.add_line(
        coords=line_coords,
        feature_id="line1",
        style=PolygonStyle(
            stroke_color=QColor("purple"),
            stroke_width=3.0,
            stroke_opacity=0.8
        )
    )

    # 5. Polygon (simple triangle)
    polygon_ring = [
        (37.7000, -122.5000),
        (37.7000, -122.3500),
        (37.6500, -122.4250),
        (37.7000, -122.5000),  # Close the polygon
    ]
    layer.add_polygon(
        ring=polygon_ring,
        feature_id="polygon1",
        style=PolygonStyle(
            stroke_color=QColor("darkgreen"),
            stroke_width=2.5,
            stroke_opacity=0.95,
            fill_color=QColor("lightgreen"),
            fill_opacity=0.4,
            fill=True
        )
    )

    # 6. Ellipse (uncertainty visualization)
    layer.add_ellipse(
        center=(37.7500, -122.2000),  # East Bay
        sma_m=3000,  # Semi-major axis: 3km
        smi_m=1500,  # Semi-minor axis: 1.5km
        tilt_deg=45,  # 45 degrees from north
        feature_id="ellipse1",
        style=EllipseStyle(
            stroke_color=QColor("orange"),
            stroke_width=2.0,
            stroke_opacity=0.9,
            fill_color=QColor("gold"),
            fill_opacity=0.25,
            fill=True
        )
    )

    # 7. Additional styled points using color names
    layer.add_points(
        [(37.7200, -122.4800)],
        ids=["point2"],
        style=PointStyle(
            radius=8.0,
            fill_color="purple",  # Color names work too!
            stroke_color="indigo",
            stroke_width=1.5
        )
    )

    # Show the map
    map_widget.setWindowTitle("Layer Types and Styling with QColor")
    map_widget.resize(1200, 800)
    map_widget.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
