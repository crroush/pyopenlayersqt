#!/usr/bin/env python3
"""Range Slider Filter Example

This example demonstrates the RangeSliderWidget with map and table filtering:
- Dual-handle range slider for numeric and timestamp filtering
- Bidirectional sync between map, table, and range sliders
- Features can be filtered by multiple attributes
- Filtering hides features temporarily (they can be shown again)
- Works with FastPointsLayer and FastGeoPointsLayer
"""

from datetime import datetime, timedelta
import sys

import numpy as np
from PySide6 import QtWidgets

from pyopenlayersqt import (
    OLMapWidget,
    FastPointsStyle,
)
from pyopenlayersqt.features_table import FeatureTableWidget, ColumnSpec
from pyopenlayersqt.range_slider import RangeSliderWidget


class RangeFilterWindow(QtWidgets.QMainWindow):
    """Main window demonstrating range slider filtering."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Range Slider Filter Example - pyopenlayersqt")

        # Create map widget
        self.map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)

        # Add fast points layer
        self.fast_layer = self.map_widget.add_fast_points_layer(
            "fast_points",
            selectable=True,
            style=FastPointsStyle(
                radius=3.0,
                default_rgba=(0, 180, 100, 200),
                selected_radius=6.0,
                selected_rgba=(255, 200, 0, 255)
            )
        )

        # Store feature data for filtering
        self.feature_data = []

        # Create feature table
        def format_timestamp(ts_str):
            """Format ISO8601 timestamp for display."""
            if not ts_str:
                return ""
            try:
                dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                return dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                return ts_str

        columns = [
            ColumnSpec("ID", lambda r: r["feature_id"]),
            ColumnSpec("Value", lambda r: r["value"], fmt=lambda v: f"{v:.1f}"),
            ColumnSpec("Timestamp", lambda r: r["timestamp"], fmt=format_timestamp),
            ColumnSpec("Lat", lambda r: r["lat"], fmt=lambda v: f"{v:.4f}"),
            ColumnSpec("Lon", lambda r: r["lon"], fmt=lambda v: f"{v:.4f}"),
        ]

        self.table = FeatureTableWidget(
            columns=columns,
            key_fn=lambda r: (str(r["layer_id"]), str(r["feature_id"]))
        )

        # Create range slider widgets
        self.value_slider = RangeSliderWidget(
            min_val=0.0,
            max_val=100.0,
            step=1.0,
            label="Filter by Value"
        )
        self.value_slider.rangeChanged.connect(self.on_value_range_changed)

        # For timestamp slider, we'll set it up after generating data
        self.timestamp_slider = None

        # Setup UI layout
        self.setup_ui()

        # Connect signals
        self.map_widget.selectionChanged.connect(self.on_map_selection)
        self.table.selectionKeysChanged.connect(self.on_table_selection)

        # Add sample data after map is ready
        self.map_widget.ready.connect(self.add_sample_data)

    def setup_ui(self):
        """Setup the user interface layout."""
        # Main container
        container = QtWidgets.QWidget()
        main_layout = QtWidgets.QHBoxLayout(container)

        # Left panel: table and controls
        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Add controls section
        controls_group = QtWidgets.QGroupBox("Range Filters")
        controls_layout = QtWidgets.QVBoxLayout(controls_group)
        controls_layout.addWidget(self.value_slider)

        # Placeholder for timestamp slider (created after data)
        self.timestamp_slider_container = QtWidgets.QWidget()
        self.timestamp_slider_layout = QtWidgets.QVBoxLayout(self.timestamp_slider_container)
        self.timestamp_slider_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(self.timestamp_slider_container)

        # Reset button
        reset_btn = QtWidgets.QPushButton("Reset Filters")
        reset_btn.clicked.connect(self.reset_filters)
        controls_layout.addWidget(reset_btn)

        # Info label
        self.info_label = QtWidgets.QLabel("Loading data...")
        controls_layout.addWidget(self.info_label)

        left_layout.addWidget(controls_group)
        left_layout.addWidget(self.table, 1)

        # Add panels to main layout
        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(self.map_widget, 2)

        self.setCentralWidget(container)

    def add_sample_data(self):
        """Generate and add sample data with values and timestamps."""
        print("Generating sample data...")

        # Generate random data
        rng = np.random.default_rng(42)
        n = 5000

        # Random locations in visible area
        lats = 32 + rng.random(n) * 10
        lons = -125 + rng.random(n) * 10

        # Random values (0-100)
        values = rng.random(n) * 100

        # Random timestamps over 30 days
        base_time = datetime(2024, 1, 1)
        timestamps = []
        for i in range(n):
            delta = timedelta(days=rng.random() * 30)
            ts = base_time + delta
            timestamps.append(ts.isoformat() + 'Z')

        # Color points by value (green to red)
        colors = []
        for val in values:
            # Green (low value) to red (high value)
            r = int(val * 2.55)
            g = int((100 - val) * 2.55)
            b = 50
            colors.append((r, g, b, 200))

        # Create feature IDs and coordinates
        coords = list(zip(lats.tolist(), lons.tolist()))
        ids = [f"fp{i}" for i in range(n)]

        # Add points to map
        self.fast_layer.add_points(coords, ids=ids, colors_rgba=colors)

        # Store feature data
        self.feature_data = []
        for i in range(n):
            self.feature_data.append({
                "layer_id": self.fast_layer.id,
                "feature_id": ids[i],
                "value": float(values[i]),
                "timestamp": timestamps[i],
                "lat": float(lats[i]),
                "lon": float(lons[i]),
            })

        # Add to table
        self.table.append_rows(self.feature_data)

        # Create timestamp slider with unique sorted timestamps
        unique_timestamps = sorted(set(timestamps))
        self.timestamp_slider = RangeSliderWidget(
            values=unique_timestamps,
            label="Filter by Timestamp"
        )
        self.timestamp_slider.rangeChanged.connect(self.on_timestamp_range_changed)
        self.timestamp_slider_layout.addWidget(self.timestamp_slider)

        # Update info
        self.info_label.setText(f"Total: {n} points\nVisible: {n}")

        print(f"Added {n} points to map and table")
        print("Try adjusting the range sliders to filter points!")

    def on_value_range_changed(self, _min_val, _max_val):
        """Filter features by value range."""
        self.apply_filters()

    def on_timestamp_range_changed(self, _min_ts, _max_ts):
        """Filter features by timestamp range."""
        self.apply_filters()

    def apply_filters(self):
        """Apply all active filters to map and table."""
        if not self.feature_data:
            return

        # Get current filter ranges
        value_min, value_max = self.value_slider.get_range()

        # Get timestamp range if slider exists
        if self.timestamp_slider:
            ts_min, ts_max = self.timestamp_slider.get_range()
        else:
            ts_min = ts_max = None

        # Find features to hide and show
        hidden_ids = []
        visible_ids = []

        for feat in self.feature_data:
            val = feat["value"]
            ts = feat["timestamp"]
            fid = feat["feature_id"]

            # Check if feature passes all filters
            passes = True

            # Value filter
            if not value_min <= val <= value_max:
                passes = False

            # Timestamp filter
            if ts_min and ts_max:
                if not ts_min <= ts <= ts_max:
                    passes = False

            if passes:
                visible_ids.append(fid)
            else:
                hidden_ids.append(fid)

        # Apply filters to map
        if hidden_ids:
            self.fast_layer.hide_features(hidden_ids)
        if visible_ids:
            self.fast_layer.show_features(visible_ids)

        # Apply filters to table
        hidden_keys = [(self.fast_layer.id, fid) for fid in hidden_ids]
        visible_keys = [(self.fast_layer.id, fid) for fid in visible_ids]

        if hidden_keys:
            self.table.hide_rows_by_keys(hidden_keys)
        if visible_keys:
            self.table.show_rows_by_keys(visible_keys)

        # Update info
        self.info_label.setText(
            f"Total: {len(self.feature_data)} points\n"
            f"Visible: {len(visible_ids)}\n"
            f"Hidden: {len(hidden_ids)}"
        )

    def reset_filters(self):
        """Reset all filters to show all features."""
        # Reset sliders to full range
        self.value_slider.set_range(0.0, 100.0)
        if self.timestamp_slider:
            # Get full range from slider
            timestamps = sorted(set(f["timestamp"] for f in self.feature_data))
            if timestamps:
                self.timestamp_slider.set_range(timestamps[0], timestamps[-1])

        # Show all features on map
        self.fast_layer.show_all_features()

        # Show all rows in table
        self.table.show_all_rows()

        # Update info
        n = len(self.feature_data)
        self.info_label.setText(f"Total: {n} points\nVisible: {n}")

    def on_map_selection(self, selection):
        """Handle selection from map -> update table."""
        keys = [(selection.layer_id, fid) for fid in selection.feature_ids]
        self.table.select_keys(keys, clear_first=True)

    def on_table_selection(self, keys):
        """Handle selection from table -> update map."""
        # Group by layer
        by_layer = {}
        for layer_id, fid in keys:
            by_layer.setdefault(layer_id, []).append(fid)

        # Update each layer's selection
        for layer_id, fids in by_layer.items():
            if layer_id == self.fast_layer.id:
                self.map_widget.set_fast_points_selection(layer_id, fids)


def main():
    """Run the range slider filter example."""
    app = QtWidgets.QApplication(sys.argv)
    window = RangeFilterWindow()
    window.resize(1400, 900)
    window.show()

    print("="*70)
    print("Range Slider Filter Example")
    print("="*70)
    print("Features:")
    print("  • Dual-handle range sliders for filtering")
    print("  • Filter by numeric values and ISO8601 timestamps")
    print("  • Bidirectional sync between map and table")
    print("  • Features are hidden (not removed) and can be shown again")
    print("  • Points colored by value (green=low, red=high)")
    print("\nTry:")
    print("  • Adjust the 'Value' slider to filter by value")
    print("  • Adjust the 'Timestamp' slider to filter by time")
    print("  • Click 'Reset Filters' to show all points again")
    print("  • Select points on the map or in the table")
    print("="*70)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
