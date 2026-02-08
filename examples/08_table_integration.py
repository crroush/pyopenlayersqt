#!/usr/bin/env python3
"""Map-Table Bidirectional Synchronization

This example demonstrates the core table integration feature:
- FeatureTableWidget for displaying feature attributes
- Bidirectional selection sync between map and table
- Click on map -> updates table selection
- Click on table -> updates map selection
- Handling large datasets efficiently (10,000+ features)
- QColor-based point styling

This is a CORE feature of pyopenlayersqt for data exploration workflows.
"""

import sys

import numpy as np
from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, PointStyle, FastPointsStyle
from pyopenlayersqt.features_table import FeatureTableWidget, ColumnSpec


class TableIntegrationExample(QtWidgets.QMainWindow):
    """Map-table integration example window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Map-Table Bidirectional Synchronization")
        self.resize(1400, 900)

        # Create map widget
        self.map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)

        # Add vector layer with a few notable points
        self.vector_layer = self.map_widget.add_vector_layer("cities", selectable=True)

        # Add fast points layer for large dataset
        self.fast_layer = self.map_widget.add_fast_points_layer(
            "measurements",
            selectable=True,
            style=FastPointsStyle(
                radius=3.0,
                default_color=QColor("green"),
                selected_radius=6.0,
                selected_color=QColor("yellow")
            )
        )

        # Create feature table
        self.table = self._create_table()

        # Connect signals for bidirectional sync
        self.map_widget.selectionChanged.connect(self._on_map_selection)
        self.table.selectionKeysChanged.connect(self._on_table_selection)

        # Add data after map is ready
        self.map_widget.ready.connect(self._add_data)

        # Layout
        splitter = QtWidgets.QSplitter(QtWidgets.Qt.Horizontal)
        splitter.addWidget(self.table)
        splitter.addWidget(self.map_widget)
        splitter.setStretchFactor(0, 1)  # Table gets 1/3
        splitter.setStretchFactor(1, 2)  # Map gets 2/3

        # Add info panel
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        info = QtWidgets.QLabel(
            "Click on map points to select them (updates table). "
            "Click on table rows to select features (updates map). "
            "Demonstrates bidirectional synchronization."
        )
        info.setWordWrap(True)
        info.setStyleSheet("background-color: #e8f4f8; padding: 8px; border-radius: 4px;")
        layout.addWidget(info)
        layout.addWidget(splitter, stretch=1)

        self.setCentralWidget(container)

    def _create_table(self):
        """Create the feature table widget."""
        columns = [
            ColumnSpec("Layer", lambda r: r.get("layer_kind", "")),
            ColumnSpec("Type", lambda r: r.get("geom_type", "")),
            ColumnSpec("ID", lambda r: r.get("feature_id", "")),
            ColumnSpec("Value", lambda r: r.get("value", "")),
        ]

        return FeatureTableWidget(
            columns=columns,
            key_fn=lambda r: (str(r.get("layer_id")), str(r.get("feature_id"))),
            sorting_enabled=True
        )

    def _add_data(self):
        """Add sample data to map and table."""
        # Add a few city points to vector layer
        cities = [
            (37.7749, -122.4194, "San Francisco", 850000),
            (34.0522, -118.2437, "Los Angeles", 4000000),
            (47.6062, -122.3321, "Seattle", 750000),
        ]

        for lat, lon, city_name, population in cities:
            self.vector_layer.add_points(
                [(lat, lon)],
                ids=[city_name],
                style=PointStyle(
                    radius=12.0,
                    fill_color=QColor("red"),
                    stroke_color=QColor("darkred"),
                    stroke_width=2.0
                )
            )

            # Add to table
            self.table.append_rows([{
                "layer_kind": "cities",
                "layer_id": self.vector_layer.id,
                "feature_id": city_name,
                "geom_type": "point",
                "value": f"{population:,}",
            }])

        # Add many fast points
        rng = np.random.default_rng(seed=42)
        n_points = 10000

        lats = 32.0 + rng.random(n_points) * 15.0
        lons = -125.0 + rng.random(n_points) * 15.0
        coords = list(zip(lats.tolist(), lons.tolist()))
        ids = [f"meas_{i}" for i in range(n_points)]
        values = (rng.random(n_points) * 100).tolist()

        self.fast_layer.add_points(coords, ids=ids)

        # Add to table (using generator for memory efficiency)
        rows = (
            {
                "layer_kind": "measurements",
                "layer_id": self.fast_layer.id,
                "feature_id": ids[i],
                "geom_type": "point",
                "value": f"{values[i]:.1f}",
            }
            for i in range(n_points)
        )
        self.table.append_rows(rows)

        print(f"Added {len(cities)} cities and {n_points} measurements")

    def _on_map_selection(self, selection):
        """Handle map selection changes -> update table."""
        keys = [(selection.layer_id, fid) for fid in selection.feature_ids]
        self.table.select_keys(keys, clear_first=True)

    def _on_table_selection(self, keys):
        """Handle table selection changes -> update map."""
        # Group by layer
        by_layer = {}
        for layer_id, fid in keys:
            by_layer.setdefault(layer_id, []).append(fid)

        # Update each layer's selection
        for layer_id, fids in by_layer.items():
            if layer_id == self.vector_layer.id:
                self.map_widget.set_vector_selection(layer_id, fids)
            elif layer_id == self.fast_layer.id:
                self.map_widget.set_fast_points_selection(layer_id, fids)


def main():
    """Run the table integration example."""
    app = QtWidgets.QApplication(sys.argv)
    window = TableIntegrationExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
