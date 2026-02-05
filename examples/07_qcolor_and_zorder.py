#!/usr/bin/env python3
"""QColor Support and Z-Ordering Example

This example demonstrates:
1. Using QColor objects directly in ALL style classes
2. Using color names (e.g., 'Green', 'Red') in styles
3. Improved z-ordering: selected points/ellipses are drawn on top
4. Both default_rgba/selected_rgba and default_color/selected_color options

Key features:
- ALL Style classes (PointStyle, CircleStyle, PolygonStyle, EllipseStyle) accept QColor
- FastPointsStyle and FastGeoPointsStyle have default_color/selected_color options
- Selected points and ellipses are always drawn on top in dense areas
- No need for .name() - pass QColor objects directly!
- Color names like "red", "Green", "steelblue" work everywhere
"""

import sys
import numpy as np
from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import (
    OLMapWidget,
    PointStyle,
    FastPointsStyle,
    FastGeoPointsStyle,
)


class QColorExampleWindow(QtWidgets.QMainWindow):
    """Main window demonstrating QColor support and z-ordering."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("pyopenlayersqt - QColor Support & Z-Ordering Example")

        # Create map widget
        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=12)

        # Track selections
        self.selections = {}

        # Connect to selection events
        self.map_widget.selectionChanged.connect(self.on_selection_changed)

        # Create controls
        self.create_controls()

        # Layout
        controls_layout = QtWidgets.QVBoxLayout()
        controls_layout.addWidget(QtWidgets.QLabel("<b>QColor Support & Z-Ordering Demo</b>"))
        controls_layout.addWidget(QtWidgets.QLabel(""))
        controls_layout.addWidget(QtWidgets.QLabel("<b>Features:</b>"))
        controls_layout.addWidget(QtWidgets.QLabel("✓ QColor objects in styles"))
        controls_layout.addWidget(QtWidgets.QLabel("✓ Color names like 'Green', 'Red'"))
        controls_layout.addWidget(QtWidgets.QLabel("✓ Selected items on top"))
        controls_layout.addWidget(QtWidgets.QLabel(""))
        controls_layout.addWidget(QtWidgets.QLabel("<b>Try it:</b>"))
        controls_layout.addWidget(QtWidgets.QLabel("Click to select points"))
        controls_layout.addWidget(QtWidgets.QLabel("Notice selected items appear on top!"))
        controls_layout.addWidget(QtWidgets.QLabel(""))
        controls_layout.addWidget(self.info_label)
        controls_layout.addStretch()

        controls_widget = QtWidgets.QWidget()
        controls_widget.setLayout(controls_layout)
        controls_widget.setMaximumWidth(350)

        main_layout = QtWidgets.QHBoxLayout()
        main_layout.addWidget(controls_widget)
        main_layout.addWidget(self.map_widget, 1)

        container = QtWidgets.QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Add data after map is ready
        self.map_widget.ready.connect(self.add_sample_data)

    def create_controls(self):
        """Create control widgets."""
        self.info_label = QtWidgets.QLabel("Loading...")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet(
            "QLabel { background-color: #f0f0f0; padding: 10px; "
            "border-radius: 5px; }"
        )

    def add_sample_data(self):
        """Add sample data demonstrating QColor support and z-ordering."""
        print("="*60)
        print("Adding sample data with QColor support")
        print("="*60)

        # Example 1: FastPointsLayer with QColor
        print("\n1. FastPointsLayer using QColor objects:")
        self.fast_layer_qcolor = self.map_widget.add_fast_points_layer(
            "fast_qcolor",
            selectable=True,
            style=FastPointsStyle(
                radius=4.0,
                default_color=QColor("steelblue"),  # Using QColor directly!
                selected_radius=8.0,
                selected_color=QColor("orange"),    # Using QColor directly!
            )
        )
        print("   Using: default_color=QColor('steelblue'), selected_color=QColor('orange')")

        # Add dense cluster of points
        rng = np.random.default_rng(seed=42)
        n = 200
        lats = 37.77 + rng.normal(0, 0.01, n)
        lons = -122.42 + rng.normal(0, 0.01, n)
        coords = list(zip(lats.tolist(), lons.tolist()))
        ids = [f"qc{i}" for i in range(n)]
        self.fast_layer_qcolor.add_points(coords, ids=ids)
        print(f"   Added {n} points in dense cluster")

        # Example 2: FastPointsLayer with color names
        print("\n2. FastPointsLayer using color name strings:")
        self.fast_layer_names = self.map_widget.add_fast_points_layer(
            "fast_names",
            selectable=True,
            style=FastPointsStyle(
                radius=4.0,
                default_color="purple",     # Using color name string!
                selected_radius=8.0,
                selected_color="yellow",    # Using color name string!
            )
        )
        print("   Using: default_color='purple', selected_color='yellow'")

        # Add another dense cluster
        lats = 37.78 + rng.normal(0, 0.01, n)
        lons = -122.41 + rng.normal(0, 0.01, n)
        coords = list(zip(lats.tolist(), lons.tolist()))
        ids = [f"cn{i}" for i in range(n)]
        self.fast_layer_names.add_points(coords, ids=ids)
        print(f"   Added {n} points in dense cluster")

        # Example 3: FastGeoPointsLayer with QColor
        print("\n3. FastGeoPointsLayer using QColor objects:")
        self.geo_layer = self.map_widget.add_fast_geopoints_layer(
            "geo_qcolor",
            selectable=True,
            style=FastGeoPointsStyle(
                point_radius=4.0,
                default_color=QColor("darkgreen"),   # Using QColor!
                selected_point_radius=8.0,
                selected_color=QColor("red"),        # Using QColor!
                ellipse_stroke_rgba=(100, 200, 100, 150),
                selected_ellipse_stroke_rgba=(255, 100, 100, 200),
                ellipse_stroke_width=2.0,
                fill_ellipses=True,
                ellipse_fill_rgba=(100, 200, 100, 40),
                ellipses_visible=True,
            )
        )
        print("   Using: default_color=QColor('darkgreen'), selected_color=QColor('red')")

        # Add geo points with ellipses
        n_geo = 100
        lats = 37.76 + rng.normal(0, 0.01, n_geo)
        lons = -122.43 + rng.normal(0, 0.01, n_geo)
        coords = list(zip(lats.tolist(), lons.tolist()))
        ids = [f"geo{i}" for i in range(n_geo)]
        sma_m = (30 + rng.random(n_geo) * 100).tolist()
        smi_m = (20 + rng.random(n_geo) * 50).tolist()
        tilt_deg = (rng.random(n_geo) * 360).tolist()
        self.geo_layer.add_points_with_ellipses(
            coords=coords, sma_m=sma_m, smi_m=smi_m, tilt_deg=tilt_deg, ids=ids
        )
        print(f"   Added {n_geo} points with ellipses")

        # Example 4: VectorLayer with QColor (no .name() needed!)
        print("\n4. VectorLayer using QColor objects (no .name() needed):")
        self.vector_layer = self.map_widget.add_vector_layer("vector", selectable=True)
        
        coords = [
            (37.775, -122.415),
            (37.780, -122.420),
            (37.770, -122.425),
        ]
        for i, coord in enumerate(coords):
            # Pass QColor directly - no need for .name()!
            self.vector_layer.add_points(
                [coord],
                ids=[f"v{i}"],
                style=PointStyle(
                    radius=12.0,
                    fill_color=QColor("crimson"),     # QColor directly!
                    fill_opacity=0.9,
                    stroke_color=QColor("darkred"),   # QColor directly!
                    stroke_width=2.0
                )
            )
        print("   Using: fill_color=QColor('crimson'), stroke_color=QColor('darkred')")
        print(f"   Added {len(coords)} large marker points")

        print("\n" + "="*60)
        print("All layers added! Click points to see z-ordering in action.")
        print("Selected points/ellipses will appear on TOP of others.")
        print("="*60 + "\n")

        self.update_info_label()

    def on_selection_changed(self, selection):
        """Handle selection change from map."""
        if len(selection.feature_ids) > 0:
            self.selections[selection.layer_id] = selection.feature_ids
        elif selection.layer_id in self.selections:
            del self.selections[selection.layer_id]

        total = sum(len(ids) for ids in self.selections.values())
        print(f"Selection: {selection.layer_id} - {len(selection.feature_ids)} items (total: {total})")
        
        self.update_info_label()

    def update_info_label(self):
        """Update the info label."""
        if len(self.selections) == 0:
            self.info_label.setText(
                "<b>No selection</b><br><br>"
                "Click any point to select it.<br><br>"
                "<b>Notice:</b> Selected items appear on top!"
            )
        else:
            total = sum(len(ids) for ids in self.selections.values())
            layer_info = []
            for layer_id, ids in self.selections.items():
                if "qcolor" in layer_id:
                    layer_info.append(f"QColor layer: {len(ids)}")
                elif "names" in layer_id:
                    layer_info.append(f"Color names layer: {len(ids)}")
                elif "geo" in layer_id:
                    layer_info.append(f"Geo layer: {len(ids)}")
                elif "vector" in layer_id:
                    layer_info.append(f"Vector layer: {len(ids)}")
            
            self.info_label.setText(
                f"<b>Selected: {total} item(s)</b><br><br>"
                + "<br>".join(layer_info) + 
                "<br><br><b>Z-Ordering:</b> Selected items<br>are drawn on top!"
            )


def main():
    """Run the QColor example."""
    app = QtWidgets.QApplication(sys.argv)
    window = QColorExampleWindow()
    window.resize(1400, 800)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
