#!/usr/bin/env python3
"""Graphical Time Slider Filtering

This example demonstrates TimeHistogramSliderWidget as a drop-in replacement
for the ISO8601 RangeSliderWidget. The slider draws an aggregated activity
histogram so users can see when map features are active over time. Use the
mouse wheel over the plot to zoom; the histogram re-aggregates for the new
visible time window to reveal higher-fidelity activity patterns.

Pass --sparse to load 20,000 early points and only six later points, with
controls for checking that sparse histogram bins remain visible.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from pyopenlayersqt import FastPointsStyle, OLMapWidget
from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget
from pyopenlayersqt.time_histogram_slider import TimeHistogramSliderWidget


class TimeHistogramSliderExample(QtWidgets.QMainWindow):
    """Map example using a graphical histogram time slider."""

    def __init__(self, *, sparse=False):
        super().__init__()
        self._sparse = sparse
        title = "Graphical Time Slider Filtering"
        self.setWindowTitle(f"{title} — Sparse data" if sparse else title)
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
        """Set up table, map, and time controls under the map."""
        map_panel = QtWidgets.QWidget()
        map_layout = QtWidgets.QVBoxLayout(map_panel)
        map_layout.addWidget(self.map_widget, stretch=1)
        map_layout.addWidget(self.time_slider)

        if self._sparse:
            instructions = QtWidgets.QLabel(
                "Blue: 20,000 points on Jan 1, 00:00–06:00 UTC. "
                "Orange: 1 point on Jan 10, 2 on Jan 20, and 3 on Jan 29.\n"
                "Look for three short bars after the early peak. Drag the blue handles "
                "to filter the map and table; wheel over the histogram to zoom."
            )
            instructions.setWordWrap(True)
            map_layout.addWidget(instructions)
            self.sparse_btn = QtWidgets.QPushButton("Show sparse points only (6 points)")
            self.sparse_btn.setEnabled(False)
            self.sparse_btn.clicked.connect(self._show_sparse_points)
            map_layout.addWidget(self.sparse_btn)

        self.info_label = QtWidgets.QLabel("Loading time-based data...")
        self.info_label.setStyleSheet("background-color: #e8f4f8; padding: 8px;")
        self.info_label.setWordWrap(True)
        map_layout.addWidget(self.info_label)

        reset_btn = QtWidgets.QPushButton("Reset Time Filter")
        reset_btn.clicked.connect(self._reset_filter)
        map_layout.addWidget(reset_btn)

        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        splitter.addWidget(self.table)
        splitter.addWidget(map_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(splitter, stretch=1)
        self.setCentralWidget(container)

    def _time_samples(self, rng):
        """Return timestamp/activity pairs for the selected demonstration."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        if self._sparse:
            samples = [
                (start + timedelta(seconds=int(seconds)), "Early surge")
                for seconds in rng.integers(0, 6 * 3600, size=20000)
            ]
            for day, count in ((10, 1), (20, 2), (29, 3)):
                timestamp = start + timedelta(days=day - 1, hours=12)
                samples.extend([(timestamp, "Sparse activity")] * count)
            return samples

        clusters = [
            (start + timedelta(days=2), 0.35, "Early surge"),
            (start + timedelta(days=11), 0.25, "Mid-month"),
            (start + timedelta(days=20), 0.30, "Late surge"),
            (start + timedelta(days=28), 0.10, "Cleanup"),
        ]
        cluster_choices = rng.choice(
            len(clusters), size=6000, p=[c[1] for c in clusters]
        )
        samples = []
        for cluster_idx in cluster_choices:
            center, _, activity = clusters[int(cluster_idx)]
            offset_hours = float(rng.normal(0.0, 28.0))
            timestamp = center + timedelta(hours=offset_hours)
            timestamp = max(start, min(start + timedelta(days=30), timestamp))
            samples.append((timestamp, activity))
        return samples

    def _add_data(self):
        """Generate sample timestamps and add map/table features."""
        rng = np.random.default_rng(seed=7)
        samples = self._time_samples(rng)
        lats = 32.0 + rng.random(len(samples)) * 15.0
        lons = -125.0 + rng.random(len(samples)) * 15.0
        coords = list(zip(lats.tolist(), lons.tolist()))

        self.data = []
        colors = []
        for i, (timestamp, activity) in enumerate(samples):
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
            colors.append(
                QColor("#f97316") if activity == "Sparse activity" else QColor(30, 144, 255, 180)
            )

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
        if self._sparse:
            # Keep the last sparse bin clear of the right-hand filter handle.
            self.time_slider.set_available_range("2024-01-01T00:00:00Z", "2024-01-31T00:00:00Z")
            self.sparse_btn.setEnabled(True)
            self.map_widget.fit_to_data()
        else:
            self.time_slider.set_available_range(min(timestamps), max(timestamps))
        self.time_slider.set_distribution_values(timestamps)
        self._update_info_label(len(self.data), 0)

    def _show_sparse_points(self):
        """Exclude the early surge while keeping the full histogram extent."""
        self.time_slider.set_range("2024-01-02T00:00:00Z", "2024-01-31T00:00:00Z")

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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sparse", action="store_true", help="Show a large early peak and six later points."
    )
    args = parser.parse_args()
    app = QtWidgets.QApplication(sys.argv)
    window = TimeHistogramSliderExample(sparse=args.sparse)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
