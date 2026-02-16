#!/usr/bin/env python3
"""Map + table + pyqtgraph tri-directional selection for 100k time-series points.

This example extends the map/table ideas from example 08 by adding a pyqtgraph
chart. Selection is synchronized in all directions:

- map -> table -> plot
- table -> map -> plot
- plot -> table -> map

Dataset:
- 100,000 points
- timestamped over a 4-hour window
- timestamp shown on x-axis using pyqtgraph.DateAxisItem
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import numpy as np
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

try:
    import pyqtgraph as pg
except ImportError as exc:  # pragma: no cover - runtime guidance
    raise SystemExit(
        "This example requires pyqtgraph. Install with: pip install pyqtgraph"
    ) from exc

from pyopenlayersqt import FastPointsStyle, OLMapWidget
from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget


class TimeSeriesMapTablePlotExample(QtWidgets.QMainWindow):
    """Demonstrate tri-directional selection across map/table/plot."""

    POINT_COUNT = 100_000

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Time-Series Selection Sync: Map ↔ Table ↔ Plot (100k)")
        self.resize(1820, 980)

        self._selection_guard = False
        self._updating_region = False

        self.map_widget = OLMapWidget(center=(39.8, -98.6), zoom=4)
        self.layer = self.map_widget.add_fast_points_layer(
            "timeseries_points",
            selectable=True,
            style=FastPointsStyle(
                radius=3.0,
                default_color=QColor("dodgerblue"),
                selected_radius=6.0,
                selected_color=QColor("yellow"),
            ),
        )

        self.table = self._create_table()
        self.plot_widget = self._create_plot()

        self.status_label = QtWidgets.QLabel("Loading 100,000 points...")
        self.status_label.setStyleSheet(
            "background-color: #e8f4f8; padding: 8px; border-radius: 4px;"
        )

        self._build_layout()

        self.feature_ids: list[str] = []
        self.id_to_idx: dict[str, int] = {}
        self.timestamps_s: np.ndarray = np.array([], dtype=float)
        self.values: np.ndarray = np.array([], dtype=float)

        self.map_widget.ready.connect(self._load_data)
        self.map_widget.selectionChanged.connect(self._on_map_selection)
        self.table.selectionKeysChanged.connect(self._on_table_selection)

    def _create_table(self) -> FeatureTableWidget:
        columns = [
            ColumnSpec("Feature ID", lambda r: r.get("feature_id", "")),
            ColumnSpec("Timestamp (UTC)", lambda r: r.get("timestamp_iso", "")),
            ColumnSpec("Value", lambda r: r.get("value", 0.0), fmt=lambda v: f"{float(v):.3f}"),
        ]
        return FeatureTableWidget(
            columns=columns,
            key_fn=lambda r: (str(r.get("layer_id")), str(r.get("feature_id"))),
            sorting_enabled=True,
        )

    def _create_plot(self) -> pg.PlotWidget:
        axis = pg.DateAxisItem(orientation="bottom", utcOffset=0)
        plot = pg.PlotWidget(axisItems={"bottom": axis})
        plot.setBackground("w")
        plot.showGrid(x=True, y=True, alpha=0.25)
        plot.setLabel("bottom", "Time (UTC)")
        plot.setLabel("left", "Value")
        plot.setTitle("100k Point Time Series (line) + Selected Points (orange)")

        self.series_curve = plot.plot(
            pen=pg.mkPen(color=(70, 130, 180), width=1),
            antialias=False,
        )
        self.selected_scatter = pg.ScatterPlotItem(
            size=7,
            pen=pg.mkPen(color=(180, 70, 20), width=1),
            brush=pg.mkBrush(255, 140, 0, 220),
        )
        plot.addItem(self.selected_scatter)

        self.selection_region = pg.LinearRegionItem(movable=True)
        self.selection_region.setZValue(10)
        self.selection_region.sigRegionChangeFinished.connect(self._on_plot_region_changed)
        plot.addItem(self.selection_region)

        plot.scene().sigMouseClicked.connect(self._on_plot_clicked)
        return plot

    def _build_layout(self) -> None:
        info = QtWidgets.QLabel(
            "<b>Selection workflow:</b> Click map markers, select rows in the table, "
            "or click the chart near a point. Move the chart's vertical region to select "
            "a time range. All three views stay synchronized."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "background-color: #fff6d5; padding: 8px; border-radius: 4px;"
        )

        left_split = QtWidgets.QSplitter(Qt.Vertical)
        left_split.addWidget(self.table)
        left_split.addWidget(self.plot_widget)
        left_split.setStretchFactor(0, 3)
        left_split.setStretchFactor(1, 2)

        main_split = QtWidgets.QSplitter(Qt.Horizontal)
        main_split.addWidget(left_split)
        main_split.addWidget(self.map_widget)
        main_split.setStretchFactor(0, 3)
        main_split.setStretchFactor(1, 4)

        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(info)
        layout.addWidget(self.status_label)
        layout.addWidget(main_split, stretch=1)
        self.setCentralWidget(container)

    def _load_data(self) -> None:
        rng = np.random.default_rng(42)

        start_dt = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=4)
        base_s = start_dt.timestamp()
        duration_s = 4 * 60 * 60

        self.timestamps_s = np.linspace(base_s, base_s + duration_s, self.POINT_COUNT)

        minutes = (self.timestamps_s - base_s) / 60.0
        self.values = 25.0 + 0.03 * minutes + 2.4 * np.sin(minutes / 5.0)
        self.values += rng.normal(0.0, 0.35, self.POINT_COUNT)

        lats = 39.8 + rng.normal(0.0, 1.3, self.POINT_COUNT)
        lons = -98.6 + rng.normal(0.0, 1.8, self.POINT_COUNT)
        coords = list(zip(lats.tolist(), lons.tolist()))

        self.feature_ids = [f"ts_{i:06d}" for i in range(self.POINT_COUNT)]
        self.id_to_idx = {fid: i for i, fid in enumerate(self.feature_ids)}

        self.layer.add_points(coords, ids=self.feature_ids)

        rows = (
            {
                "layer_id": self.layer.id,
                "feature_id": self.feature_ids[i],
                "timestamp_iso": datetime.fromtimestamp(
                    float(self.timestamps_s[i]), timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "value": float(self.values[i]),
            }
            for i in range(self.POINT_COUNT)
        )
        self.table.append_rows(rows)

        self.series_curve.setData(self.timestamps_s, self.values)

        initial_start = base_s + duration_s * 0.45
        initial_end = base_s + duration_s * 0.50
        self.selection_region.setRegion((initial_start, initial_end))
        self._on_plot_region_changed()

    def _on_map_selection(self, selection) -> None:
        if selection.layer_id != self.layer.id:
            return
        self._sync_selection(selection.feature_ids, source="map")

    def _on_table_selection(self, keys: list[tuple[str, str]]) -> None:
        ids = [feature_id for layer_id, feature_id in keys if layer_id == self.layer.id]
        self._sync_selection(ids, source="table")

    def _on_plot_clicked(self, mouse_event) -> None:
        if mouse_event.button() != Qt.LeftButton:
            return

        scene_pos = mouse_event.scenePos()
        view_box = self.plot_widget.plotItem.vb
        if not self.plot_widget.sceneBoundingRect().contains(scene_pos):
            return

        data_pt = view_box.mapSceneToView(scene_pos)
        x_val = float(data_pt.x())
        if self.timestamps_s.size == 0:
            return

        idx = int(np.searchsorted(self.timestamps_s, x_val))
        if idx <= 0:
            nearest = 0
        elif idx >= self.timestamps_s.size:
            nearest = self.timestamps_s.size - 1
        else:
            prev_diff = abs(self.timestamps_s[idx - 1] - x_val)
            next_diff = abs(self.timestamps_s[idx] - x_val)
            nearest = idx - 1 if prev_diff <= next_diff else idx

        self._sync_selection([self.feature_ids[nearest]], source="plot")

    def _on_plot_region_changed(self) -> None:
        if self._updating_region or self.timestamps_s.size == 0:
            return

        x0, x1 = self.selection_region.getRegion()
        lo = min(x0, x1)
        hi = max(x0, x1)

        start = int(np.searchsorted(self.timestamps_s, lo, side="left"))
        end = int(np.searchsorted(self.timestamps_s, hi, side="right"))
        ids = self.feature_ids[start:end]
        self._sync_selection(ids, source="plot")

    def _sync_selection(self, ids: list[str], *, source: str) -> None:
        if self._selection_guard:
            return

        unique_ids = list(dict.fromkeys(str(fid) for fid in ids))
        keys = [(self.layer.id, fid) for fid in unique_ids]

        self._selection_guard = True
        try:
            if source != "table":
                self.table.select_keys(keys, clear_first=True)

            if source != "map":
                self.map_widget.set_fast_points_selection(self.layer.id, unique_ids)

            self._update_plot_selection(unique_ids)
            self._update_status(unique_ids)
        finally:
            self._selection_guard = False

    def _update_plot_selection(self, ids: list[str]) -> None:
        if not ids:
            self.selected_scatter.setData([], [])
            return

        idxs = [self.id_to_idx[fid] for fid in ids if fid in self.id_to_idx]
        if not idxs:
            self.selected_scatter.setData([], [])
            return

        x = self.timestamps_s[idxs]
        y = self.values[idxs]
        self.selected_scatter.setData(x=x, y=y)

    def _update_status(self, ids: list[str]) -> None:
        count = len(ids)
        if count == 0:
            self.status_label.setText("Selected: 0 points")
            return

        idxs = [self.id_to_idx[fid] for fid in ids if fid in self.id_to_idx]
        if not idxs:
            self.status_label.setText("Selected: 0 points")
            return

        lo = float(np.min(self.timestamps_s[idxs]))
        hi = float(np.max(self.timestamps_s[idxs]))
        lo_txt = datetime.fromtimestamp(lo, timezone.utc).strftime("%H:%M:%S")
        hi_txt = datetime.fromtimestamp(hi, timezone.utc).strftime("%H:%M:%S")
        self.status_label.setText(
            f"Selected: {count:,} points | UTC window: {lo_txt} → {hi_txt}"
        )

        if count > 1:
            self._updating_region = True
            try:
                self.selection_region.setRegion((lo, hi))
            finally:
                self._updating_region = False


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = TimeSeriesMapTablePlotExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
