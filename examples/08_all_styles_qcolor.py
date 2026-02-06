#!/usr/bin/env python3
"""Complete QColor Support Demo - All Style Classes

This example demonstrates that ALL Style classes now support QColor:
- PointStyle
- CircleStyle
- PolygonStyle
- EllipseStyle
- FastPointsStyle
- FastGeoPointsStyle

All accept:
- QColor objects: QColor("red"), QColor(255, 0, 0)
- Color names: "red", "Green", "steelblue"
- Hex colors: "#ff0000"
- RGB/RGBA tuples: (255, 0, 0) or (255, 0, 0, 255)
"""

import sys
from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import (
    OLMapWidget,
    PointStyle,
    CircleStyle,
    PolygonStyle,
    EllipseStyle,
    FastPointsStyle,
    FastGeoPointsStyle,
)


class AllStylesQColorDemo(QtWidgets.QMainWindow):
    """Demonstrates QColor support in all Style classes."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("All Styles Support QColor - Demo")

        # Create map widget
        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=11)

        # Create UI
        info_label = QtWidgets.QLabel(
            "<b>All Style Classes Support QColor!</b><br><br>"
            "This demo shows:<br>"
            "• PointStyle with QColor<br>"
            "• CircleStyle with QColor<br>"
            "• PolygonStyle with QColor<br>"
            "• EllipseStyle with QColor<br>"
            "• FastPointsStyle with color names<br>"
            "• FastGeoPointsStyle with QColor<br><br>"
            "<b>No .name() needed!</b>"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("QLabel { padding: 15px; background: #f0f0f0; }")
        info_label.setMaximumWidth(300)

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(info_label)
        layout.addWidget(self.map_widget, 1)

        container = QtWidgets.QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Add data after map is ready
        self.map_widget.ready.connect(self.add_demo_data)

    def add_demo_data(self):
        """Add features demonstrating QColor in all Style classes."""
        print("="*60)
        print("Adding features with QColor support...")
        print("="*60)

        # 1. VectorLayer with PointStyle using QColor
        print("\n1. PointStyle with QColor:")
        vector_layer = self.map_widget.add_vector_layer("points")
        vector_layer.add_points(
            [(37.78, -122.42)],
            ids=["point1"],
            style=PointStyle(
                radius=15.0,
                fill_color=QColor("crimson"),      # QColor!
                stroke_color=QColor("darkred"),    # QColor!
                stroke_width=3.0
            )
        )
        print("   ✓ PointStyle(fill_color=QColor('crimson'))")

        # 2. CircleStyle with QColor and color name
        print("\n2. CircleStyle with QColor:")
        circle_layer = self.map_widget.add_vector_layer("circles")
        circle_layer.add_circle(
            (37.77, -122.41),
            feature_id="circle1",
            radius_m=500,
            style=CircleStyle(
                stroke_color=QColor("blue"),       # QColor!
                fill_color="steelblue",            # Color name!
                fill_opacity=0.3
            )
        )
        print("   ✓ CircleStyle(stroke_color=QColor('blue'), fill_color='steelblue')")

        # 3. PolygonStyle with QColor
        print("\n3. PolygonStyle with QColor:")
        poly_layer = self.map_widget.add_vector_layer("polygons")
        polygon_coords = [
            (37.76, -122.43),
            (37.76, -122.41),
            (37.74, -122.41),
            (37.74, -122.43),
            (37.76, -122.43),
        ]
        poly_layer.add_polygon(
            polygon_coords,
            feature_id="poly1",
            style=PolygonStyle(
                stroke_color=QColor("purple"),     # QColor!
                fill_color=QColor(255, 0, 255, 100),  # QColor with RGBA!
                stroke_width=2.5
            )
        )
        print("   ✓ PolygonStyle(stroke_color=QColor('purple'))")

        # 4. EllipseStyle with QColor
        print("\n4. EllipseStyle with QColor:")
        ellipse_layer = self.map_widget.add_vector_layer("ellipses")
        ellipse_layer.add_ellipse(
            (37.79, -122.43),
            sma_m=600,
            smi_m=300,
            tilt_deg=45,
            feature_id="ellipse1",
            style=EllipseStyle(
                stroke_color=QColor("gold"),       # QColor!
                fill_color="yellow",               # Color name!
                fill_opacity=0.2,
                stroke_width=2.0
            )
        )
        print("   ✓ EllipseStyle(stroke_color=QColor('gold'), fill_color='yellow')")

        # 5. FastPointsStyle with color names
        print("\n5. FastPointsStyle with color names:")
        import numpy as np
        rng = np.random.default_rng(seed=42)
        
        fast_layer = self.map_widget.add_fast_points_layer(
            "fast_points",
            selectable=True,
            style=FastPointsStyle(
                default_color="orange",            # Color name!
                selected_color="lime"              # Color name!
            )
        )
        n = 100
        lats = 37.75 + rng.normal(0, 0.01, n)
        lons = -122.44 + rng.normal(0, 0.01, n)
        coords = list(zip(lats.tolist(), lons.tolist()))
        ids = [f"fp{i}" for i in range(n)]
        fast_layer.add_points(coords, ids=ids)
        print("   ✓ FastPointsStyle(default_color='orange', selected_color='lime')")

        # 6. FastGeoPointsStyle with QColor
        print("\n6. FastGeoPointsStyle with QColor:")
        geo_layer = self.map_widget.add_fast_geopoints_layer(
            "fast_geo",
            selectable=True,
            style=FastGeoPointsStyle(
                default_color=QColor("darkgreen"),    # QColor!
                selected_color=QColor("red"),         # QColor!
                ellipse_stroke_rgba=(100, 200, 100, 150),
                fill_ellipses=True
            )
        )
        n_geo = 50
        lats_geo = 37.78 + rng.normal(0, 0.008, n_geo)
        lons_geo = -122.40 + rng.normal(0, 0.008, n_geo)
        coords_geo = list(zip(lats_geo.tolist(), lons_geo.tolist()))
        ids_geo = [f"geo{i}" for i in range(n_geo)]
        sma = (50 + rng.random(n_geo) * 150).tolist()
        smi = (30 + rng.random(n_geo) * 80).tolist()
        tilt = (rng.random(n_geo) * 360).tolist()
        geo_layer.add_points_with_ellipses(
            coords=coords_geo, sma_m=sma, smi_m=smi, tilt_deg=tilt, ids=ids_geo
        )
        print("   ✓ FastGeoPointsStyle(default_color=QColor('darkgreen'))")

        print("\n" + "="*60)
        print("✓ All Style classes support QColor!")
        print("="*60)


def main():
    """Run the demo."""
    app = QtWidgets.QApplication(sys.argv)
    window = AllStylesQColorDemo()
    window.resize(1200, 700)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
