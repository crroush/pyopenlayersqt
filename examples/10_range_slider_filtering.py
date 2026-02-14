#!/usr/bin/env python3
"""Range Slider for Feature Filtering

This example demonstrates RangeSliderWidget for interactive filtering:
- Dual-handle sliders for filtering numeric ranges
- Timestamp filtering with ISO8601 dates
- hide_features() and show_features() for FastPointsLayer
- Synchronized filtering between map and table
- QColor-based point coloring
- Live updates as slider moves

Useful for exploring large datasets by filtering on continuous variables.
"""

import sys
from datetime import datetime, timedelta, timezone

import numpy as np
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, FastPointsStyle
from pyopenlayersqt.features_table import FeatureTableWidget, ColumnSpec
from pyopenlayersqt.range_slider import RangeSliderWidget


class RangeSliderExample(QtWidgets.QMainWindow):
    """Range slider filtering example window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Range Slider Feature Filtering")
        self.resize(1400, 900)

        # Create map
        self.map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)

        # Create fast points layer
        self.fast_layer = self.map_widget.add_fast_points_layer(
            "filterable_points",
            selectable=True,
            style=FastPointsStyle(
                radius=4.0,
                default_color=QColor("green"),
                selected_radius=7.0,
                selected_color=QColor("yellow")
            )
        )

        # Create feature table
        self.table = self._create_table()

        # Create sliders
        self.value_slider, self.time_slider = self._create_sliders()

        # Generate data after map is ready
        self.map_widget.ready.connect(self._add_data)

        # Layout
        self._setup_layout()

    def _create_table(self):
        """Create feature table."""
        columns = [
            ColumnSpec("ID", lambda r: r.get("feature_id", "")),
            ColumnSpec("Value", lambda r: f"{r.get('value', 0):.1f}"),
            ColumnSpec("Timestamp", lambda r: r.get("timestamp", "")),
        ]

        return FeatureTableWidget(
            columns=columns,
            key_fn=lambda r: (str(r.get("layer_id")), str(r.get("feature_id"))),
            sorting_enabled=True
        )

    def _create_sliders(self):
        """Create range slider widgets."""
        # Value slider (0-100)
        value_slider = RangeSliderWidget(
            min_val=0.0,
            max_val=100.0,
            step=1.0,
            label="Filter by Value",
            show_value_tooltips=True
        )
        value_slider.rangeChanged.connect(self._on_value_range_changed)

        # Time slider (30-day range with hourly ISO8601 values)
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        total_hours = 30 * 24
        timestamp_values = [
            (start_date + timedelta(hours=hour)).isoformat().replace("+00:00", "Z")
            for hour in range(total_hours + 1)
        ]
        time_slider = RangeSliderWidget(
            values=timestamp_values,
            label="Filter by Timestamp",
            show_value_tooltips=True
        )
        time_slider.rangeChanged.connect(self._on_time_range_changed)

        return value_slider, time_slider

    def _setup_layout(self):
        """Setup window layout."""
        # Sliders panel
        sliders_panel = QtWidgets.QWidget()
        sliders_layout = QtWidgets.QVBoxLayout(sliders_panel)
        sliders_layout.addWidget(self.value_slider)
        sliders_layout.addWidget(self.time_slider)

        # Info label
        self.info_label = QtWidgets.QLabel("Loading data...")
        self.info_label.setStyleSheet("background-color: #e8f4f8; padding: 8px;")
        sliders_layout.addWidget(self.info_label)

        # Reset button
        reset_btn = QtWidgets.QPushButton("Reset All Filters")
        reset_btn.clicked.connect(self._reset_filters)
        sliders_layout.addWidget(reset_btn)

        sliders_layout.addStretch(1)

        # Splitter for table and map
        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        splitter.addWidget(self.table)
        splitter.addWidget(self.map_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        # Main layout
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(sliders_panel)
        layout.addWidget(splitter, stretch=1)
        self.setCentralWidget(container)

    def _add_data(self):
        """Generate and add sample data."""
        rng = np.random.default_rng(seed=42)
        n_points = 5000

        # Generate points
        lats = 32.0 + rng.random(n_points) * 15.0
        lons = -125.0 + rng.random(n_points) * 15.0
        coords = list(zip(lats.tolist(), lons.tolist()))

        # Generate values and timestamps
        values = (rng.random(n_points) * 100).tolist()
        start_ts = datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()
        end_ts = (datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=30)).timestamp()
        timestamp_seconds = (start_ts + rng.random(n_points) * (end_ts - start_ts)).tolist()

        # Generate IDs and store data
        self.data = []
        for i in range(n_points):
            feature_id = f"point_{i}"
            self.data.append({
                "id": feature_id,
                "coord": coords[i],
                "value": values[i],
                "timestamp": (
                    datetime.fromtimestamp(timestamp_seconds[i], tz=timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z")
                ),
            })

        ids = [d["id"] for d in self.data]

        # Color points by value (green=low, yellow=medium, red=high)
        colors = []
        for val in values:
            ratio = val / 100.0
            if ratio < 0.5:
                # Green to yellow
                r = int(255 * (ratio * 2))
                g = 255
            else:
                # Yellow to red
                r = 255
                g = int(255 * (1 - (ratio - 0.5) * 2))
            colors.append(QColor(r, g, 0, 200))

        self.fast_layer.add_points(coords, ids=ids, colors_rgba=colors)

        # Add to table
        rows = [
            {
                "layer_id": self.fast_layer.id,
                "feature_id": d["id"],
                "value": d["value"],
                "timestamp": d["timestamp"],
            }
            for d in self.data
        ]
        self.table.append_rows(rows)

        self._update_info_label()

    def _on_value_range_changed(self, _min_val, _max_val):
        """Handle value range changes."""
        self._apply_filters()

    def _on_time_range_changed(self, _min_val, _max_val):
        """Handle time range changes."""
        self._apply_filters()

    def _apply_filters(self):
        """Apply both filters."""
        if not hasattr(self, 'data'):
            return

        # Get current ranges
        val_min, val_max = self.value_slider.get_range()
        time_min, time_max = self.time_slider.get_range()

        # Filter data
        visible_ids = []
        hidden_ids = []

        for item in self.data:
            if (val_min <= item["value"] <= val_max and
                time_min <= item["timestamp"] <= time_max):
                visible_ids.append(item["id"])
            else:
                hidden_ids.append(item["id"])

        # Update map
        if hidden_ids:
            self.fast_layer.hide_features(hidden_ids)
        if visible_ids:
            self.fast_layer.show_features(visible_ids)

        # Update table
        hidden_keys = [(self.fast_layer.id, fid) for fid in hidden_ids]
        visible_keys = [(self.fast_layer.id, fid) for fid in visible_ids]

        if hidden_keys:
            self.table.hide_rows_by_keys(hidden_keys)
        if visible_keys:
            self.table.show_rows_by_keys(visible_keys)

        self._update_info_label(len(visible_ids), len(hidden_ids))

    def _reset_filters(self):
        """Reset all filters to show all data."""
        self.value_slider.reset_range()
        self.time_slider.reset_range()
        self._apply_filters()

    def _update_info_label(self, visible=None, hidden=None):
        """Update info label."""
        if visible is None:
            total = len(self.data) if hasattr(self, 'data') else 0
            self.info_label.setText(
                f"Total: {total:,} points | "
                "Use sliders to filter by value and timestamp"
            )
        else:
            total = visible + hidden
            self.info_label.setText(
                f"Showing {visible:,} / {total:,} points | "
                f"Hidden: {hidden:,}"
            )


def main():
    """Run the range slider filtering example."""
    app = QtWidgets.QApplication(sys.argv)
    window = RangeSliderExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
