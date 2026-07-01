#!/usr/bin/env python3
"""Manual CSV FastPoints viewer for profiling streaming load and selection.

This console app mirrors the large-CSV workflow used while investigating
FastPoints selection performance and prints PERF lines when
PYOPENLAYERSQT_PERF=1 or PYOPENLAYERSQT_BENCH=1.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import re
import sys
import time
from typing import Sequence

import numpy as np
import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from pyopenlayersqt import FastPointsStyle, OLMapWidget, RangeSliderWidget
from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget


def _sorted_indices_to_ranges(indices: np.ndarray) -> np.ndarray:
    """Compress sorted uint32 indices into inclusive [start, end] ranges."""
    if indices.size == 0:
        return np.empty((0, 2), dtype=np.uint32)
    sorted_indices = np.asarray(indices, dtype=np.uint32)
    breaks = np.flatnonzero(np.diff(sorted_indices) != 1) + 1
    starts = np.concatenate((sorted_indices[:1], sorted_indices[breaks]))
    ends = np.concatenate((sorted_indices[breaks - 1], sorted_indices[-1:]))
    return np.column_stack((starts, ends)).astype(np.uint32, copy=False)


def _wildcard_term_to_regex(term: str) -> str:
    """Translate a shell-style wildcard term into an Arrow-safe regex."""
    regex_parts: list[str] = ["^"]
    for char in term:
        if char == "*":
            regex_parts.append(".*")
        elif char == "?":
            regex_parts.append(".")
        else:
            regex_parts.append(re.escape(char))
    regex_parts.append("$")
    return "".join(regex_parts)


def _datetime_series_to_epoch_seconds(values: pd.Series) -> np.ndarray:
    """Convert a parsed pandas datetime Series to Unix epoch seconds.

    Use pandas' timedelta conversion from a fixed UTC epoch instead of guessing
    units from value magnitude.  AIS values like ``2022-03-31T00:00:01`` and
    near-epoch values like ``1970-01-01T00:00:01Z`` both convert correctly.
    """
    valid = values.notna().to_numpy(dtype=bool, copy=False)
    epoch = pd.Timestamp("1970-01-01T00:00:00Z")
    seconds = (values - epoch).dt.total_seconds()
    out = seconds.to_numpy(dtype=np.float64, copy=True)
    out[~valid] = np.nan
    return out


def _turbo_rgb(values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Approximate Google's Turbo color map for values in [0, 1]."""
    x = np.clip(values.astype(np.float64, copy=False), 0.0, 1.0)
    red = 34.61 + x * (
        1172.33 + x * (-10793.56 + x * (33300.12 + x * (-38394.49 + x * 14825.05)))
    )
    green = 23.31 + x * (
        557.33 + x * (1225.33 + x * (-3574.96 + x * (1073.77 + x * 707.56)))
    )
    blue = 27.20 + x * (
        3211.10 + x * (-15327.97 + x * (27814.00 + x * (-22569.18 + x * 6838.66)))
    )
    return (
        np.clip(np.rint(red), 0, 255).astype(np.uint32),
        np.clip(np.rint(green), 0, 255).astype(np.uint32),
        np.clip(np.rint(blue), 0, 255).astype(np.uint32),
    )


def _category_codes_to_packed_rgba(codes: np.ndarray) -> np.ndarray:
    """Map integer category codes to bright Turbo-like packed RGBA colors."""
    code_arr = np.asarray(codes, dtype=np.int64)
    safe_codes = np.where(code_arr < 0, 0, code_arr).astype(np.float64, copy=False)
    # Golden-ratio spacing keeps adjacent category codes visually distinct while
    # preserving a compact integer-code representation for large data sets.
    color_positions = np.mod(safe_codes * 0.6180339887498949, 1.0)
    red, green, blue = _turbo_rgb(color_positions)
    alpha = np.full(code_arr.shape, 255, dtype=np.uint32)
    packed = (
        (red << np.uint32(24))
        | (green << np.uint32(16))
        | (blue << np.uint32(8))
        | alpha
    )
    packed[code_arr < 0] = np.uint32(0x999999FF)
    return packed.astype(np.uint32, copy=False)


def perf_enabled() -> bool:
    return (
        os.environ.get("PYOPENLAYERSQT_BENCH", "") == "1"
        or os.environ.get("PYOPENLAYERSQT_PERF", "") == "1"
    )


def perf(message: str, **fields: object) -> None:
    if not perf_enabled():
        return
    suffix = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"PERF: app {message}" + (f" {suffix}" if suffix else ""), flush=True)


class DataFrameTableRow:
    """Lightweight table row backed by a chunk DataFrame.

    This avoids converting every CSV row into a Python dict during load. The
    table model only needs a mapping-like ``get`` method for visible cells and
    key extraction, so values can be fetched lazily from the retained chunk.
    """

    __slots__ = ("_df", "_row_index", "_layer_id", "_feature_id")

    def __init__(
        self, df: pd.DataFrame, row_index: int, layer_id: str, feature_id: str
    ) -> None:
        self._df = df
        self._row_index = row_index
        self._layer_id = layer_id
        self._feature_id = feature_id

    def get(self, key: str, default: object = None) -> object:
        if key == "_layer_id":
            return self._layer_id
        if key == "_feature_id":
            return self._feature_id
        if key in self._df.columns:
            return self._df[key].iat[self._row_index]
        return default


