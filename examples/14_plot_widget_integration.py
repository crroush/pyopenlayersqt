"""Plot widget integration example (map + plot + table workflow).

Run:
    python examples/14_plot_widget_integration.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from pyopenlayersqt import FastPointsStyle, FeatureTableWidget, OLMapWidget, PlotWidget, TraceStyle
from pyopenlayersqt.features_table import ColumnSpec


@dataclass
class SampleRow:
    layer_id: str
    feature_id: str
    timestamp: str
    value: float


def to_epoch(dt: datetime) -> float:
    return dt.replace(tzinfo=timezone.utc).timestamp()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Plot / Map / Table Sync Demo")
        self.resize(1450, 860)

        center = (37.78, -122.42)
        self.map_widget = OLMapWidget(center=center, zoom=10)
        self.fast_points = self.map_widget.add_fast_points_layer(
            "stations",
            selectable=True,
            style=FastPointsStyle(
                radius=3.5,
                selected_radius=6.5,
                default_color=QColor("deepskyblue"),
                selected_color=QColor("gold"),
            ),
        )

        self.plot = PlotWidget()
        self.plot.set_datetime_axis_format("yyyy-MM-dd\nHH:mm:ss")
        self.plot.set_datetime_axis_tick_count(8)
        self.plot.set_datetime_labels_angle(-30)
        self.plot.setMinimumHeight(340)

        self.table = FeatureTableWidget(
            columns=[
                ColumnSpec("Feature ID", lambda r: r.feature_id),
                ColumnSpec("Timestamp", lambda r: r.timestamp),
                ColumnSpec("Value", lambda r: r.value, fmt=lambda v: f"{float(v):.3f}"),
            ],
            key_fn=lambda r: (r.layer_id, r.feature_id),
        )
        self.table.table.setMinimumHeight(220)

        self.info = QLabel(
            "Select on plot, map, or table. All views stay synchronized."
        )

        self._suppress_map_to_plot = False
        self._build_data()

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        controls = self._build_controls()
        layout.addWidget(controls)
        layout.addWidget(self.info)

        left_split = QSplitter(Qt.Vertical)
        left_split.addWidget(self.plot)
        left_split.addWidget(self.table)
        left_split.setStretchFactor(0, 3)
        left_split.setStretchFactor(1, 2)

        main_split = QSplitter(Qt.Horizontal)
        main_split.addWidget(left_split)
        main_split.addWidget(self.map_widget)
        main_split.setStretchFactor(0, 3)
        main_split.setStretchFactor(1, 4)
        main_split.setSizes([700, 900])
        layout.addWidget(main_split)

        self.plot.highlightFeatureKeys.connect(self._on_plot_highlight)
        self.map_widget.selectionChanged.connect(self._on_map_selection)
        self.table.selectionKeysChanged.connect(self._on_table_selection)

    def _build_controls(self) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)

        row.addWidget(QLabel("Line style:"))
        self.line_style_combo = QComboBox()
        self.line_style_combo.addItems(["solid", "dash", "dot", "dashdot"])
        self.line_style_combo.currentTextChanged.connect(self._on_line_style_changed)
        row.addWidget(self.line_style_combo)

        row.addSpacing(14)
        row.addWidget(QLabel("Time labels:"))
        self.time_label_combo = QComboBox()
        self.time_label_combo.addItems([
            "yyyy-MM-dd\nHH:mm:ss",
            "MM-dd HH:mm:ss",
            "HH:mm:ss",
        ])
        self.time_label_combo.setCurrentText("yyyy-MM-dd\nHH:mm:ss")
        self.time_label_combo.currentTextChanged.connect(self.plot.set_datetime_axis_format)
        row.addWidget(self.time_label_combo)

        row.addSpacing(14)
        reset_btn = QPushButton("Reset Selection")
        reset_btn.clicked.connect(self._clear_selection)
        row.addWidget(reset_btn)

        row.addStretch(1)
        return w

    def _build_data(self) -> None:
        n = 500
        rng = np.random.default_rng(7)
        lat = 37.78 + rng.normal(scale=0.03, size=n)
        lon = -122.42 + rng.normal(scale=0.04, size=n)

        ids = [f"pt_{i}" for i in range(n)]
        self.fast_points.add_points(list(zip(lat, lon)), ids=ids)

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        ts_dt = [start + timedelta(minutes=i * 10) for i in range(n)]
        ts_epoch = np.array([to_epoch(dt) for dt in ts_dt], dtype=float)
        values = np.cumsum(rng.normal(size=n))

        self.plot.add_trace(
            "metric_a",
            x=ts_epoch,
            y=values,
            mode="both",
            style=TraceStyle(
                color=QColor("cornflowerblue"),
                selected_color=QColor("orangered"),
                marker_size=7,
                selected_marker_size=10,
                line_width=2.2,
                line_style="solid",
            ),
            timestamps=ts_epoch,
            feature_keys=[(self.fast_points.id, fid) for fid in ids],
        )

        rows = [
            SampleRow(
                layer_id=self.fast_points.id,
                feature_id=fid,
                timestamp=dt.strftime("%Y-%m-%d %H:%M:%S"),
                value=float(val),
            )
            for fid, dt, val in zip(ids, ts_dt, values)
        ]
        self.table.append_rows(rows)

    def _on_line_style_changed(self, style_name: str) -> None:
        self.plot.set_trace_style(
            "metric_a",
            TraceStyle(
                color=QColor("cornflowerblue"),
                selected_color=QColor("orangered"),
                marker_size=7,
                selected_marker_size=10,
                line_width=2.2,
                line_style=style_name,
            ),
        )

    def _on_plot_highlight(self, keys: list[tuple[str, str]]) -> None:
        selected_ids = [feature_id for layer_id, feature_id in keys if layer_id == self.fast_points.id]
        self._suppress_map_to_plot = True
        self.map_widget.set_fast_points_selection(self.fast_points.id, selected_ids)
        QTimer.singleShot(120, self._release_map_sync_suppression)
        self.table.select_keys([(self.fast_points.id, fid) for fid in selected_ids])
        self.info.setText(f"Selected points: {len(selected_ids)}")

    def _on_map_selection(self, selection) -> None:
        if self._suppress_map_to_plot:
            return
        layer_id = getattr(selection, "layer_id", "")
        feature_ids = list(getattr(selection, "feature_ids", []))
        if layer_id != self.fast_points.id:
            return
        keys = [(self.fast_points.id, fid) for fid in feature_ids]
        self.plot.set_selected_feature_keys(keys)
        self.table.select_keys(keys)
        self.info.setText(f"Selected points: {len(feature_ids)}")

    def _on_table_selection(self, keys: list[tuple[str, str]]) -> None:
        filtered = [k for k in keys if k[0] == self.fast_points.id]
        self.plot.set_selected_feature_keys(filtered)
        self._suppress_map_to_plot = True
        self.map_widget.set_fast_points_selection(self.fast_points.id, [fid for _, fid in filtered])
        QTimer.singleShot(120, self._release_map_sync_suppression)

    def _release_map_sync_suppression(self) -> None:
        self._suppress_map_to_plot = False

    def _clear_selection(self) -> None:
        self.map_widget.set_fast_points_selection(self.fast_points.id, [])
        self.plot.set_selected_points([])
        self.table.clear_selection()
        self.info.setText("Selection cleared")


def main() -> None:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
