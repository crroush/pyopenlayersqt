"""Plot widget integration example (table + map + plot style workflow).

Run:
    python examples/14_plot_widget_integration.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from pyopenlayersqt import FastPointsStyle, OLMapWidget, PlotWidget, TraceStyle


def to_epoch(dt: datetime) -> float:
    return dt.replace(tzinfo=timezone.utc).timestamp()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Plot / Map Sync Demo")
        self.resize(1300, 700)

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
        self.plot.set_datetime_labels_angle(-35)
        self.info = QLabel(
            "Box-select points in the plot OR select points on the map. Both stay synchronized."
        )

        self._build_data()

        self._build_toolbar()

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self.info)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Vertical)
        splitter.addWidget(self.map_widget)
        splitter.addWidget(self.plot)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        self.plot.highlightFeatureKeys.connect(self._on_plot_highlight)
        self.map_widget.selectionChanged.connect(self._on_map_selection)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Plot Controls")
        self.addToolBar(toolbar)

        toolbar.addWidget(QLabel("Line style:"))
        self.line_style_combo = QComboBox()
        self.line_style_combo.addItems(["solid", "dash", "dot", "dashdot"])
        self.line_style_combo.currentTextChanged.connect(self._on_line_style_changed)
        toolbar.addWidget(self.line_style_combo)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Time labels:"))
        self.time_label_combo = QComboBox()
        self.time_label_combo.addItems([
            "yyyy-MM-dd\nHH:mm:ss",
            "MM-dd HH:mm",
            "HH:mm:ss",
        ])
        self.time_label_combo.setCurrentText("yyyy-MM-dd\nHH:mm:ss")
        self.time_label_combo.currentTextChanged.connect(self.plot.set_datetime_axis_format)
        toolbar.addWidget(self.time_label_combo)

        toolbar.addSeparator()
        reset_btn = QPushButton("Reset Selection")
        reset_btn.clicked.connect(self._clear_selection)
        toolbar.addWidget(reset_btn)

    def _build_data(self) -> None:
        n = 500
        rng = np.random.default_rng(7)
        lat = 37.78 + rng.normal(scale=0.03, size=n)
        lon = -122.42 + rng.normal(scale=0.04, size=n)

        self.fast_points.add_points(
            list(zip(lat, lon)),
            ids=[f"pt_{i}" for i in range(n)],
        )

        start = datetime(2024, 1, 1)
        ts = np.array([to_epoch(start + timedelta(minutes=i * 10)) for i in range(n)], dtype=float)

        self.plot.add_trace(
            "metric_a",
            x=ts,
            y=np.cumsum(rng.normal(size=n)),
            mode="both",
            style=TraceStyle(
                color=QColor("cornflowerblue"),
                selected_color=QColor("orangered"),
                marker_size=7,
                selected_marker_size=10,
            ),
            timestamps=ts,
            feature_keys=[(self.fast_points.id, f"pt_{i}") for i in range(n)],
        )

        self.plot.add_trace(
            "metric_b",
            x=ts,
            y=np.cumsum(rng.normal(size=n) * 0.7) + 25.0,
            mode="line",
            style=TraceStyle(
                color=QColor("mediumpurple"),
                line_width=2.5,
                line_style="dash",
            ),
            timestamps=ts,
        )

    def _on_line_style_changed(self, style_name: str) -> None:
        self.plot.set_trace_style(
            "metric_b",
            TraceStyle(
                color=QColor("mediumpurple"),
                line_width=2.5,
                line_style=style_name,
            ),
        )

    def _on_plot_highlight(self, keys: list[tuple[str, str]]) -> None:
        selected_ids = [feature_id for layer_id, feature_id in keys if layer_id == self.fast_points.id]
        self.map_widget.set_fast_points_selection(self.fast_points.id, selected_ids)
        self.info.setText(f"Selected points: {len(keys)}")

    def _on_map_selection(self, selection) -> None:
        layer_id = getattr(selection, "layer_id", "")
        feature_ids = list(getattr(selection, "feature_ids", []))
        if layer_id != self.fast_points.id:
            return
        keys = [(self.fast_points.id, fid) for fid in feature_ids]
        self.plot.set_selected_feature_keys(keys)
        self.info.setText(f"Selected points: {len(feature_ids)}")

    def _clear_selection(self) -> None:
        self.map_widget.set_fast_points_selection(self.fast_points.id, [])
        self.plot.set_selected_points([])
        self.info.setText("Selection cleared")


def main() -> None:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