class CsvLoaderThread(QtCore.QThread):
    """Background thread that streams CSV chunks to the GUI thread."""

    progress_update = QtCore.Signal(int)
    status_update = QtCore.Signal(str)
    chunk_ready = QtCore.Signal(object)
    finished_success = QtCore.Signal(list)
    finished_error = QtCore.Signal(str)

    def __init__(self, paths: Sequence[str], base_columns: list[str], chunk_size: int):
        super().__init__()
        self.paths = list(paths)
        self.base_columns = base_columns
        self.chunk_size = int(chunk_size)

    def run(self) -> None:
        try:
            error_files: list[str] = []
            self.status_update.emit("Calculating total data size...")
            file_sizes = {path: max(os.path.getsize(path), 0) for path in self.paths}
            total_bytes = max(sum(file_sizes.values()), 1)
            bytes_finished = 0

            for path in self.paths:
                file_name = os.path.basename(path)
                file_size = file_sizes.get(path, 0)
                self.status_update.emit(f"Streaming chunks from {file_name}...")
                try:
                    temp_schema = pd.read_csv(path, nrows=0)
                    if list(temp_schema.columns) != self.base_columns:
                        error_files.append(file_name)
                        bytes_finished += file_size
                        self.progress_update.emit(
                            min(int((bytes_finished / total_bytes) * 100), 100)
                        )
                        continue

                    with open(path, "rb") as fh:
                        for chunk in pd.read_csv(fh, chunksize=self.chunk_size):
                            self.chunk_ready.emit(chunk)
                            try:
                                current_bytes = bytes_finished + fh.tell()
                            except Exception:
                                current_bytes = bytes_finished
                            self.progress_update.emit(
                                min(int((current_bytes / total_bytes) * 100), 100)
                            )
                    bytes_finished += file_size
                except Exception:
                    error_files.append(file_name)
                    bytes_finished += file_size

            self.progress_update.emit(100)
            self.finished_success.emit(error_files)
        except Exception as exc:
            self.finished_error.emit(str(exc))


