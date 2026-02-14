#!/usr/bin/env python3
"""Map-Table Bidirectional Synchronization with Interactive Add/Delete

This example demonstrates the core table integration feature:
- FeatureTableWidget for displaying feature attributes
- Bidirectional selection sync between map and table
- Click on map -> updates table selection
- Click on table -> updates map selection
- Interactive adding of points to all 3 layer types (Vector, FastPoints, FastGeoPoints)
- Deleting selected features via button or Delete key
- Handling large datasets efficiently
- QColor-based point styling

This is a CORE feature of pyopenlayersqt for data exploration workflows.
"""

import sys

import numpy as np
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut

from pyopenlayersqt import OLMapWidget, PointStyle, FastPointsStyle, FastGeoPointsStyle
from pyopenlayersqt.features_table import FeatureTableWidget, ColumnSpec


class TableIntegrationExample(QtWidgets.QMainWindow):
    """Map-table integration example with interactive add/delete."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Interactive Map-Table Integration")
        self.resize(1600, 900)

        # Counters for generating unique IDs
        self.city_counter = 0
        self.meas_counter = 0
        self.geo_counter = 0

        # Create map widget
        self.map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)

        # Add vector layer for cities
        self.vector_layer = self.map_widget.add_vector_layer("cities", selectable=True)

        # Add fast points layer for measurements
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

        # Add fast geo points layer for uncertainty ellipses
        self.geo_layer = self.map_widget.add_fast_geopoints_layer(
            "geo_points",
            selectable=True,
            style=FastGeoPointsStyle(
                point_radius=4.0,
                default_color=QColor("#1e88e5"),
                selected_point_radius=7.0,
                selected_color=QColor("#d81b60"),
                ellipse_stroke_color=QColor("#1e88e5"),
                selected_ellipse_stroke_color=QColor("#d81b60")
            )
        )

        self._all_ellipses_visible = True
        self._selected_ellipses_visible = False

        # Create feature table
        self.table = self._create_table()

        # Cache map-side selection per layer; map events are emitted per-layer.
        self._map_selection_by_layer = {}

        # Connect signals for bidirectional sync
        self.map_widget.selectionChanged.connect(self._on_map_selection)
        self.table.selectionKeysChanged.connect(self._on_table_selection)

        # Add initial data after map is ready
        self.map_widget.ready.connect(self._add_initial_data)

        # Create control panel
        controls = self._create_controls()

        # Layout: controls on left, table in middle, map on right
        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        splitter.addWidget(controls)
        splitter.addWidget(self.table)
        splitter.addWidget(self.map_widget)
        splitter.setStretchFactor(0, 1)  # Controls
        splitter.setStretchFactor(1, 2)  # Table
        splitter.setStretchFactor(2, 3)  # Map

        # Add info panel
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        info = QtWidgets.QLabel(
            "Add points to any layer type, select them on map or table, "
            "and delete with button or Delete key. "
            "Use ellipse checkboxes to hide all ellipses or show only selected ellipses. "
            "Demonstrates full CRUD operations with bidirectional sync."
        )
        info.setWordWrap(True)
        info.setStyleSheet("background-color: #e8f4f8; padding: 8px; border-radius: 4px;")
        layout.addWidget(info)
        layout.addWidget(splitter, stretch=1)

        self.setCentralWidget(container)

        # Add Delete key shortcut
        delete_shortcut = QShortcut(QKeySequence.Delete, self)
        delete_shortcut.activated.connect(self._delete_selected)

    def _create_controls(self):
        """Create the control panel for adding/deleting features."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QtWidgets.QLabel("<b>Layer Controls</b>")
        layout.addWidget(title)

        # Vector Layer (Cities) controls
        layout.addWidget(QtWidgets.QLabel("<b>Vector Layer (Cities)</b>"))
        self.vector_count = QtWidgets.QSpinBox()
        self.vector_count.setRange(1, 1000)
        self.vector_count.setValue(5)
        vector_btn = QtWidgets.QPushButton("Add Cities")
        vector_btn.clicked.connect(self._add_vector_points)
        layout.addWidget(QtWidgets.QLabel("Number of cities:"))
        layout.addWidget(self.vector_count)
        layout.addWidget(vector_btn)

        layout.addWidget(QtWidgets.QLabel(""))  # Spacer

        # FastPointsLayer (Measurements) controls
        layout.addWidget(QtWidgets.QLabel("<b>FastPoints Layer (Measurements)</b>"))
        self.fast_count = QtWidgets.QSpinBox()
        self.fast_count.setRange(1, 50000)
        self.fast_count.setValue(100)
        fast_btn = QtWidgets.QPushButton("Add Measurements")
        fast_btn.clicked.connect(self._add_fast_points)
        layout.addWidget(QtWidgets.QLabel("Number of measurements:"))
        layout.addWidget(self.fast_count)
        layout.addWidget(fast_btn)

        layout.addWidget(QtWidgets.QLabel(""))  # Spacer

        # FastGeoPointsLayer (Geo Uncertainty) controls
        layout.addWidget(QtWidgets.QLabel("<b>FastGeoPoints Layer (Uncertainty)</b>"))
        self.geo_count = QtWidgets.QSpinBox()
        self.geo_count.setRange(1, 50000)
        self.geo_count.setValue(50)
        geo_btn = QtWidgets.QPushButton("Add Geo Points")
        geo_btn.clicked.connect(self._add_geo_points)
        layout.addWidget(QtWidgets.QLabel("Number of geo points:"))
        layout.addWidget(self.geo_count)
        layout.addWidget(geo_btn)

        self.show_all_ellipses_checkbox = QtWidgets.QCheckBox("Show All Ellipses")
        self.show_all_ellipses_checkbox.setChecked(True)
        self.show_all_ellipses_checkbox.toggled.connect(self._on_show_all_ellipses_toggled)
        layout.addWidget(self.show_all_ellipses_checkbox)

        self.show_selected_ellipses_checkbox = QtWidgets.QCheckBox("Show Selected Ellipses")
        self.show_selected_ellipses_checkbox.setChecked(False)
        self.show_selected_ellipses_checkbox.toggled.connect(
            self._on_show_selected_ellipses_toggled
        )
        layout.addWidget(self.show_selected_ellipses_checkbox)

        layout.addWidget(QtWidgets.QLabel(""))  # Spacer

        # Delete button
        delete_btn = QtWidgets.QPushButton("Delete Selected (or press Delete key)")
        delete_btn.setStyleSheet("background-color: #ffcccc; font-weight: bold;")
        delete_btn.clicked.connect(self._delete_selected)
        layout.addWidget(delete_btn)

        # Stats label
        self.stats_label = QtWidgets.QLabel("Total features: 0")
        layout.addWidget(self.stats_label)

        layout.addStretch()
        return widget

    def _on_show_all_ellipses_toggled(self, checked):
        """Toggle visibility of all ellipses globally."""
        self._all_ellipses_visible = bool(checked)
        self._apply_ellipse_visibility()

    def _on_show_selected_ellipses_toggled(self, checked):
        """Toggle visibility of selected ellipses."""
        self._selected_ellipses_visible = bool(checked)
        self._apply_ellipse_visibility()

    def _apply_ellipse_visibility(self):
        """Apply current ellipse visibility settings to the geo layer."""
        # "Show All Ellipses" controls unselected ellipses.
        self.geo_layer.set_ellipses_visible(self._all_ellipses_visible)

        # Selected ellipses are visible when either all ellipses are shown,
        # or when the selected-ellipse checkbox is explicitly enabled.
        show_selected = self._all_ellipses_visible or self._selected_ellipses_visible
        self.geo_layer.set_selected_ellipses_visible(show_selected)

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

    def _add_initial_data(self):
        """Add initial sample data to map and table."""
        # Add a few cities to show the example
        self.city_counter = 3
        cities = [
            (37.7749, -122.4194, "San Francisco"),
            (34.0522, -118.2437, "Los Angeles"),
            (47.6062, -122.3321, "Seattle"),
        ]

        for i, (lat, lon, city_name) in enumerate(cities):
            self.vector_layer.add_points(
                [(lat, lon)],
                ids=[f"city_{i}"],
                style=PointStyle(
                    radius=10.0,
                    fill_color=QColor("red"),
                    stroke_color=QColor("darkred"),
                    stroke_width=2.0
                )
            )

            # Add to table
            self.table.append_rows([{
                "layer_kind": "cities",
                "layer_id": self.vector_layer.id,
                "feature_id": f"city_{i}",
                "geom_type": "point",
                "value": city_name,
            }])

        self._update_stats()
        print(f"Added {len(cities)} initial cities")

    def _add_vector_points(self):
        """Add random city points to vector layer."""
        count = self.vector_count.value()
        rng = np.random.default_rng()

        # Generate random points in California area
        lats = 32.5 + rng.random(count) * 10.0
        lons = -124.0 + rng.random(count) * 10.0

        for i in range(count):
            city_id = f"city_{self.city_counter}"
            self.city_counter += 1

            self.vector_layer.add_points(
                [(lats[i], lons[i])],
                ids=[city_id],
                style=PointStyle(
                    radius=8.0,
                    fill_color=QColor("red"),
                    stroke_color=QColor("darkred"),
                    stroke_width=1.5
                )
            )

            # Add to table
            self.table.append_rows([{
                "layer_kind": "cities",
                "layer_id": self.vector_layer.id,
                "feature_id": city_id,
                "geom_type": "point",
                "value": f"City #{self.city_counter}",
            }])

        self._update_stats()
        print(f"Added {count} cities")

    def _add_fast_points(self):
        """Add random measurement points to fast points layer."""
        count = self.fast_count.value()
        rng = np.random.default_rng()

        # Generate random points
        lats = 32.0 + rng.random(count) * 15.0
        lons = -125.0 + rng.random(count) * 15.0
        coords = list(zip(lats.tolist(), lons.tolist()))

        # Generate IDs
        ids = [f"meas_{self.meas_counter + i}" for i in range(count)]
        self.meas_counter += count

        # Generate random values
        values = (rng.random(count) * 100).tolist()

        # Add to layer
        self.fast_layer.add_points(coords, ids=ids)

        # Add to table
        rows = (
            {
                "layer_kind": "measurements",
                "layer_id": self.fast_layer.id,
                "feature_id": ids[i],
                "geom_type": "point",
                "value": f"{values[i]:.1f}",
            }
            for i in range(count)
        )
        self.table.append_rows(rows)

        self._update_stats()
        print(f"Added {count} measurements")

    def _add_geo_points(self):
        """Add random geo uncertainty points to fast geo points layer."""
        count = self.geo_count.value()
        rng = np.random.default_rng()

        # Generate random points
        lats = 32.0 + rng.random(count) * 15.0
        lons = -125.0 + rng.random(count) * 15.0
        coords = list(zip(lats.tolist(), lons.tolist()))

        # Generate uncertainty ellipse parameters (larger for easier visibility)
        sma_m = (500.0 + rng.random(count) * 3500.0).tolist()  # 500-4000m
        smi_m = (250.0 + rng.random(count) * 1750.0).tolist()  # 250-2000m
        tilt_deg = (rng.random(count) * 360.0).tolist()       # 0-360 degrees

        # Generate IDs
        ids = [f"geo_{self.geo_counter + i}" for i in range(count)]
        self.geo_counter += count

        # Add to layer
        self.geo_layer.add_points_with_ellipses(
            coords=coords,
            sma_m=sma_m,
            smi_m=smi_m,
            tilt_deg=tilt_deg,
            ids=ids
        )

        # Add to table
        rows = (
            {
                "layer_kind": "geo_points",
                "layer_id": self.geo_layer.id,
                "feature_id": ids[i],
                "geom_type": "geo_point",
                "value": f"σ={sma_m[i]:.0f}m",
            }
            for i in range(count)
        )
        self.table.append_rows(rows)

        self._update_stats()
        print(f"Added {count} geo points with uncertainty ellipses")

    def _delete_selected(self):
        """Delete currently selected features from map and table."""
        # Get selected keys from table
        selected_keys = self.table.selected_keys()
        if not selected_keys:
            print("No features selected for deletion")
            return

        # Group by layer
        by_layer = {}
        for layer_id, fid in selected_keys:
            by_layer.setdefault(layer_id, []).append(fid)

        # Delete from each layer and clear map-side selection for deleted layers.
        for layer_id, fids in by_layer.items():
            if layer_id == self.vector_layer.id:
                self.vector_layer.remove_features(fids)
                self.map_widget.set_vector_selection(layer_id, [])
                print(f"Deleted {len(fids)} cities")
            elif layer_id == self.fast_layer.id:
                self.fast_layer.remove_points(fids)
                self.map_widget.set_fast_points_selection(layer_id, [])
                print(f"Deleted {len(fids)} measurements")
            elif layer_id == self.geo_layer.id:
                self.geo_layer.remove_ids(fids)
                self.map_widget.set_fast_geopoints_selection(layer_id, [])
                print(f"Deleted {len(fids)} geo points")
            self._map_selection_by_layer[layer_id] = []

        # Remove from table
        self.table.remove_keys(selected_keys)

        self._update_stats()

    def _update_stats(self):
        """Update the statistics label."""
        total = self.table.model.rowCount()
        self.stats_label.setText(f"Total features: {total}")

    def _on_map_selection(self, selection):
        """Handle map selection changes -> update table."""
        self._map_selection_by_layer[selection.layer_id] = list(selection.feature_ids)

        # JS emits selection events per-layer; aggregate all known layer selections
        # so the table reflects multi-layer selection state.
        keys = []
        for layer_id, feature_ids in self._map_selection_by_layer.items():
            keys.extend((layer_id, fid) for fid in feature_ids)

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
            elif layer_id == self.geo_layer.id:
                self.map_widget.set_fast_geopoints_selection(layer_id, fids)


def main():
    """Run the interactive table integration example."""
    app = QtWidgets.QApplication(sys.argv)
    window = TableIntegrationExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
