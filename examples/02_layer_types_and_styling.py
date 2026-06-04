#!/usr/bin/env python3
"""Layer Types and Styling with QColor

This example demonstrates different layer types and styling options:
- VectorLayer for points, custom icon markers, circles, lines, polygons, and ellipses
- Comprehensive QColor-based styling for all geometry types
- Different stroke and fill options

Features demonstrated:
- Points with custom radius and colors
- Custom icon markers anchored to map coordinates
- Circles with geodesic radius
- Lines/Polylines (non-closed paths)
- Polygons with custom fill and stroke
- Ellipses with custom dimensions
"""

import sys
from urllib.parse import quote

from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import (
    OLMapWidget,
    PointStyle,
    IconStyle,
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

    # 2. Custom icon marker using an inline SVG data URI
    pin_svg = quote("""
    <svg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 48 48'>
      <path d='M24 45S9 28.5 9 17a15 15 0 1 1 30 0c0 11.5-15 28-15 28z' fill='#ff7f0e' stroke='#7a3b00' stroke-width='2'/>
      <circle cx='24' cy='17' r='6' fill='white'/>
    </svg>
    """.strip())
    layer.add_icon_points(
        [(37.8044, -122.2712)],  # Oakland
        icon_src=f"data:image/svg+xml;utf8,{pin_svg}",
        ids=["icon1"],
        style=IconStyle(
            scale=0.9,
            anchor=(0.5, 1.0),
        ),
        properties=[{"name": "Custom SVG icon marker"}],
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
