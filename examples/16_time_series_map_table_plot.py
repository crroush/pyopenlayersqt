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
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from pyopenlayersqt import FastPointsStyle, OLMapWidget
from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget


class SelectableViewBox(pg.ViewBox):
    """ViewBox supporting map-like modifier drags.

    - Ctrl + left-drag: box select
    - Shift + left-drag: zoom box
    - plain drag: pan
    """

    sigSelectionBoxFinished = QtCore.Signal(float, float, float, float)

    def __init__(self) -> None:
        super().__init__()
        self._active_drag_mode = "pan"
        self.setMouseMode(self.PanMode)

    def mouseDragEvent(self, ev, axis=None):
        if ev.button() != Qt.LeftButton:
            super().mouseDragEvent(ev, axis=axis)
            return

        if ev.isStart():
            mods = ev.modifiers()
            if mods & Qt.ControlModifier:
                self._active_drag_mode = "select"
            elif mods & Qt.ShiftModifier:
                self._active_drag_mode = "zoom"
            else:
                self._active_drag_mode = "pan"

        if self._active_drag_mode == "zoom":
            self.setMouseMode(self.RectMode)
            super().mouseDragEvent(ev, axis=axis)
            if ev.isFinish():
                self.setMouseMode(self.PanMode)
                self._active_drag_mode = "pan"
            return

        if self._active_drag_mode != "select":
            self.setMouseMode(self.PanMode)
            super().mouseDragEvent(ev, axis=axis)
            if ev.isFinish():
                self._active_drag_mode = "pan"
            return

        ev.accept()
        if ev.isStart():
            self.updateScaleBox(ev.buttonDownPos(), ev.pos())
            return

        if ev.isFinish():
            self.rbScaleBox.hide()
            start = self.mapToView(ev.buttonDownPos())
            end = self.mapToView(ev.pos())
            x_min, x_max = sorted((float(start.x()), float(end.x())))
            y_min, y_max = sorted((float(start.y()), float(end.y())))
            self.sigSelectionBoxFinished.emit(x_min, x_max, y_min, y_max)
            self._active_drag_mode = "pan"
            return

        self.updateScaleBox(ev.buttonDownPos(), ev.pos())


class TimeSeriesMapTablePlotExample(QtWidgets.QMainWindow):
    """Demonstrate tri-directional selection across map/table/plot."""

    POINT_COUNT = 100_000

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Time-Series Selection Sync: Map ↔ Table ↔ Plot (100k)")
        self.resize(1820, 980)

        self._selection_guard = False

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
        self.plot_toolbar = self._create_plot_toolbar()

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
            ColumnSpec(
                "Value",
                lambda r: r.get("value", 0.0),
                fmt=lambda v: f"{float(v):.3f}",
            ),
        ]
        return FeatureTableWidget(
            columns=columns,
            key_fn=lambda r: (str(r.get("layer_id")), str(r.get("feature_id"))),
            sorting_enabled=False,
        )

    def _create_plot(self) -> pg.PlotWidget:
        axis = pg.DateAxisItem(orientation="bottom", utcOffset=0)
        self.plot_view = SelectableViewBox()
        self.plot_view.sigSelectionBoxFinished.connect(self._on_plot_box_selection)

        plot = pg.PlotWidget(axisItems={"bottom": axis}, viewBox=self.plot_view)
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

        plot.scene().sigMouseClicked.connect(self._on_plot_clicked)
        return plot

    def _create_plot_toolbar(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        reset_zoom_btn = QtWidgets.QPushButton("Reset Chart Zoom")
        reset_zoom_btn.clicked.connect(self._reset_chart_zoom)

        clear_selection_btn = QtWidgets.QPushButton("Clear Selection")
        clear_selection_btn.clicked.connect(lambda: self._sync_selection([], source="plot"))

        hint = QtWidgets.QLabel(
            "Tip: Ctrl+drag = box select, Shift+drag = zoom box, drag = pan."
        )
        hint.setStyleSheet("color: #555;")

        layout.addWidget(reset_zoom_btn)
        layout.addWidget(clear_selection_btn)
        layout.addStretch(1)
        layout.addWidget(hint)
        return widget

    def _build_layout(self) -> None:
        info = QtWidgets.QLabel(
            "<b>Selection workflow:</b> Click map markers, select rows in the table, "
            "or use chart interactions (click nearest point, Ctrl+drag box select, "
            "Shift+drag zoom box). "
            "All three views stay synchronized."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "background-color: #fff6d5; padding: 8px; border-radius: 4px;"
        )

        plot_panel = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.addWidget(self.plot_toolbar)
        plot_layout.addWidget(self.plot_widget, stretch=1)

        left_split = QtWidgets.QSplitter(Qt.Vertical)
        left_split.addWidget(self.table)
        left_split.addWidget(plot_panel)
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
        self._reset_chart_zoom()
        self.status_label.setText("Ready: 100,000 points loaded")

    def _reset_chart_zoom(self) -> None:
        if self.timestamps_s.size == 0:
            return
        self.plot_widget.plotItem.enableAutoRange(axis="xy")
        self.plot_widget.plotItem.autoRange()

    def _on_plot_box_selection(
        self,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> None:
        if self.timestamps_s.size == 0:
            return

        mask = (
            (self.timestamps_s >= x_min)
            & (self.timestamps_s <= x_max)
            & (self.values >= y_min)
            & (self.values <= y_max)
        )
        indices = np.flatnonzero(mask)
        self._sync_selection_by_indices(indices, source="plot")

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
        if (
            mouse_event.modifiers() & Qt.ControlModifier
            or mouse_event.modifiers() & Qt.ShiftModifier
        ):
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

    def _sync_selection_by_indices(self, indices: np.ndarray, *, source: str) -> None:
        total = int(indices.size)
        if total <= 0:
            self._sync_selection([], source=source)
            return

        if total >= len(self.feature_ids):
            self._sync_select_all(source=source)
            return

        ids = [self.feature_ids[int(i)] for i in indices]
        self._sync_selection(ids, source=source)

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

    def _sync_select_all(self, *, source: str) -> None:
        if self._selection_guard:
            return

        all_ids = list(self.feature_ids)
        keys = [(self.layer.id, fid) for fid in all_ids]

        self._selection_guard = True
        try:
            if source != "table":
                self.table.select_keys(keys, clear_first=True)

            if source != "map":
                self.map_widget.set_fast_points_selection(self.layer.id, all_ids)

            self._update_plot_selection(all_ids)
            self._update_status(all_ids)
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

    def _update_status(self, selected_ids: list[str]) -> None:
        total_selected = len(selected_ids)
        if total_selected == 0:
            self.status_label.setText("Selected: 0 points")
            return

        idxs = [self.id_to_idx[fid] for fid in selected_ids if fid in self.id_to_idx]
        if not idxs:
            self.status_label.setText("Selected: 0 points")
            return

        lo = float(np.min(self.timestamps_s[idxs]))
        hi = float(np.max(self.timestamps_s[idxs]))
        lo_txt = datetime.fromtimestamp(lo, timezone.utc).strftime("%H:%M:%S")
        hi_txt = datetime.fromtimestamp(hi, timezone.utc).strftime("%H:%M:%S")
        self.status_label.setText(
            f"Selected: {total_selected:,} points | UTC window: {lo_txt} → {hi_txt}"
        )


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = TimeSeriesMapTablePlotExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
