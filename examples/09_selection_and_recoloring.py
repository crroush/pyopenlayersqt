#!/usr/bin/env python3
"""Selection and Interactive Recoloring

This example demonstrates interactive feature recoloring - a CORE feature:
- Select features by clicking
- Change colors of selected features using color picker buttons
- Works across all layer types (vector, fast points, geo points)
- Uses QColor for all color operations
- Demonstrates set_colors() for fast layers
- Demonstrates update_feature_styles() for vector layers

This is essential for interactive data exploration and annotation workflows.
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


class RecoloringExample(QtWidgets.QMainWindow):
    """Selection and recoloring example window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Selection and Interactive Recoloring")
        self.resize(1400, 900)

        # Create map
        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=10)

        # Track selections
        self.selections = {}

        # Connect selection signal
        self.map_widget.selectionChanged.connect(self._on_selection_changed)

        # Add layers
        self._add_vector_layer()
        self._add_fast_points_layer()
        self._add_geo_layer()

        # Create control panel
        controls = self._create_controls()

        # Layout
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(controls)
        layout.addWidget(self.map_widget, stretch=1)
        self.setCentralWidget(container)

    def _add_vector_layer(self):
        """Add vector points with different colors."""
        self.vector_layer = self.map_widget.add_vector_layer("vector_points", selectable=True)

        points = [
            (37.7749, -122.4194, "red"),
            (37.7844, -122.4078, "blue"),
            (37.7694, -122.4362, "green"),
            (37.7599, -122.4148, "purple"),
            (37.7899, -122.4294, "orange"),
        ]

        for lat, lon, color in points:
            self.vector_layer.add_points(
                [(lat, lon)],
                ids=[f"vec_{color}"],
                style=PointStyle(
                    radius=12.0,
                    fill_color=QColor(color),
                    stroke_color=QColor("black"),
                    stroke_width=2.0
                )
            )

    def _add_fast_points_layer(self):
        """Add fast points with per-point colors."""
        self.fast_layer = self.map_widget.add_fast_points_layer(
            "fast_points",
            selectable=True,
            style=FastPointsStyle(
                radius=5.0,
                default_color=QColor("gray"),
                selected_radius=8.0,
                selected_color=QColor("yellow")
            )
        )

        # Add points with random colors
        rng = np.random.default_rng(seed=42)
        n = 100
        lats = 37.72 + rng.random(n) * 0.12
        lons = -122.50 + rng.random(n) * 0.15
        coords = list(zip(lats.tolist(), lons.tolist()))
        ids = [f"fast_{i}" for i in range(n)]

        # Generate random colors
        colors = [
            QColor(
                int(rng.integers(50, 255)),
                int(rng.integers(50, 255)),
                int(rng.integers(50, 255)),
                200
            )
            for _ in range(n)
        ]

        self.fast_layer.add_points(coords, ids=ids, colors_rgba=colors)

    def _add_geo_layer(self):
        """Add geo points with ellipses and colors."""
        self.geo_layer = self.map_widget.add_fast_geopoints_layer(
            "geo_points",
            selectable=True,
            style=FastGeoPointsStyle(
                point_radius=6.0,
                default_color=QColor("steelblue"),
                selected_color=QColor("orange"),
                ellipse_stroke_color=QColor("steelblue"),
                fill_ellipses=True,
                ellipse_fill_color=QColor(70, 130, 180, 40)
            )
        )

        # Add points with ellipses and random colors
        rng = np.random.default_rng(seed=43)
        n = 50
        lats = 37.74 + rng.random(n) * 0.08
        lons = -122.48 + rng.random(n) * 0.10
        coords = list(zip(lats.tolist(), lons.tolist()))
        ids = [f"geo_{i}" for i in range(n)]

        sma_m = (100 + rng.random(n) * 300).tolist()
        smi_m = (50 + rng.random(n) * 150).tolist()
        tilt_deg = (rng.random(n) * 360).tolist()

        # Random colors for geo points
        colors = [
            QColor(
                int(rng.integers(50, 255)),
                int(rng.integers(50, 255)),
                int(rng.integers(50, 255)),
                200
            )
            for _ in range(n)
        ]

        self.geo_layer.add_points_with_ellipses(
            coords=coords,
            sma_m=sma_m,
            smi_m=smi_m,
            tilt_deg=tilt_deg,
            ids=ids,
            colors_rgba=colors
        )

    def _create_controls(self):
        """Create control panel with recoloring buttons."""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)

        # Instructions
        instructions = QtWidgets.QLabel(
            "Select features (click or Ctrl+drag), then click a color button to recolor them"
        )
        instructions.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(instructions)

        # Color buttons
        button_layout = QtWidgets.QHBoxLayout()
        colors = [
            ("Red", QColor("red")),
            ("Green", QColor("green")),
            ("Blue", QColor("blue")),
            ("Yellow", QColor("yellow")),
            ("Purple", QColor("purple")),
            ("Orange", QColor("orange")),
            ("Pink", QColor("pink")),
            ("Cyan", QColor("cyan")),
        ]

        for name, color in colors:
            btn = QtWidgets.QPushButton(name)
            btn.setFixedWidth(80)
            # Set button background color
            rgb = f"rgb({color.red()}, {color.green()}, {color.blue()})"
            btn.setStyleSheet(f"background-color: {rgb}; color: white; font-weight: bold;")
            btn.clicked.connect(lambda checked, c=color: self._recolor_selected(c))
            button_layout.addWidget(btn)

        button_layout.addStretch(1)
        layout.addLayout(button_layout)

        # Selection info
        self.selection_label = QtWidgets.QLabel("No selection")
        self.selection_label.setStyleSheet("color: blue; padding: 5px;")
        layout.addWidget(self.selection_label)

        return panel

    def _on_selection_changed(self, selection):
        """Handle selection changes."""
        if len(selection.feature_ids) > 0:
            self.selections[selection.layer_id] = selection.feature_ids
        elif selection.layer_id in self.selections:
            del self.selections[selection.layer_id]

        # Update label
        total = sum(len(ids) for ids in self.selections.values())
        if total == 0:
            self.selection_label.setText("No selection - click on points to select them")
        else:
            self.selection_label.setText(f"Selected {total} feature(s)")

    def _recolor_selected(self, color):
        """Recolor all selected features to the given QColor."""
        if not self.selections:
            QtWidgets.QMessageBox.information(
                self,
                "No Selection",
                "Please select some features first by clicking on them."
            )
            return

        # Recolor selected features on each layer
        for layer_id, feature_ids in self.selections.items():
            if layer_id == self.vector_layer.id:
                # Vector layer: use update_feature_styles
                styles = [
                    PointStyle(
                        radius=12.0,
                        fill_color=color,
                        stroke_color=QColor("black"),
                        stroke_width=2.0
                    )
                    for _ in feature_ids
                ]
                self.vector_layer.update_feature_styles(feature_ids, styles)

            elif layer_id == self.fast_layer.id:
                # Fast points layer: use set_colors with QColor
                colors = [color for _ in feature_ids]
                self.fast_layer.set_colors(feature_ids, colors)

            elif layer_id == self.geo_layer.id:
                # Geo points layer: use set_colors with QColor
                colors = [color for _ in feature_ids]
                self.geo_layer.set_colors(feature_ids, colors)


def main():
    """Run the recoloring example."""
    app = QtWidgets.QApplication(sys.argv)
    window = RecoloringExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
