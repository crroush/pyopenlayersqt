"""Example 07: Plot Integration with Bidirectional Selection Sync.

This example demonstrates:
- High-performance plotting with 200k+ points using PyQtGraph
- Bidirectional selection synchronization between map, table, and plot
- Time-series and scatter plot modes
- Interactive point selection and manipulation

The example creates a FastPointsLayer with synthetic data and displays it in:
1. Map widget (spatial view)
2. Table widget (tabular view)
3. Plot widget (temporal/scatter view)

Selection in any view automatically updates the other views.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List

import numpy as np
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QLabel,
    QSplitter,
)

from pyopenlayersqt import (
    OLMapWidget,
    FastPointsStyle,
    PlotWidget,
    PlotControlWidget,
    TraceStyle,
)
from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget


def generate_synthetic_data(n_points: int = 200000) -> List[Dict]:
    """Generate synthetic geospatial time-series data.

    Args:
        n_points: Number of data points to generate

    Returns:
        List of dictionaries containing lat, lon, timestamp, value, etc.
    """
    print(f"Generating {n_points} synthetic data points...")
    start = time.time()

    rng = np.random.default_rng(42)

    # Generate random locations in a region (e.g., USA-ish)
    lats = 25.0 + rng.random(n_points) * 25.0  # 25°N to 50°N
    lons = -125.0 + rng.random(n_points) * 50.0  # -125°W to -75°W

    # Generate time series (last 30 days)
    base_time = datetime.now() - timedelta(days=30)
    timestamps = [
        base_time + timedelta(seconds=float(i) * 30 * 86400 / n_points)
        for i in range(n_points)
    ]

    # Generate values (simulate temperature, sensor reading, etc.)
    # Add some trend and noise
    trend = np.linspace(15.0, 25.0, n_points)
    noise = rng.normal(0, 3.0, n_points)
    values = trend + noise

    # Generate altitude (for a second dimension)
    altitudes = 50.0 + rng.random(n_points) * 1000.0

    data = []
    layer_id = "synthetic_layer"

    for i in range(n_points):
        data.append({
            "layer_id": layer_id,
            "feature_id": str(i),
            "layer_kind": "fast_points",
            "geom_type": "Point",
            "center_lat": float(lats[i]),
            "center_lon": float(lons[i]),
            "timestamp": timestamps[i].isoformat(),
            "timestamp_unix": timestamps[i].timestamp(),
            "value": float(values[i]),
            "altitude": float(altitudes[i]),
        })

    elapsed = time.time() - start
    print(f"Generated {n_points} points in {elapsed:.2f}s")

    return data


class PlotIntegrationWindow(QMainWindow):
    """Main window demonstrating plot integration with map and table."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("pyopenlayersqt - Plot Integration Demo (200k+ points)")
        self.resize(1800, 1000)

        # Create widgets
        self._build_ui()

        # Create map layer first (so we have the layer ID)
        self._create_map_layer()

        # Generate data with correct layer_id
        self.data = generate_synthetic_data(200000)
        # Update layer_id to match the actual layer
        for d in self.data:
            d["layer_id"] = self.fast_layer.id

        # Add data to map
        self._add_points_to_map()

        # Add data to table
        self._populate_table()

        # Initial plot setup
        self._initial_plot_setup()

    def _build_ui(self) -> None:
        """Build the user interface."""
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)

        # Info label
        info = QLabel(
            "Plot Integration Demo: 200k points with bidirectional selection sync.\n"
            "• Select points in map/table/plot - selection syncs across all views\n"
            "• Ctrl+Drag for box select, Shift+Drag for box zoom (matches map behavior)\n"
            "• Left-Drag to pan, Right-Drag for alt box zoom, Mouse wheel to zoom\n"
            "• Use plot controls to change X/Y axes and delete/color selected points"
        )
        info.setWordWrap(True)
        info.setStyleSheet("padding: 10px; background-color: #e8f4f8; border-radius: 5px;")
        main_layout.addWidget(info)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left side: Map and Table
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Map widget
        self.map_widget = OLMapWidget(center=(37.5, -100.0), zoom=4)
        self.map_widget.selectionChanged.connect(self._on_map_selection)

        # Table widget
        columns = [
            ColumnSpec("Feature ID", lambda r: r.get("feature_id", "")[:10]),
            ColumnSpec("Lat", lambda r: r.get("center_lat", ""),
                      fmt=lambda v: f"{float(v):.4f}" if v != "" else ""),
            ColumnSpec("Lon", lambda r: r.get("center_lon", ""),
                      fmt=lambda v: f"{float(v):.4f}" if v != "" else ""),
            ColumnSpec("Timestamp", lambda r: r.get("timestamp", "")[:19]),
            ColumnSpec("Value", lambda r: r.get("value", ""),
                      fmt=lambda v: f"{float(v):.2f}" if v != "" else ""),
            ColumnSpec("Altitude", lambda r: r.get("altitude", ""),
                      fmt=lambda v: f"{float(v):.1f}" if v != "" else ""),
        ]

        self.table_widget = FeatureTableWidget(
            columns=columns,
            key_fn=lambda r: (str(r.get("layer_id", "")), str(r.get("feature_id", ""))),
            debounce_ms=90,
        )
        self.table_widget.selectionKeysChanged.connect(self._on_table_selection)

        # Split map and table vertically
        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.addWidget(self.map_widget)
        left_splitter.addWidget(self.table_widget)
        left_splitter.setStretchFactor(0, 2)
        left_splitter.setStretchFactor(1, 1)

        left_layout.addWidget(left_splitter)

        # Right side: Plot with controls
        right_widget = QWidget()
        right_layout = QHBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Plot control widget
        self.plot_ctrl = PlotControlWidget()
        self.plot_ctrl.dataRequested.connect(self._on_plot_data_requested)
        self.plot_ctrl.clearRequested.connect(self._on_plot_clear)
        self.plot_ctrl.deleteSelectedRequested.connect(self._on_plot_delete)
        self.plot_ctrl.colorSelectedRequested.connect(self._on_plot_color)

        # Set available fields (hardcoded for synthetic data)
        fields = ["timestamp_unix", "value", "altitude", "center_lat", "center_lon"]
        self.plot_ctrl.set_available_fields(fields)

        # Plot widget
        self.plot_widget = PlotWidget()
        self.plot_widget.selectionKeysChanged.connect(self._on_plot_selection)

        right_layout.addWidget(self.plot_ctrl, 0)
        right_layout.addWidget(self.plot_widget, 1)

        # Add to main splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

    def _create_map_layer(self) -> None:
        """Create the fast points layer (data will be added later)."""
        self.fast_layer = self.map_widget.add_fast_points_layer(
            name="synthetic_data",
            selectable=True,
            style=FastPointsStyle(
                radius=2.5,
                default_rgba=(0, 120, 200, 180),
                selected_radius=6.0,
                selected_rgba=(255, 255, 0, 255),
            ),
            cell_size_m=1000.0,
        )

    def _add_points_to_map(self) -> None:
        """Add data to map as fast points layer."""
        print("Adding points to map...")
        start = time.time()

        # Add points
        coords = [(d["center_lat"], d["center_lon"]) for d in self.data]
        ids = [str(d["feature_id"]) for d in self.data]

        self.fast_layer.add_points(coords, ids=ids)

        elapsed = time.time() - start
        print(f"Added {len(coords)} points to map in {elapsed:.2f}s")

    def _populate_table(self) -> None:
        """Add data to table."""
        print("Adding rows to table...")
        start = time.time()

        self.table_widget.append_rows(self.data)

        elapsed = time.time() - start
        print(f"Added {len(self.data)} rows to table in {elapsed:.2f}s")

    def _initial_plot_setup(self) -> None:
        """Setup initial plot with time-series view."""
        print("Setting up initial plot (time-series)...")
        start = time.time()

        def key_fn(r):
            return (str(r.get("layer_id", "")), str(r.get("feature_id", "")))

        self.plot_widget.set_data(
            data_rows=self.data,
            key_fn=key_fn,
            x_field="timestamp_unix",
            y_field="value",
            trace_style=TraceStyle(
                color='#0078c8',
                width=1.0,
                symbol='o',
                symbol_size=3.0,
            )
        )

        elapsed = time.time() - start
        print(f"Created plot with {len(self.data)} points in {elapsed:.2f}s")

    def _on_map_selection(self, sel) -> None:
        """Handle selection from map."""
        layer_id = getattr(sel, "layer_id", "")
        fids = list(getattr(sel, "feature_ids", []) or [])

        if not layer_id or not fids:
            return

        keys = [(layer_id, str(fid)) for fid in fids]

        # Update table and plot
        self.table_widget.select_keys(keys, clear_first=True)
        self.plot_widget.select_keys(keys, clear_first=True)

    def _on_table_selection(self, keys: List) -> None:
        """Handle selection from table."""
        if not keys:
            # Clear selections
            self.map_widget.set_fast_points_selection(self.fast_layer.id, [])
            self.plot_widget.clear_selection()
            return

        # Group by layer
        by_layer: Dict[str, List[str]] = {}
        for layer_id, fid in keys:
            by_layer.setdefault(str(layer_id), []).append(str(fid))

        # Update map
        for layer_id, fids in by_layer.items():
            self.map_widget.set_fast_points_selection(self.fast_layer.id, fids)

        # Update plot
        self.plot_widget.select_keys(keys, clear_first=True)

    def _on_plot_selection(self, keys: List) -> None:
        """Handle selection from plot."""
        # PySide6 Signal(list) converts tuples to lists, so convert back
        keys = [tuple(k) if isinstance(k, list) else k for k in keys]

        # Update table
        self.table_widget.select_keys(keys, clear_first=True)

        # Also update map directly (table won't emit signal during programmatic selection)
        if not keys:
            self.map_widget.set_fast_points_selection(self.fast_layer.id, [])
            return

        # Group by layer and update map
        by_layer: Dict[str, List[str]] = {}
        for layer_id, fid in keys:
            by_layer.setdefault(str(layer_id), []).append(str(fid))

        for layer_id, fids in by_layer.items():
            if layer_id == self.fast_layer.id:
                self.map_widget.set_fast_points_selection(self.fast_layer.id, fids)

    def _on_plot_data_requested(self, x_field: str, y_field: str) -> None:
        """Handle request to update plot axes."""
        print(f"Updating plot: X={x_field}, Y={y_field}")

        def key_fn(r):
            return (str(r.get("layer_id", "")), str(r.get("feature_id", "")))

        self.plot_widget.set_data(
            data_rows=self.data,
            key_fn=key_fn,
            x_field=x_field,
            y_field=y_field,
            trace_style=TraceStyle(
                color='#0078c8',
                width=1.0,
                symbol='o',
                symbol_size=3.0,
            )
        )

    def _on_plot_clear(self) -> None:
        """Handle plot clear request."""
        self.plot_widget.clear_plot()

    def _on_plot_delete(self) -> None:
        """Handle delete selected from plot."""
        deleted_keys = self.plot_widget.delete_selected()

        if not deleted_keys:
            return

        # Convert to set for O(1) lookup performance
        deleted_keys_set = set(deleted_keys)

        # Remove from table using predicate
        def predicate(row):
            key = (str(row.get("layer_id", "")), str(row.get("feature_id", "")))
            return key in deleted_keys_set

        self.table_widget.remove_where(predicate)

        # Remove from data list - optimized with set membership
        self.data = [
            d for d in self.data
            if (str(d.get("layer_id", "")), str(d.get("feature_id", ""))) not in deleted_keys_set
        ]

        # Remove from map by layer
        by_layer = {}
        for layer_id, fid in deleted_keys:
            by_layer.setdefault(layer_id, []).append(fid)

        for layer_id, fids in by_layer.items():
            if layer_id == self.fast_layer.id:
                self.fast_layer.remove_points(fids)

        print(f"Deleted {len(deleted_keys)} points")

    def _on_plot_color(self, color: str) -> None:
        """Handle color selected points."""
        self.plot_widget.recolor_selected(color)


def main() -> None:
    """Run the plot integration example."""
    app = QtWidgets.QApplication(sys.argv)

    window = PlotIntegrationWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
