#!/usr/bin/env python3
"""Selection and Recoloring Example

This example demonstrates selection and color updating across all layer types:
- FastPointsLayer with per-point colors
- FastGeoPointsLayer with per-point colors and uncertainty ellipses
- VectorLayer with point features
- Select features by clicking (Ctrl/Cmd+click for multi-select)
- Change colors of selected features with buttons
- Shows how to update colors for selected items on any layer type
"""

import sys

import numpy as np
from PySide6 import QtWidgets

from pyopenlayersqt import (
    OLMapWidget,
    PointStyle,
    FastPointsStyle,
    FastGeoPointsStyle,
)


class SelectionRecoloringWindow(QtWidgets.QMainWindow):
    """Main window demonstrating selection and recoloring features."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("pyopenlayersqt - Selection and Recoloring Example")

        # Create map widget centered on San Francisco Bay Area
        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=10)

        # Track selections for all layers (layer_id -> list of feature_ids)
        self.selections = {}

        # Connect to selection events
        self.map_widget.selectionChanged.connect(self.on_selection_changed)
        print("Selection change handler connected")

        # Create layers
        self.vector_layer = None
        self.fast_layer = None
        self.fast_geo_layer = None

        # Create controls
        self.create_controls()

        # Layout
        controls_layout = QtWidgets.QVBoxLayout()
        controls_layout.addWidget(QtWidgets.QLabel("<b>Instructions:</b>"))
        controls_layout.addWidget(
            QtWidgets.QLabel("• Vector points (large): Click to select")
        )
        controls_layout.addWidget(
            QtWidgets.QLabel("• Fast points (small): Ctrl/Cmd+Click to select")
        )
        controls_layout.addWidget(
            QtWidgets.QLabel("• Ctrl/Cmd+Drag for box-select")
        )
        controls_layout.addWidget(QtWidgets.QLabel("• Color buttons enable when items selected"))
        controls_layout.addWidget(QtWidgets.QLabel(""))
        controls_layout.addWidget(QtWidgets.QLabel("<b>Recolor Selected Items:</b>"))
        controls_layout.addWidget(self.red_button)
        controls_layout.addWidget(self.green_button)
        controls_layout.addWidget(self.blue_button)
        controls_layout.addWidget(self.yellow_button)
        controls_layout.addWidget(self.cyan_button)
        controls_layout.addWidget(self.magenta_button)
        controls_layout.addWidget(QtWidgets.QLabel(""))
        controls_layout.addWidget(self.info_label)
        controls_layout.addStretch()

        controls_widget = QtWidgets.QWidget()
        controls_widget.setLayout(controls_layout)
        controls_widget.setMaximumWidth(300)

        main_layout = QtWidgets.QHBoxLayout()
        main_layout.addWidget(controls_widget)
        main_layout.addWidget(self.map_widget, 1)

        container = QtWidgets.QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Add data after map is ready
        self.map_widget.ready.connect(self.add_sample_data)

    def create_controls(self):
        """Create control buttons."""
        self.red_button = QtWidgets.QPushButton("🔴 Red")
        self.red_button.clicked.connect(lambda: self.recolor_selection(255, 0, 0))

        self.green_button = QtWidgets.QPushButton("🟢 Green")
        self.green_button.clicked.connect(lambda: self.recolor_selection(0, 255, 0))

        self.blue_button = QtWidgets.QPushButton("🔵 Blue")
        self.blue_button.clicked.connect(lambda: self.recolor_selection(0, 0, 255))

        self.yellow_button = QtWidgets.QPushButton("🟡 Yellow")
        self.yellow_button.clicked.connect(lambda: self.recolor_selection(255, 255, 0))

        self.cyan_button = QtWidgets.QPushButton("🔵 Cyan")
        self.cyan_button.clicked.connect(lambda: self.recolor_selection(0, 255, 255))

        self.magenta_button = QtWidgets.QPushButton("🟣 Magenta")
        self.magenta_button.clicked.connect(lambda: self.recolor_selection(255, 0, 255))

        self.info_label = QtWidgets.QLabel("No selection")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet(
            "QLabel { background-color: #f0f0f0; padding: 10px; "
            "border-radius: 5px; }"
        )

        # Disable buttons initially
        self.set_buttons_enabled(False)

    def set_buttons_enabled(self, enabled):
        """Enable or disable recolor buttons."""
        self.red_button.setEnabled(enabled)
        self.green_button.setEnabled(enabled)
        self.blue_button.setEnabled(enabled)
        self.yellow_button.setEnabled(enabled)
        self.cyan_button.setEnabled(enabled)
        self.magenta_button.setEnabled(enabled)

    def add_sample_data(self):
        """Add sample data to the map."""
        print("="*60)
        print("MAP READY - Adding sample data")
        print("To select items:")
        print("  - VECTOR points (large circles): Click to select, Ctrl/Cmd+Click to toggle")
        print("  - FAST points (small colored dots): Ctrl/Cmd+Click to select/toggle")
        print("  - FAST GEO points (dots with ellipses): Ctrl/Cmd+Click to select/toggle")
        print("When items are selected, color buttons will enable")
        print("="*60)

        # Add vector layer with a few points
        self.vector_layer = self.map_widget.add_vector_layer("vector", selectable=True)

        # Add 5 vector points in SF
        coords = [
            (37.7749, -122.4194),  # Downtown SF
            (37.8044, -122.2712),  # Berkeley
            (37.7749, -122.5194),  # Outer SF
            (37.7349, -122.4194),  # South SF
            (37.8149, -122.4194),  # North SF
        ]
        ids = [f"v{i}" for i in range(len(coords))]
        # Different colors for each point
        colors = ["#ff3333", "#33ff33", "#3333ff", "#ffff33", "#ff33ff"]

        for i, (coord, fid, color) in enumerate(zip(coords, ids, colors)):
            self.vector_layer.add_points(
                [coord],
                ids=[fid],
                style=PointStyle(radius=10.0, fill_color=color, fill_opacity=0.9)
            )

        # Add fast points layer with many small points
        self.fast_layer = self.map_widget.add_fast_points_layer(
            "fast_points",
            selectable=True,
            style=FastPointsStyle(
                radius=3.0,
                default_rgba=(200, 100, 50, 200),
                selected_radius=6.0,
                selected_rgba=(255, 255, 0, 255)
            )
        )

        # Add 100 fast points with random colors
        rng = np.random.default_rng(seed=42)
        n = 100
        lats = 37.6 + rng.random(n) * 0.3
        lons = -122.6 + rng.random(n) * 0.3
        coords_fast = list(zip(lats.tolist(), lons.tolist()))
        ids_fast = [f"fp{i}" for i in range(n)]

        # Random colors for each fast point
        colors_rgba = [
            (
                int(rng.integers(100, 255)),
                int(rng.integers(100, 255)),
                int(rng.integers(100, 255)),
                200
            )
            for _ in range(n)
        ]

        self.fast_layer.add_points(coords_fast, ids=ids_fast, colors_rgba=colors_rgba)

        # Add fast geo points layer with uncertainty ellipses
        self.fast_geo_layer = self.map_widget.add_fast_geopoints_layer(
            "fast_geo",
            selectable=True,
            style=FastGeoPointsStyle(
                point_radius=3.0,
                default_point_rgba=(50, 100, 200, 200),
                selected_point_radius=6.0,
                selected_point_rgba=(0, 255, 255, 255),
                ellipse_stroke_rgba=(50, 100, 200, 150),
                ellipse_stroke_width=1.5,
                fill_ellipses=True,
                ellipse_fill_rgba=(50, 100, 200, 30),
                ellipses_visible=True,
            )
        )

        # Add 50 geo points with ellipses
        n_geo = 50
        lats_geo = 37.65 + rng.random(n_geo) * 0.25
        lons_geo = -122.3 + rng.random(n_geo) * 0.25
        coords_geo = list(zip(lats_geo.tolist(), lons_geo.tolist()))
        ids_geo = [f"geo{i}" for i in range(n_geo)]

        # Random ellipse parameters
        sma_m = (50 + rng.random(n_geo) * 200).tolist()  # 50-250m
        smi_m = (30 + rng.random(n_geo) * 100).tolist()  # 30-130m
        tilt_deg = (rng.random(n_geo) * 360).tolist()

        # Random colors for geo points
        colors_rgba_geo = [
            (
                int(rng.integers(100, 255)),
                int(rng.integers(100, 255)),
                int(rng.integers(100, 255)),
                200
            )
            for _ in range(n_geo)
        ]

        self.fast_geo_layer.add_points_with_ellipses(
            coords=coords_geo,
            sma_m=sma_m,
            smi_m=smi_m,
            tilt_deg=tilt_deg,
            ids=ids_geo,
            colors_rgba=colors_rgba_geo,
        )

        print(f"Added {len(coords)} vector points, {n} fast points, and {n_geo} fast geo points")
        self.update_info_label()

    def on_selection_changed(self, selection):
        """Handle selection change from map."""
        # Update selections for this layer
        if len(selection.feature_ids) > 0:
            self.selections[selection.layer_id] = selection.feature_ids
        elif selection.layer_id in self.selections:
            # Clear selection for this layer
            del self.selections[selection.layer_id]

        has_selection = len(self.selections) > 0
        total_features = sum(len(ids) for ids in self.selections.values())

        print(
            f"Selection changed: {selection.layer_id}, "
            f"{len(selection.feature_ids)} features, total selections: {total_features}"
        )
        print(f"  Feature IDs: {selection.feature_ids}")
        print(f"  All selections: {list(self.selections.keys())}")
        self.update_info_label()

        # Enable/disable buttons based on selection
        self.set_buttons_enabled(has_selection)

        # Verify buttons are actually enabled
        print(f"  Red button enabled: {self.red_button.isEnabled()}")

    def update_info_label(self):
        """Update the info label with current selection."""
        if len(self.selections) == 0:
            self.info_label.setText("No selection\n\nClick on points to select them")
        else:
            total_features = sum(len(ids) for ids in self.selections.values())

            # Build a summary of selections by layer
            layer_summaries = []
            for layer_id, feature_ids in self.selections.items():
                # Determine layer type
                if layer_id == (self.vector_layer.id if self.vector_layer else ""):
                    layer_type = "Vector"
                elif layer_id == (self.fast_layer.id if self.fast_layer else ""):
                    layer_type = "Fast Points"
                elif layer_id == (self.fast_geo_layer.id if self.fast_geo_layer else ""):
                    layer_type = "Fast Geo"
                else:
                    layer_type = "Unknown"

                layer_summaries.append(f"{layer_type}: {len(feature_ids)} items")

            summary_text = "<br>".join(layer_summaries)

            self.info_label.setText(
                f"<b>Selected: {total_features} item(s) total</b><br>"
                f"{summary_text}"
            )

    def recolor_selection(self, r, g, b):
        """Recolor the selected features across all layers."""
        if len(self.selections) == 0:
            print("No selection to recolor")
            return

        total_recolored = 0

        # Recolor selections on each layer
        for layer_id, feature_ids in self.selections.items():
            print(
                f"Recoloring {len(feature_ids)} features on layer {layer_id} "
                f"to RGB({r}, {g}, {b})"
            )

            if layer_id == self.vector_layer.id:
                # For vector layer, update feature styles
                styles = [
                    PointStyle(
                        radius=10.0,
                        fill_color=(r, g, b),
                        fill_opacity=0.9,
                        stroke_color="#000000",
                        stroke_width=1.0
                    )
                    for _ in feature_ids
                ]
                self.vector_layer.update_feature_styles(feature_ids, styles)
                print(f"  Updated {len(feature_ids)} vector point styles")
                total_recolored += len(feature_ids)

            elif layer_id == self.fast_layer.id:
                # For fast points layer, set colors
                colors_rgba = [(r, g, b, 200) for _ in feature_ids]
                self.fast_layer.set_colors(feature_ids, colors_rgba)
                print(f"  Updated {len(feature_ids)} fast point colors")
                total_recolored += len(feature_ids)

            elif layer_id == self.fast_geo_layer.id:
                # For fast geo points layer, set colors
                colors_rgba = [(r, g, b, 200) for _ in feature_ids]
                self.fast_geo_layer.set_colors(feature_ids, colors_rgba)
                print(f"  Updated {len(feature_ids)} fast geo point colors")
                total_recolored += len(feature_ids)

            else:
                print(f"  Unknown layer: {layer_id}")

        print(f"Total recolored: {total_recolored} features across {len(self.selections)} layer(s)")


def main():
    """Run the selection and recoloring example."""
    app = QtWidgets.QApplication(sys.argv)
    window = SelectionRecoloringWindow()
    window.resize(1200, 700)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
