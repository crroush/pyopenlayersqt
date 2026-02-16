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
from PySide6.QtGui import QColor, QPen

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
    LINE_STYLES = {
        "No line": None,
        "Solid": Qt.SolidLine,
        "Dash": Qt.DashLine,
        "Dot": Qt.DotLine,
        "DashDot": Qt.DashDotLine,
    }
    POINT_STYLES = {
        "Circle": "o",
        "Square": "s",
        "Triangle": "t",
        "Diamond": "d",
        "Cross": "+",
    }

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Time-Series Selection Sync: Map ↔ Table ↔ Plot (100k)")
        self.resize(1820, 980)

        self._selection_guard = False
        self._ignore_next_map_selection = False
        self._current_selection_indices = np.array([], dtype=np.int64)

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
        self.feature_ids_np: np.ndarray = np.array([], dtype=object)
        self.id_to_idx: dict[str, int] = {}
        self.timestamps_s: np.ndarray = np.array([], dtype=float)
        self.values: np.ndarray = np.array([], dtype=float)
        self._x_bounds: tuple[float, float] = (0.0, 1.0)
        self._y_bounds: tuple[float, float] = (0.0, 1.0)

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
        plot.setTitle("100k Point Time Series (line or symbols) + selection by color")

        self.series_curve = plot.plot(
            pen=pg.mkPen(color=(70, 130, 180), width=1),
            antialias=False,
        )
        self.series_curve.setClipToView(True)
        self.series_curve.setDownsampling(auto=True)
        self.series_curve.setSkipFiniteCheck(True)

        self.point_curve = plot.plot(
            pen=None,
            symbol="o",
            symbolSize=4,
            symbolPen=pg.mkPen(70, 130, 180, 220),
            symbolBrush=pg.mkBrush(70, 130, 180, 120),
            antialias=False,
        )
        self.point_curve.setClipToView(True)
        self.point_curve.setDownsampling(auto=True)
        self.point_curve.setSkipFiniteCheck(True)

        self.selected_scatter = pg.ScatterPlotItem(
            size=4,
            pen=pg.mkPen(color=(250, 170, 20), width=1),
            brush=pg.mkBrush(255, 220, 60, 220),
            symbol="o",
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
        clear_selection_btn.clicked.connect(
            lambda: self._sync_selection_by_indices(np.array([], dtype=np.int64), source="plot")
        )

        self.line_style_combo = QtWidgets.QComboBox()
        self.line_style_combo.addItems(list(self.LINE_STYLES.keys()))
        self.line_style_combo.currentTextChanged.connect(self._apply_plot_styles)

        self.point_style_combo = QtWidgets.QComboBox()
        self.point_style_combo.addItems(list(self.POINT_STYLES.keys()))
        self.point_style_combo.currentTextChanged.connect(self._apply_plot_styles)

        hint = QtWidgets.QLabel(
            "Tip: Ctrl+drag = box select, Shift+drag = zoom box, drag = pan."
        )
        hint.setStyleSheet("color: #555;")

        layout.addWidget(reset_zoom_btn)
        layout.addWidget(clear_selection_btn)
        layout.addSpacing(14)
        layout.addWidget(QtWidgets.QLabel("Line:"))
        layout.addWidget(self.line_style_combo)
        layout.addWidget(QtWidgets.QLabel("Point style:"))
        layout.addWidget(self.point_style_combo)
        layout.addStretch(1)
        layout.addWidget(hint)

        self.line_style_combo.setCurrentText("Solid")
        self.point_style_combo.setCurrentText("Circle")
        self._apply_plot_styles()
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
        self.feature_ids_np = np.array(self.feature_ids, dtype=object)
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
        self.point_curve.setData(self.timestamps_s, self.values)
        self._configure_plot_limits()
        self._reset_chart_zoom()
        self.status_label.setText("Ready: 100,000 points loaded")

    def _reset_chart_zoom(self) -> None:
        if self.timestamps_s.size == 0:
            return
        x_min, x_max = self._x_bounds
        y_min, y_max = self._y_bounds
        self.plot_widget.plotItem.setXRange(x_min, x_max, padding=0.0)
        self.plot_widget.plotItem.setYRange(y_min, y_max, padding=0.0)

    def _configure_plot_limits(self) -> None:
        if self.timestamps_s.size == 0:
            return

        x_min = float(self.timestamps_s[0])
        x_max = float(self.timestamps_s[-1])
        y_min = float(np.min(self.values))
        y_max = float(np.max(self.values))

        x_span = max(1.0, x_max - x_min)
        y_span = max(1.0, y_max - y_min)

        x_pad = 0.02 * x_span
        y_pad = 0.08 * y_span

        self._x_bounds = (x_min - x_pad, x_max + x_pad)
        self._y_bounds = (y_min - y_pad, y_max + y_pad)

        vb = self.plot_widget.plotItem.vb
        vb.setLimits(
            xMin=self._x_bounds[0],
            xMax=self._x_bounds[1],
            yMin=self._y_bounds[0],
            yMax=self._y_bounds[1],
            maxXRange=x_span * 1.5,
            maxYRange=y_span * 1.8,
        )

    def _apply_plot_styles(self) -> None:
        line_name = self.line_style_combo.currentText()
        line_style = self.LINE_STYLES.get(line_name, Qt.SolidLine)

        show_points = line_style is None
        self.point_curve.setVisible(show_points)

        if line_style is None:
            self.series_curve.setPen(None)
        else:
            pen = QPen(QColor(70, 130, 180))
            pen.setWidth(1)
            pen.setStyle(line_style)
            self.series_curve.setPen(pen)

        point_name = self.point_style_combo.currentText()
        symbol = self.POINT_STYLES.get(point_name, "o")
        self.point_curve.setSymbol(symbol)
        self.selected_scatter.setSymbol(symbol)

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
        self._sync_selection_by_indices(np.flatnonzero(mask), source="plot")

    def _on_map_selection(self, selection) -> None:
        if selection.layer_id != self.layer.id:
            return
        if self._ignore_next_map_selection:
            self._ignore_next_map_selection = False
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

        self._sync_selection_by_indices(np.array([nearest], dtype=np.int64), source="plot")

    def _sync_selection(self, ids: list[str], *, source: str) -> None:
        unique_ids = list(dict.fromkeys(str(fid) for fid in ids))
        if not unique_ids:
            self._sync_selection_by_indices(np.array([], dtype=np.int64), source=source)
            return

        indices = self._ids_to_indices(unique_ids)
        self._sync_selection_by_indices(indices, source=source)

    def _ids_to_indices(self, ids: list[str]) -> np.ndarray:
        parsed: list[int] = []
        for fid in ids:
            if fid.startswith("ts_"):
                suffix = fid[3:]
                if suffix.isdigit():
                    idx = int(suffix)
                    if 0 <= idx < self.POINT_COUNT:
                        parsed.append(idx)
                        continue

            idx = self.id_to_idx.get(fid)
            if idx is not None:
                parsed.append(idx)

        return np.array(parsed, dtype=np.int64)

    def _sync_selection_by_indices(self, indices: np.ndarray, *, source: str) -> None:
        if self._selection_guard:
            return

        if indices.size == 0:
            indices = np.array([], dtype=np.int64)
        else:
            indices = np.unique(indices.astype(np.int64, copy=False))

        if (
            indices.size == self._current_selection_indices.size
            and np.array_equal(indices, self._current_selection_indices)
        ):
            return

        self._current_selection_indices = indices.copy()

        self._selection_guard = True
        try:
            if source != "table":
                self._set_table_selection_by_indices(indices)

            if source != "map":
                ids = self.feature_ids_np[indices].tolist() if indices.size else []
                self._ignore_next_map_selection = True
                self.map_widget.set_fast_points_selection(self.layer.id, ids)

            self._update_plot_selection_by_indices(indices)
            self._update_status_by_indices(indices)
        finally:
            self._selection_guard = False

    def _set_table_selection_by_indices(self, indices: np.ndarray) -> None:
        table_view = self.table.table
        sm = self.table.table.selectionModel()
        if sm is None:
            return

        blocker = QtCore.QSignalBlocker(sm)
        table_view.setUpdatesEnabled(False)
        try:
            if indices.size == 0:
                sm.clearSelection()
                return

            total = self.table.model.rowCount()
            if int(indices.size) == total:
                table_view.selectAll()
                return

            select_ranges = self._contiguous_ranges(indices)
            use_inverse = False
            deselect_ranges: list[tuple[int, int]] = []

            if int(indices.size) > (total // 2):
                unselected = np.setdiff1d(
                    np.arange(total, dtype=np.int64),
                    indices,
                    assume_unique=True,
                )
                deselect_ranges = self._contiguous_ranges(unselected)
                use_inverse = (len(deselect_ranges) + 1) < len(select_ranges)

            last_col = max(0, self.table.model.columnCount() - 1)

            if use_inverse:
                table_view.selectAll()
                if deselect_ranges:
                    deselection = QtCore.QItemSelection()
                    for start, end in deselect_ranges:
                        deselection.select(
                            self.table.model.index(start, 0),
                            self.table.model.index(end, last_col),
                        )
                    sm.select(
                        deselection,
                        QtCore.QItemSelectionModel.Deselect
                        | QtCore.QItemSelectionModel.Rows,
                    )
                return

            selection = QtCore.QItemSelection()
            for start, end in select_ranges:
                selection.select(
                    self.table.model.index(start, 0),
                    self.table.model.index(end, last_col),
                )

            sm.select(
                selection,
                QtCore.QItemSelectionModel.ClearAndSelect
                | QtCore.QItemSelectionModel.Rows,
            )
        finally:
            table_view.setUpdatesEnabled(True)
            del blocker

    def _contiguous_ranges(self, indices: np.ndarray) -> list[tuple[int, int]]:
        if indices.size == 0:
            return []

        breaks = np.flatnonzero(np.diff(indices) != 1) + 1
        starts = np.r_[indices[0], indices[breaks]]
        ends = np.r_[indices[breaks - 1], indices[-1]]
        return list(zip(starts.astype(int).tolist(), ends.astype(int).tolist()))

    def _update_plot_selection_by_indices(self, indices: np.ndarray) -> None:
        if indices.size == 0:
            self.selected_scatter.setData([], [])
            return

        x = self.timestamps_s[indices]
        y = self.values[indices]
        self.selected_scatter.setData(x=x, y=y)

    def _update_status_by_indices(self, indices: np.ndarray) -> None:
        total_selected = int(indices.size)
        if total_selected == 0:
            self.status_label.setText("Selected: 0 points")
            return

        lo = float(np.min(self.timestamps_s[indices]))
        hi = float(np.max(self.timestamps_s[indices]))
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
