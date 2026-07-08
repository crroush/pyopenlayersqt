#!/usr/bin/env python3
"""Graphical Time Slider Filtering

This example demonstrates TimeHistogramSliderWidget as a drop-in replacement
for the ISO8601 RangeSliderWidget. The slider draws an aggregated activity
histogram so users can see when map features are active over time. Use the
mouse wheel over the plot to zoom; the histogram re-aggregates for the new
visible time window to reveal higher-fidelity activity patterns.
"""

import sys
from datetime import datetime, timedelta, timezone

import numpy as np
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from pyopenlayersqt import FastPointsStyle, OLMapWidget
from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget
from pyopenlayersqt.range_slider import TimeHistogramSliderWidget


class TimeHistogramSliderExample(QtWidgets.QMainWindow):
    """Map example using a graphical histogram time slider."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Graphical Time Slider Filtering")
        self.resize(1400, 900)

        self.map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)
        self.fast_layer = self.map_widget.add_fast_points_layer(
            "time_filtered_points",
            selectable=True,
            style=FastPointsStyle(
                radius=4.0,
                default_color=QColor("deepskyblue"),
                selected_radius=7.0,
                selected_color=QColor("yellow"),
            ),
        )
        self.table = self._create_table()
        self.time_slider = TimeHistogramSliderWidget(
            label="Feature activity over time",
            show_value_tooltips=True,
        )
        self.time_slider.rangeChanged.connect(self._apply_time_filter)
        self.map_widget.ready.connect(self._add_data)
        self._setup_layout()

    def _create_table(self):
        """Create feature table for active-time metadata."""
        columns = [
            ColumnSpec("ID", lambda r: r.get("feature_id", "")),
            ColumnSpec("Activity", lambda r: r.get("activity", "")),
            ColumnSpec("Timestamp", lambda r: r.get("timestamp", "")),
        ]
        return FeatureTableWidget(
            columns=columns,
            key_fn=lambda r: (str(r.get("layer_id")), str(r.get("feature_id"))),
            sorting_enabled=True,
        )

    def _setup_layout(self):
        """Set up controls, map, and table."""
        controls = QtWidgets.QWidget()
        controls_layout = QtWidgets.QVBoxLayout(controls)
        controls_layout.addWidget(self.time_slider)

        self.info_label = QtWidgets.QLabel("Loading time-based data...")
        self.info_label.setStyleSheet("background-color: #e8f4f8; padding: 8px;")
        controls_layout.addWidget(self.info_label)

        reset_btn = QtWidgets.QPushButton("Reset Time Filter")
        reset_btn.clicked.connect(self._reset_filter)
        controls_layout.addWidget(reset_btn)

        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        splitter.addWidget(self.table)
        splitter.addWidget(self.map_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(controls)
        layout.addWidget(splitter, stretch=1)
        self.setCentralWidget(container)

    def _add_data(self):
        """Generate clustered sample timestamps and add map/table features."""
        rng = np.random.default_rng(seed=7)
        n_points = 6000
        lats = 32.0 + rng.random(n_points) * 15.0
        lons = -125.0 + rng.random(n_points) * 15.0
        coords = list(zip(lats.tolist(), lons.tolist()))

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        clusters = [
            (start + timedelta(days=2), 0.35, "Early surge"),
            (start + timedelta(days=11), 0.25, "Mid-month"),
            (start + timedelta(days=20), 0.30, "Late surge"),
            (start + timedelta(days=28), 0.10, "Cleanup"),
        ]
        cluster_choices = rng.choice(
            len(clusters), size=n_points, p=[c[1] for c in clusters]
        )

        self.data = []
        colors = []
        for i, cluster_idx in enumerate(cluster_choices):
            center, _, activity = clusters[int(cluster_idx)]
            offset_hours = float(rng.normal(0.0, 28.0))
            timestamp = center + timedelta(hours=offset_hours)
            timestamp = max(start, min(start + timedelta(days=30), timestamp))
            iso_timestamp = timestamp.isoformat().replace("+00:00", "Z")
            feature_id = f"time_point_{i}"
            self.data.append(
                {
                    "id": feature_id,
                    "coord": coords[i],
                    "timestamp": iso_timestamp,
                    "activity": activity,
                }
            )
            colors.append(QColor(30, 144, 255, 180))

        self.fast_layer.add_points(
            coords, ids=[d["id"] for d in self.data], colors_rgba=colors
        )
        self.table.append_rows(
            [
                {
                    "layer_id": self.fast_layer.id,
                    "feature_id": d["id"],
                    "timestamp": d["timestamp"],
                    "activity": d["activity"],
                }
                for d in self.data
            ]
        )

        timestamps = [d["timestamp"] for d in self.data]
        self.time_slider.set_available_range(min(timestamps), max(timestamps))
        self.time_slider.set_distribution_values(timestamps)
        self._update_info_label(len(self.data), 0)

    def _apply_time_filter(self, _min_timestamp=None, _max_timestamp=None):
        """Hide map/table rows outside the selected time range."""
        if not hasattr(self, "data"):
            return
        time_min, time_max = self.time_slider.get_range()
        visible_ids = []
        hidden_ids = []
        for item in self.data:
            if time_min <= item["timestamp"] <= time_max:
                visible_ids.append(item["id"])
            else:
                hidden_ids.append(item["id"])

        if hidden_ids:
            self.fast_layer.hide_features(hidden_ids)
        if visible_ids:
            self.fast_layer.show_features(visible_ids)

        hidden_keys = [(self.fast_layer.id, fid) for fid in hidden_ids]
        visible_keys = [(self.fast_layer.id, fid) for fid in visible_ids]
        if hidden_keys:
            self.table.hide_rows_by_keys(hidden_keys)
        if visible_keys:
            self.table.show_rows_by_keys(visible_keys)
        self._update_info_label(len(visible_ids), len(hidden_ids))

    def _reset_filter(self):
        """Reset selection and plot zoom to the full time extent."""
        self.time_slider.reset_range()
        self.time_slider.reset_view()
        self._apply_time_filter()

    def _update_info_label(self, visible, hidden):
        """Update the status text."""
        total = visible + hidden
        self.info_label.setText(
            f"Showing {visible:,} / {total:,} points | Hidden: {hidden:,} | "
            "Wheel over the plot to zoom and re-aggregate the activity histogram."
        )


def main():
    """Run the graphical time slider example."""
    app = QtWidgets.QApplication(sys.argv)
    window = TimeHistogramSliderExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
