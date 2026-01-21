#!/usr/bin/env python3
"""Complete Example with Feature Table

This example demonstrates:
- Creating a map widget with custom initial view
- Adding multiple layer types (vector, fast points)
- Feature table integration
- Bidirectional selection synchronization between map and table
- Handling 10,000+ points efficiently
"""

from PySide6 import QtWidgets
from pyopenlayersqt import (
    OLMapWidget,
    PointStyle,
    FastPointsStyle,
)
from pyopenlayersqt.features_table import FeatureTableWidget, ColumnSpec
import sys
import numpy as np


class MapWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pyopenlayersqt Complete Example")
        
        # Create map widget centered on US West Coast at appropriate zoom
        self.map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)
        
        # Add layers
        self.vector = self.map_widget.add_vector_layer("vector", selectable=True)
        
        self.fast = self.map_widget.add_fast_points_layer(
            "fast_points",
            selectable=True,
            style=FastPointsStyle(
                radius=2.5,
                default_rgba=(0, 180, 0, 180)
            )
        )
        
        # Create feature table
        columns = [
            ColumnSpec("Layer", lambda r: r.get("layer_kind", "")),
            ColumnSpec("Type", lambda r: r.get("geom_type", "")),
            ColumnSpec("ID", lambda r: r.get("feature_id", "")),
        ]
        
        self.table = FeatureTableWidget(
            columns=columns,
            key_fn=lambda r: (str(r.get("layer_id")), str(r.get("feature_id")))
        )
        
        # Connect signals for bidirectional selection sync
        self.map_widget.selectionChanged.connect(self.on_map_selection)
        self.table.selectionKeysChanged.connect(self.on_table_selection)
        
        # Layout
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.map_widget, 2)
        self.setCentralWidget(container)
        
        # Add some data after map is ready
        self.map_widget.ready.connect(self.add_sample_data)
    
    def add_sample_data(self):
        # Add a vector point (latitude, longitude)
        self.vector.add_points(
            [(37.7749, -122.4194)],
            ids=["sf"],
            style=PointStyle(radius=8.0, fill_color="#ff3333")
        )
        
        # Add to table
        self.table.append_rows([{
            "layer_kind": "vector",
            "layer_id": self.vector.id,
            "feature_id": "sf",
            "geom_type": "point"
        }])
        
        # Add 10,000 fast points in the visible area
        rng = np.random.default_rng()
        n = 10000
        lats = 32 + rng.random(n) * 10
        lons = -125 + rng.random(n) * 10
        coords = list(zip(lats.tolist(), lons.tolist()))
        ids = [f"fp{i}" for i in range(n)]
        self.fast.add_points(coords, ids=ids)
        
        # Add fast points to table (using generator for memory efficiency)
        rows = (
            {
                "layer_kind": "fast_points",
                "layer_id": self.fast.id,
                "feature_id": ids[i],
                "geom_type": "point"
            }
            for i in range(n)
        )
        self.table.append_rows(rows)
        
        print(f"Added {n} fast points and 1 vector point to map and table")
    
    def on_map_selection(self, selection):
        """Handle selection from map -> update table"""
        keys = [(selection.layer_id, fid) for fid in selection.feature_ids]
        self.table.select_keys(keys, clear_first=True)
    
    def on_table_selection(self, keys):
        """Handle selection from table -> update map"""
        # Group by layer
        by_layer = {}
        for layer_id, fid in keys:
            by_layer.setdefault(layer_id, []).append(fid)
        
        # Update each layer's selection
        for layer_id, fids in by_layer.items():
            if layer_id == self.vector.id:
                self.map_widget.set_vector_selection(layer_id, fids)
            elif layer_id == self.fast.id:
                self.map_widget.set_fast_points_selection(layer_id, fids)


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = MapWindow()
    window.resize(1200, 800)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
