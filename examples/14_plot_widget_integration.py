"""Plot widget integration example (table + map + plot style workflow).

Run:
    python examples/14_plot_widget_integration.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import numpy as np
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QVBoxLayout, QWidget

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
        self.info = QLabel(
            "Box-select points in the plot. Selected points are highlighted in the fast-points layer."
        )

        self._build_data()

        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)

        left = QVBoxLayout()
        left.addWidget(self.info)
        left.addWidget(self.plot)
        layout.addLayout(left, stretch=2)
        layout.addWidget(self.map_widget, stretch=3)

        self.plot.highlightFeatureKeys.connect(self._on_plot_highlight)

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

    def _on_plot_highlight(self, keys: list[tuple[str, str]]) -> None:
        selected_ids = [feature_id for layer_id, feature_id in keys if layer_id == self.fast_points.id]
        self.map_widget.set_fast_points_selection(self.fast_points.id, selected_ids)
        self.info.setText(f"Selected points: {len(keys)}")


def main() -> None:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