class CsvImportDialog(QtWidgets.QDialog):
    def __init__(
        self,
        columns: Sequence[str],
        default_lat: str | None = None,
        default_lon: str | None = None,
        default_time: str | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Map CSV Columns")
        layout = QtWidgets.QFormLayout(self)

        self.lat_cb = QtWidgets.QComboBox()
        self.lat_cb.addItems(columns)
        self._set_default(self.lat_cb, default_lat, ["lat", "latitude", "y"])

        self.lon_cb = QtWidgets.QComboBox()
        self.lon_cb.addItems(columns)
        self._set_default(self.lon_cb, default_lon, ["lon", "longitude", "lng", "x"])

        self.time_cb = QtWidgets.QComboBox()
        self.time_cb.addItem("None")
        self.time_cb.addItems(columns)
        self._set_default(self.time_cb, default_time, ["time", "date", "timestamp"])

        layout.addRow("Latitude Column:", self.lat_cb)
        layout.addRow("Longitude Column:", self.lon_cb)
        layout.addRow("Time Column:", self.time_cb)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_default(
        self, combo_box: QtWidgets.QComboBox, explicit_default: str | None, auto_matches: list[str]
    ) -> None:
        if explicit_default and explicit_default in [
            combo_box.itemText(i) for i in range(combo_box.count())
        ]:
            combo_box.setCurrentText(explicit_default)
            return
        for i in range(combo_box.count()):
            if combo_box.itemText(i).lower() in auto_matches:
                combo_box.setCurrentIndex(i)
                break

    def get_selections(self) -> tuple[str, str, str]:
        return (
            self.lat_cb.currentText(),
            self.lon_cb.currentText(),
            self.time_cb.currentText(),
        )


class PyOpenLayersCsvApp(QtWidgets.QMainWindow):
    def __init__(self, cli_args: argparse.Namespace):
        super().__init__()
        self.setWindowTitle("CSV Viewer")
        self.resize(1200, 800)
        self.cli_args = cli_args

        self.df: pd.DataFrame | None = None
        self.chunk_list: list[pd.DataFrame] = []
        self.global_fid_counter = 0
        self.current_lat_col: str | None = None
        self.current_lon_col: str | None = None
        self.current_time_col: str | None = None
        self.mapped_epoch_col = "_slider_epoch_time"
        self.feature_ids: list[str] | np.ndarray = []
        self._visible_mask: np.ndarray | None = None
        self._deleted_mask: np.ndarray | None = None
        self._keyword_mask: np.ndarray | None = None
        self._keyword_filter: tuple[str, str] | None = None
        self.current_selection_fids: list[str] = []
        self.table_widget: FeatureTableWidget | None = None
        self._map_selection_conn = None
        self._slider_range_conn = None
        self._table_sort_column: int | None = None
        self._table_sort_order = QtCore.Qt.SortOrder.AscendingOrder
        self._pending_time_filter: tuple[float, float] | None = None
        self._time_filter_range: tuple[float, float] | None = None
        self._time_filter_timer = QtCore.QTimer(self)
        self._time_filter_timer.setSingleShot(True)
        self._time_filter_timer.setInterval(50)
        self._time_filter_timer.timeout.connect(self._apply_pending_time_filter)

        self._setup_ui()
        if self.cli_args.csv:
            QtCore.QTimer.singleShot(
                100,
                lambda: self.process_csv(
                    self.cli_args.csv,
                    self.cli_args.lat,
                    self.cli_args.lon,
                    self.cli_args.time,
                ),
            )

    def _setup_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        toolbar = self.addToolBar("Map Tools")
        self.measure_action = QtGui.QAction(
            self._measurement_icon(), "Measurement Mode", self
        )
        self.measure_action.setCheckable(True)
        self.measure_action.triggered.connect(self.toggle_measurement)
        toolbar.addAction(self.measure_action)

        delete_action = QtGui.QAction(
            self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TrashIcon),
            "Delete Selected",
            self,
        )
        delete_action.triggered.connect(self.delete_selected_features)
        toolbar.addAction(delete_action)

        save_action = QtGui.QAction(
            self.style().standardIcon(
                QtWidgets.QStyle.StandardPixmap.SP_DialogSaveButton
            ),
            "Save Selected",
            self,
        )
        save_action.triggered.connect(self.save_selected_csv)
        toolbar.addAction(save_action)

        toolbar.addSeparator()
        toolbar.addWidget(QtWidgets.QLabel("  Color By: "))
        self.color_cb = QtWidgets.QComboBox()
        self.color_cb.addItem("None (Uniform)")
        self.color_cb.currentTextChanged.connect(self.apply_color_by)
        toolbar.addWidget(self.color_cb)

        toolbar.addSeparator()
        toolbar.addWidget(QtWidgets.QLabel("  Filter Column: "))
        self.keyword_column_cb = QtWidgets.QComboBox()
        self.keyword_column_cb.setEnabled(False)
        toolbar.addWidget(self.keyword_column_cb)

        self.keyword_edit = QtWidgets.QLineEdit()
        self.keyword_edit.setPlaceholderText("Keyword, wildcard, or A or B")
        self.keyword_edit.setClearButtonEnabled(True)
        self.keyword_edit.setEnabled(False)
        self.keyword_edit.returnPressed.connect(self.apply_keyword_filter)
        toolbar.addWidget(self.keyword_edit)

        keyword_action = QtGui.QAction("Apply Filter", self)
        keyword_action.triggered.connect(self.apply_keyword_filter)
        toolbar.addAction(keyword_action)

        clear_keyword_action = QtGui.QAction("Clear Filter", self)
        clear_keyword_action.triggered.connect(self.clear_keyword_filter)
        toolbar.addAction(clear_keyword_action)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        layout.addWidget(self.splitter, stretch=1)

        map_panel = QtWidgets.QWidget()
        map_layout = QtWidgets.QVBoxLayout(map_panel)
        map_layout.setContentsMargins(0, 0, 0, 0)

        self.map_widget = OLMapWidget(center=(0, 0), zoom=2)
        self.map_widget.perfReceived.connect(
            lambda payload: perf("bridge_event", payload=payload)
        )
        map_layout.addWidget(self.map_widget, stretch=1)

        self.slider = RangeSliderWidget(is_iso8601=True)
        self.slider.setEnabled(False)
        map_layout.addWidget(self.slider)
        self.splitter.addWidget(map_panel)

        self.fast_layer = self.map_widget.add_fast_points_layer(
            name="Data Points",
            selectable=True,
            style=FastPointsStyle(default_color="steelblue", radius=3),
            cell_size_m=self.cli_args.cell_size_m,
        )

        self.table_container = QtWidgets.QWidget()
        self.table_layout = QtWidgets.QVBoxLayout(self.table_container)
        self.table_layout.setContentsMargins(0, 0, 0, 0)
        self.splitter.addWidget(self.table_container)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([560, 240])

        file_menu = self.menuBar().addMenu("File")
        load_action = QtGui.QAction("Load CSV(s)...", self)
        load_action.triggered.connect(self.load_csv_from_menu)
        file_menu.addAction(load_action)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        quit_action = QtGui.QAction("Quit", self)
        quit_action.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(QtWidgets.QApplication.quit)
        file_menu.addAction(quit_action)

        status_bar = QtWidgets.QStatusBar(self)
        self.setStatusBar(status_bar)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedWidth(300)
        self.progress_bar.setVisible(False)
        status_bar.addPermanentWidget(self.progress_bar)

    def _configure_column_controls(self, columns: Sequence[str]) -> None:
        """Populate column-based controls after a CSV load is accepted."""
        self.color_cb.blockSignals(True)
        self.color_cb.clear()
        self.color_cb.addItem("None (Uniform)")
        self.color_cb.addItems(columns)
        self._resize_combo_to_items(self.color_cb)
        self.color_cb.blockSignals(False)

        self.keyword_column_cb.blockSignals(True)
        self.keyword_column_cb.clear()
        self.keyword_column_cb.addItems(columns)
        self.keyword_column_cb.setEnabled(bool(columns))
        self._resize_combo_to_items(self.keyword_column_cb)
        self.keyword_column_cb.blockSignals(False)
        self.keyword_edit.clear()
        self.keyword_edit.setEnabled(bool(columns))

    def _resize_table_columns_to_contents(self) -> None:
        """Resize CSV table columns to fit loaded headers and visible cell data."""
        if self.table_widget is None:
            return
        table = self.table_widget.table
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)

    def _resize_combo_to_items(self, combo_box: QtWidgets.QComboBox) -> None:
        """Resize a combo box and popup to fit the loaded column names."""
        if combo_box.count() == 0:
            return
        metrics = combo_box.fontMetrics()
        max_text_width = max(
            metrics.horizontalAdvance(combo_box.itemText(i))
            for i in range(combo_box.count())
        )
        # Include room for the drop-down arrow, frame, and item padding so long
        # CSV column names are readable in both the closed control and popup.
        width = max_text_width + 48
        combo_box.setMinimumWidth(width)
        combo_box.view().setMinimumWidth(width)
        combo_box.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents
        )

    def _measurement_icon(self) -> QtGui.QIcon:
        """Build a small ruler icon for the measurement action."""
        pixmap = QtGui.QPixmap(24, 24)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        try:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            pen = QtGui.QPen(QtGui.QColor("#455a64"), 2)
            painter.setPen(pen)
            painter.setBrush(QtGui.QColor("#fff59d"))
            polygon = QtGui.QPolygonF(
                [
                    QtCore.QPointF(4, 17),
                    QtCore.QPointF(17, 4),
                    QtCore.QPointF(21, 8),
                    QtCore.QPointF(8, 21),
                ]
            )
            painter.drawPolygon(polygon)
            painter.drawLine(QtCore.QPointF(9, 16), QtCore.QPointF(11, 18))
            painter.drawLine(QtCore.QPointF(12, 13), QtCore.QPointF(14, 15))
            painter.drawLine(QtCore.QPointF(15, 10), QtCore.QPointF(17, 12))
        finally:
            painter.end()
        return QtGui.QIcon(pixmap)

    def toggle_measurement(self, checked: bool) -> None:
        self.map_widget.set_measure_mode(checked)
        if not checked:
            self.map_widget.clear_measurements()

    def _feature_ids_to_row_indices(self, feature_ids: Sequence[str]) -> np.ndarray:
        """Return stable CSV/JS row indices for app-generated feature ids."""
        indices: list[int] = []
        for fid in feature_ids:
            if not fid.startswith("pt_"):
                continue
            try:
                indices.append(int(fid[3:]))
            except ValueError:
                continue
        if self.df is None:
            return np.empty(0, dtype=np.uint32)
        row_count = len(self.df)
        return np.asarray(
            [idx for idx in indices if 0 <= idx < row_count], dtype=np.uint32
        )

    def _clear_time_slider(self) -> None:
        """Disable the time slider and disconnect stale range callbacks."""
        self._time_filter_timer.stop()
        self._pending_time_filter = None
        self._time_filter_range = None
        if self._slider_range_conn:
            self.slider.rangeChanged.disconnect(self._slider_range_conn)
            self._slider_range_conn = None
        self.slider.set_value_formatter(None)
        self.slider.setEnabled(False)

    def _reset_loaded_data_state(self) -> None:
        """Clear loaded CSV state before starting or after failing a load."""
        self.df = None
        self.chunk_list = []
        self.feature_ids = []
        self._visible_mask = None
        self._deleted_mask = None
        self._keyword_mask = None
        self._keyword_filter = None
        self.current_selection_fids = []
        self._table_sort_column = None
        self._table_sort_order = QtCore.Qt.SortOrder.AscendingOrder
        self.global_fid_counter = 0
        self._clear_time_slider()

    def _sync_table_visible_rows(self) -> None:
        """Apply current filter masks without compacting table row order."""
        if self.table_widget is None or self.df is None:
            return
        visible = (
            np.ones(len(self.df), dtype=bool)
            if self._visible_mask is None
            else self._visible_mask.copy()
        )
        if self._deleted_mask is not None:
            visible &= ~self._deleted_mask
        if visible.all():
            visible_indices = None
        else:
            visible_indices = np.flatnonzero(visible).astype(np.uint32)
        self._set_table_visible_indices(visible_indices)

    def _set_table_visible_indices(
        self, indices: Sequence[int] | np.ndarray | None
    ) -> None:
        """Apply table visibility while preserving immutable CSV source indices."""
        if self.table_widget is None:
            return
        if self._table_sort_column is not None:
            sorted_indices = self.table_widget.model.sorted_source_indices(
                self._table_sort_column, self._table_sort_order, indices
            )
            self.table_widget.set_visible_row_indices(sorted_indices)
            return
        self.table_widget.set_visible_row_indices(indices)

    def delete_selected_features(self) -> None:
        if not self.current_selection_fids:
            return
        self.fast_layer.remove_points(self.current_selection_fids)
        deleted_indices = self._feature_ids_to_row_indices(self.current_selection_fids)
        if self.df is not None and deleted_indices.size:
            if self._deleted_mask is None or len(self._deleted_mask) != len(self.df):
                self._deleted_mask = np.zeros(len(self.df), dtype=bool)
            self._deleted_mask[deleted_indices] = True
            if self._visible_mask is not None:
                self._visible_mask[deleted_indices] = False
            self._sync_table_visible_rows()
        if self.table_widget is not None:
            self.table_widget.clear_selection()
        self.current_selection_fids = []

    def save_selected_csv(self) -> None:
        if not self.current_selection_fids or self.df is None:
            QtWidgets.QMessageBox.information(
                self, "No Selection", "Please select points on the map or in the table first."
            )
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Selected Data", "", "CSV Files (*.csv)"
        )
        if not path:
            return
        mask = self.df["_fid"].isin(self.current_selection_fids)
        export_df = self.df[mask].copy()
        cols_to_drop = ["_fid"]
        if self.mapped_epoch_col in export_df.columns:
            cols_to_drop.append(self.mapped_epoch_col)
        export_df.drop(columns=cols_to_drop, inplace=True, errors="ignore")
        export_df.to_csv(path, index=False)
        QtWidgets.QMessageBox.information(
            self, "Success", f"Successfully saved {len(export_df)} records to:\n{path}"
        )

    def load_csv_from_menu(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Open CSV Data", "", "CSV Files (*.csv)"
        )
        if paths:
            self.process_csv(paths)

    def process_csv(
        self,
        paths: str | Sequence[str],
        cli_lat: str | None = None,
        cli_lon: str | None = None,
        cli_time: str | None = None,
    ) -> None:
        if isinstance(paths, str):
            paths = [paths]
        if not paths:
            return

        first_file = paths[0]
        base_df = pd.read_csv(first_file, nrows=0)
        base_columns = list(base_df.columns)

        cli_time_valid = cli_time in (None, "", "None") or cli_time in base_columns
        if cli_lat in base_columns and cli_lon in base_columns and cli_time_valid:
            lat_col, lon_col, time_col = cli_lat, cli_lon, cli_time
        else:
            dialog = CsvImportDialog(base_columns, cli_lat, cli_lon, cli_time, self)
            if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                return
            lat_col, lon_col, time_col = dialog.get_selections()

        self.current_lat_col = lat_col
        self.current_lon_col = lon_col
        self.current_time_col = time_col
        self._configure_column_controls(base_columns)

        self.centralWidget().setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)

        self.fast_layer.clear()
        self._reset_loaded_data_state()
        self._initialize_empty_table(base_columns)

        self.loader_thread = CsvLoaderThread(paths, base_columns, self.cli_args.chunk_size)
        self.loader_thread.chunk_ready.connect(self._on_chunk_ready)
        self.loader_thread.progress_update.connect(self.progress_bar.setValue)
        self.loader_thread.status_update.connect(self.statusBar().showMessage)
        self.loader_thread.finished_success.connect(self._on_load_success)
        self.loader_thread.finished_error.connect(self._on_load_error)
        self.loader_thread.start()

    def _initialize_empty_table(self, columns: Sequence[str]) -> None:
        if self.table_widget is not None:
            self.table_layout.removeWidget(self.table_widget)
            self.table_widget.deleteLater()
            self.table_widget = None

        columns_spec = [
            ColumnSpec(col, lambda row, c=col: str(row.get(c, "")))
            for col in columns
            if col not in [self.mapped_epoch_col, "_fid"]
        ]
        self.table_widget = FeatureTableWidget(
            columns=columns_spec,
            key_fn=lambda row: (
                str(row.get("_layer_id", "")),
                str(row.get("_feature_id", "")),
            ),
            sorting_enabled=False,
        )
        if self.cli_args.sortable_table:
            self._install_table_sorting()
        self.table_layout.addWidget(self.table_widget)

        def on_table_selection(keys):
            perf_start = time.perf_counter()
            fids = [fid for layer_id, fid in keys if layer_id == self.fast_layer.id]
            self.map_widget.set_fast_points_selection(self.fast_layer.id, fids)
            self.current_selection_fids = fids
            perf(
                "table_to_map_selection",
                selection_count=len(fids),
                elapsed_ms=round((time.perf_counter() - perf_start) * 1000.0, 2),
            )

        self.table_widget.selectionKeysChanged.connect(on_table_selection)

        if self._map_selection_conn:
            self.map_widget.selectionChanged.disconnect(self._map_selection_conn)

        def on_map_selection(selection):
            if selection.layer_id != self.fast_layer.id:
                return
            perf_start = time.perf_counter()
            self.current_selection_fids = selection.feature_ids
            keys = [(selection.layer_id, fid) for fid in selection.feature_ids]
            self.table_widget.select_keys(keys, clear_first=True)
            perf(
                "map_to_table_selection",
                selection_count=len(keys),
                elapsed_ms=round((time.perf_counter() - perf_start) * 1000.0, 2),
            )

        self._map_selection_conn = self.map_widget.selectionChanged.connect(on_map_selection)


    def _install_table_sorting(self) -> None:
        if self.table_widget is None:
            return
        header = self.table_widget.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self._sort_table_column)

    def _sort_table_column(self, column: int) -> None:
        if self.table_widget is None:
            return
        header = self.table_widget.table.horizontalHeader()
        current_section = header.sortIndicatorSection()
        current_order = header.sortIndicatorOrder()
        if current_section == column and current_order == QtCore.Qt.SortOrder.AscendingOrder:
            order = QtCore.Qt.SortOrder.DescendingOrder
        else:
            order = QtCore.Qt.SortOrder.AscendingOrder

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            self.statusBar().showMessage("Sorting table...")
            self._table_sort_column = column
            self._table_sort_order = order
            self._sync_table_visible_rows()
            header.setSortIndicator(column, order)
            self.statusBar().showMessage("Table sorted.", 5000)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def _on_chunk_ready(self, chunk_df: pd.DataFrame) -> None:
        perf_start = time.perf_counter()
        incoming_rows = len(chunk_df)
        chunk_df = chunk_df.copy()

        if self.current_time_col and self.current_time_col != "None":
            if pd.api.types.is_numeric_dtype(chunk_df[self.current_time_col]):
                chunk_df[self.mapped_epoch_col] = chunk_df[
                    self.current_time_col
                ].astype(float)
            else:
                parsed_dates = pd.to_datetime(
                    chunk_df[self.current_time_col],
                    format="mixed",
                    errors="coerce",
                    utc=True,
                )
                chunk_df[self.mapped_epoch_col] = _datetime_series_to_epoch_seconds(
                    parsed_dates
                )

        coords_start = time.perf_counter()
        lats = pd.to_numeric(
            chunk_df[self.current_lat_col],
            errors="coerce",
        ).to_numpy(dtype=np.float64, copy=False)
        lons = pd.to_numeric(
            chunk_df[self.current_lon_col],
            errors="coerce",
        ).to_numpy(dtype=np.float64, copy=False)
        valid_coords = np.isfinite(lats) & np.isfinite(lons)
        skipped_invalid_coords = int(incoming_rows - np.count_nonzero(valid_coords))
        if skipped_invalid_coords:
            chunk_df = chunk_df.loc[valid_coords].copy()
            lats = lats[valid_coords]
            lons = lons[valid_coords]
        num_rows = len(chunk_df)
        if num_rows == 0:
            perf(
                "chunk_ready_skipped",
                rows=incoming_rows,
                skipped_invalid_coords=skipped_invalid_coords,
            )
            return

        chunk_df[self.current_lat_col] = lats
        chunk_df[self.current_lon_col] = lons
        start_idx = self.global_fid_counter
        chunk_fids = [f"pt_{i}" for i in range(start_idx, start_idx + num_rows)]
        chunk_df["_fid"] = chunk_fids
        coords = np.column_stack((lats, lons))
        coords_ms = (time.perf_counter() - coords_start) * 1000.0

        map_start = time.perf_counter()
        self.fast_layer.add_points(coords=coords, ids=chunk_fids, redraw=False)
        map_ms = (time.perf_counter() - map_start) * 1000.0

        table_start = time.perf_counter()
        table_rows = (
            DataFrameTableRow(chunk_df, row_index, self.fast_layer.id, fid)
            for row_index, fid in enumerate(chunk_fids)
        )
        table_rows_ms = (time.perf_counter() - table_start) * 1000.0

        append_start = time.perf_counter()
        self.table_widget.append_rows(table_rows)
        append_ms = (time.perf_counter() - append_start) * 1000.0

        self.chunk_list.append(chunk_df)
        self.feature_ids.extend(chunk_fids)
        self.global_fid_counter += num_rows
        perf(
            "chunk_ready",
            rows=num_rows,
            incoming_rows=incoming_rows,
            skipped_invalid_coords=skipped_invalid_coords,
            coords_ms=round(coords_ms, 2),
            map_add_ms=round(map_ms, 2),
            table_rows_ms=round(table_rows_ms, 2),
            table_append_ms=round(append_ms, 2),
            total_ms=round((time.perf_counter() - perf_start) * 1000.0, 2),
        )

    def _on_load_success(self, error_files: list[str]) -> None:
        if not self.chunk_list:
            self._reset_loaded_data_state()
            self._cleanup_load_ui()
            QtWidgets.QMessageBox.warning(self, "No Data", "No valid data could be loaded.")
            return
        self.statusBar().showMessage("Finalizing UI sync...")
        self.df = pd.concat(self.chunk_list, ignore_index=True)
        self.feature_ids = np.array(self.feature_ids)
        self._visible_mask = np.ones(len(self.df), dtype=bool)
        self._deleted_mask = np.zeros(len(self.df), dtype=bool)
        self._keyword_mask = None
        self._keyword_filter = None
        self.fast_layer.redraw()
        self._setup_slider_and_view()
        self._cleanup_load_ui()
        QtCore.QTimer.singleShot(0, self._resize_table_columns_to_contents)
        if error_files:
            QtWidgets.QMessageBox.warning(
                self,
                "Schema Mismatch",
                (
                    "The following files had structural differences or read errors "
                    "and were skipped:\n\n"
                    + "\n".join(error_files)
                ),
            )
        self.statusBar().showMessage(f"Successfully loaded {len(self.df):,} points.", 10000)

    def _on_load_error(self, error_msg: str) -> None:
        self._reset_loaded_data_state()
        self._cleanup_load_ui()
        QtWidgets.QMessageBox.critical(self, "Error Loading Data", error_msg)
        self.statusBar().showMessage("Load failed.")

    def _cleanup_load_ui(self) -> None:
        QtWidgets.QApplication.restoreOverrideCursor()
        self.progress_bar.setVisible(False)
        self.centralWidget().setEnabled(True)

    def _setup_slider_and_view(self) -> None:
        if self.df is None:
            return
        if self.current_time_col != "None" and self.mapped_epoch_col in self.df.columns:
            valid_times = self.df[self.mapped_epoch_col].dropna()
            if valid_times.empty:
                self.slider.setEnabled(False)
                return
            t_min = float(valid_times.min())
            t_max = float(valid_times.max())
            if self._slider_range_conn:
                self.slider.rangeChanged.disconnect(self._slider_range_conn)
                self._slider_range_conn = None
            self.slider.set_value_formatter(None)
            self.slider.set_available_range(
                self._epoch_to_iso8601(t_min),
                self._epoch_to_iso8601(t_max),
            )
            self.slider.setEnabled(True)
            self._slider_range_conn = self.slider.rangeChanged.connect(
                self._on_time_slider_changed
            )
        else:
            if self._slider_range_conn:
                self.slider.rangeChanged.disconnect(self._slider_range_conn)
                self._slider_range_conn = None
            self.slider.set_value_formatter(None)
            self.slider.setEnabled(False)

        lats = self.df[self.current_lat_col].values
        lons = self.df[self.current_lon_col].values
        valid_lats = lats[~np.isnan(lats)]
        valid_lons = lons[~np.isnan(lons)]
        if len(valid_lats) > 0:
            self.map_widget.set_center((np.mean(valid_lats), np.mean(valid_lons)))

    def apply_color_by(self, column_name: str) -> None:
        if self.df is None:
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            if column_name == "None (Uniform)":
                self.fast_layer.clear_colors()
                return

            codes, unique_values = pd.factorize(self.df[column_name], sort=False)
            packed_colors = _category_codes_to_packed_rgba(codes)
            self.fast_layer.set_packed_colors(self.feature_ids, packed_colors)
            perf(
                "color_by",
                column=column_name,
                category_count=len(unique_values),
                row_count=len(codes),
            )
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def _epoch_to_iso8601(self, value: float) -> str:
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")

    def _slider_value_to_epoch(self, value: object) -> float:
        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).timestamp()
        return float(value)

    def _on_time_slider_changed(self, min_val: object, max_val: object) -> None:
        self._pending_time_filter = (
            self._slider_value_to_epoch(min_val),
            self._slider_value_to_epoch(max_val),
        )
        self._time_filter_timer.start()

    def _apply_pending_time_filter(self) -> None:
        if self._pending_time_filter is None:
            return
        min_val, max_val = self._pending_time_filter
        self._pending_time_filter = None
        self.filter_by_time(min_val, max_val)

    def _keyword_terms(self, pattern: str) -> list[str]:
        """Split a keyword expression into case-insensitive OR terms."""
        return [
            term.strip()
            for term in re.split(r"\s+or\s+", pattern)
            if term.strip()
        ]

    def _build_keyword_mask(self, column_name: str, pattern: str) -> np.ndarray:
        """Return rows whose selected column matches the keyword expression."""
        if self.df is None:
            return np.empty(0, dtype=bool)
        if column_name not in self.df.columns:
            return np.zeros(len(self.df), dtype=bool)
        values = self.df[column_name].astype("string").fillna("").str.lower()
        mask = np.zeros(len(values), dtype=bool)
        for term in self._keyword_terms(pattern):
            lowered = term.lower()
            if any(char in lowered for char in "*?"):
                regex = _wildcard_term_to_regex(lowered)
                term_mask = values.str.match(regex, na=False).to_numpy(
                    dtype=bool, copy=False
                )
            else:
                term_mask = values.str.contains(
                    re.escape(lowered), regex=True, na=False
                ).to_numpy(dtype=bool, copy=False)
            mask |= term_mask
        return mask

    def _combined_filter_mask(self) -> np.ndarray:
        """Combine time, keyword, and deleted-row filters into one mask."""
        if self.df is None:
            return np.empty(0, dtype=bool)
        mask = np.ones(len(self.df), dtype=bool)
        if (
            self._time_filter_range is not None
            and self.mapped_epoch_col in self.df.columns
        ):
            min_val, max_val = self._time_filter_range
            time_values = self.df[self.mapped_epoch_col].to_numpy(
                dtype=float, copy=False
            )
            mask &= (time_values >= min_val) & (time_values <= max_val)
        if self._keyword_mask is not None and len(self._keyword_mask) == len(mask):
            mask &= self._keyword_mask
        deleted_mask = self._deleted_mask
        if deleted_mask is not None and len(deleted_mask) == len(mask):
            mask &= np.logical_not(deleted_mask)
        return mask

    def _apply_visibility_mask(
        self, new_visible: np.ndarray, perf_event: str, **perf_fields: object
    ) -> None:
        """Apply a combined visibility mask to map points and the table."""
        if self.df is None:
            return
        if self._visible_mask is None or len(self._visible_mask) != len(new_visible):
            self._visible_mask = np.ones(len(new_visible), dtype=bool)

        visible_indices = np.flatnonzero(new_visible).astype(np.uint32)
        hide_indices = np.flatnonzero(self._visible_mask & ~new_visible).astype(
            np.uint32
        )
        show_indices = np.flatnonzero(~self._visible_mask & new_visible).astype(
            np.uint32
        )
        self._visible_mask = new_visible

        all_rows_visible = visible_indices.size == len(new_visible)
        visible_ranges = np.empty((0, 2), dtype=np.uint32)
        rebuild_from_ranges = False
        if not all_rows_visible and show_indices.size > 50_000:
            visible_ranges = _sorted_indices_to_ranges(visible_indices)
            rebuild_from_ranges = visible_ranges.size < show_indices.size
        used_show_only = (
            not all_rows_visible and visible_indices.size < hide_indices.size
        )
        if all_rows_visible:
            # Restoring the full range is a common path after narrowing the
            # filters.  Sending millions of indices back to JavaScript is
            # much slower than one reset command, and the JS side can rebuild
            # quadtree visibility counts in a single pass.
            self.fast_layer.show_all_features()
        elif rebuild_from_ranges:
            # Time filters usually produce contiguous row windows.  Rebuild the
            # visible set from compressed ranges instead of re-enabling millions
            # of individual indices and updating the quadtree for each point.
            self.fast_layer.show_only_index_ranges(visible_ranges)
        elif used_show_only:
            self.fast_layer.show_only_indices(visible_indices)
        elif hide_indices.size:
            self.fast_layer.hide_indices(hide_indices)
        if (
            show_indices.size
            and not used_show_only
            and not all_rows_visible
            and not rebuild_from_ranges
        ):
            self.fast_layer.show_indices(show_indices)

        self._sync_table_visible_rows()
        perf(
            perf_event,
            hide_count=int(hide_indices.size),
            show_count=int(show_indices.size),
            visible_count=int(visible_indices.size),
            show_only=used_show_only,
            range_rebuild=rebuild_from_ranges,
            range_count=int(len(visible_ranges)),
            **perf_fields,
        )

    def apply_keyword_filter(self) -> None:
        """Filter visible rows by a selected column and keyword expression."""
        if self.df is None:
            return
        column_name = self.keyword_column_cb.currentText()
        pattern = self.keyword_edit.text().strip()
        if not column_name or not pattern:
            self.clear_keyword_filter()
            return

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            self.statusBar().showMessage("Applying keyword filter...")
            self._keyword_filter = (column_name, pattern)
            self._keyword_mask = self._build_keyword_mask(column_name, pattern)
            self._apply_visibility_mask(
                self._combined_filter_mask(),
                "filter_by_keyword",
                column=column_name,
                terms=len(self._keyword_terms(pattern)),
            )
            visible_count = int(np.count_nonzero(self._visible_mask))
            self.statusBar().showMessage(
                f"Keyword filter matched {visible_count:,} rows.", 5000
            )
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def clear_keyword_filter(self) -> None:
        """Clear the keyword filter while preserving other active filters."""
        if self.df is None:
            self.keyword_edit.clear()
            return
        self._keyword_filter = None
        self._keyword_mask = None
        self.keyword_edit.clear()
        self._apply_visibility_mask(
            self._combined_filter_mask(), "clear_keyword_filter"
        )
        self.statusBar().showMessage("Keyword filter cleared.", 5000)

    def filter_by_time(self, min_val: float, max_val: float) -> None:
        if self.df is None:
            return
        self._time_filter_range = (min_val, max_val)
        self._apply_visibility_mask(self._combined_filter_mask(), "filter_by_time")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PyOpenLayersQt CSV FastPoints viewer")
    parser.add_argument("--csv", type=str, nargs="+", default=None)
    parser.add_argument("--lat", type=str, default=None)
    parser.add_argument("--lon", type=str, default=None)
    parser.add_argument("--time", type=str, default=None)
    parser.add_argument("--chunk-size", type=int, default=50_000)
    parser.add_argument("--cell-size-m", type=float, default=50_000.0)
    parser.add_argument(
        "--sortable-table",
        action="store_true",
        help="Enable header-click table sorting. This can block for very large CSVs.",
    )
    parser.add_argument("--disable-gpu", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.disable_gpu:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
    app = QtWidgets.QApplication(sys.argv)
    window = PyOpenLayersCsvApp(args)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
