#!/usr/bin/env python3
"""Feature Selection Across Multiple Layers

This example demonstrates feature selection capabilities:
- Selecting features by clicking
- Multi-selection with Ctrl/Cmd+click
- Box selection with Ctrl/Cmd+drag
- Selection across different layer types (vector, fast points, geo points)
- Selection state synchronization
- QColor-based visual feedback

Selection is a core feature of pyopenlayersqt for interactive data exploration.
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


class SelectionExample(QtWidgets.QMainWindow):
    """Feature selection example window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Feature Selection Across Multiple Layers")
        self.resize(1200, 800)

        # Create map
        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=10)

        # Track selections
        self.selections = {}

        # Connect selection signal
        self.map_widget.selectionChanged.connect(self._on_selection_changed)

        # Add layers with different types
        self._add_vector_layer()
        self._add_fast_points_layer()
        self._add_geo_points_layer()

        # Create info panel
        info_panel = self._create_info_panel()

        # Layout
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(info_panel)
        layout.addWidget(self.map_widget, stretch=1)
        self.setCentralWidget(container)

    def _add_vector_layer(self):
        """Add vector points layer."""
        self.vector_layer = self.map_widget.add_vector_layer("vector_points", selectable=True)

        # Add a few large marker points
        coords = [
            (37.7749, -122.4194),  # SF
            (37.8044, -122.2712),  # Oakland
            (37.3382, -121.8863),  # San Jose
        ]
        for i, coord in enumerate(coords):
            self.vector_layer.add_points(
                [coord],
                ids=[f"vector_{i}"],
                style=PointStyle(
                    radius=10.0,
                    fill_color=QColor("crimson"),
                    stroke_color=QColor("darkred"),
                    stroke_width=2.0
                )
            )

    def _add_fast_points_layer(self):
        """Add fast points layer."""
        self.fast_layer = self.map_widget.add_fast_points_layer(
            "fast_points",
            selectable=True,
            style=FastPointsStyle(
                radius=4.0,
                default_color=QColor("green"),
                selected_radius=7.0,
                selected_color=QColor("yellow")
            )
        )

        # Add scattered points
        rng = np.random.default_rng(seed=42)
        n = 100
        lats = 37.5 + rng.random(n) * 0.5
        lons = -122.7 + rng.random(n) * 0.5
        coords = list(zip(lats.tolist(), lons.tolist()))
        ids = [f"fast_{i}" for i in range(n)]
        self.fast_layer.add_points(coords, ids=ids)

    def _add_geo_points_layer(self):
        """Add geo points layer with ellipses."""
        self.geo_layer = self.map_widget.add_fast_geopoints_layer(
            "geo_points",
            selectable=True,
            style=FastGeoPointsStyle(
                point_radius=5.0,
                default_color=QColor("steelblue"),
                selected_color=QColor("orange"),
                ellipse_stroke_color=QColor("steelblue"),
                fill_ellipses=True,
                ellipse_fill_color=QColor(70, 130, 180, 40)
            )
        )

        # Add points with ellipses
        rng = np.random.default_rng(seed=43)
        n = 30
        lats = 37.6 + rng.random(n) * 0.4
        lons = -122.6 + rng.random(n) * 0.4
        coords = list(zip(lats.tolist(), lons.tolist()))
        ids = [f"geo_{i}" for i in range(n)]
        sma_m = (100 + rng.random(n) * 400).tolist()
        smi_m = (50 + rng.random(n) * 200).tolist()
        tilt_deg = (rng.random(n) * 360).tolist()

        self.geo_layer.add_points_with_ellipses(
            coords=coords,
            sma_m=sma_m,
            smi_m=smi_m,
            tilt_deg=tilt_deg,
            ids=ids
        )

    def _create_info_panel(self):
        """Create information panel."""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)

        instructions = QtWidgets.QLabel(
            "Selection Instructions:\n"
            "• Click on any point to select it\n"
            "• Ctrl/Cmd+Click to add to selection (multi-select)\n"
            "• Ctrl/Cmd+Drag to box select multiple points\n"
            "• Click on empty area to clear selection"
        )
        layout.addWidget(instructions)

        self.selection_label = QtWidgets.QLabel("No selection")
        self.selection_label.setStyleSheet("font-weight: bold; color: blue;")
        layout.addWidget(self.selection_label)

        return panel

    def _on_selection_changed(self, selection):
        """Handle selection changes."""
        # Update selections tracking
        if len(selection.feature_ids) > 0:
            self.selections[selection.layer_id] = selection.feature_ids
        elif selection.layer_id in self.selections:
            del self.selections[selection.layer_id]

        # Update display
        total = sum(len(ids) for ids in self.selections.values())
        if total == 0:
            self.selection_label.setText("No selection")
        else:
            breakdown = []
            for layer_id, ids in self.selections.items():
                layer_name = layer_id.split("_")[0]
                breakdown.append(f"{layer_name}: {len(ids)}")
            self.selection_label.setText(
                f"Selected {total} feature(s): {', '.join(breakdown)}"
            )


def main():
    """Run the selection example."""
    app = QtWidgets.QApplication(sys.argv)
    window = SelectionExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
