#!/usr/bin/env python3
"""Manual CSV FastPoints viewer for profiling streaming load and selection.

This console app mirrors the large-CSV workflow used while investigating
FastPoints selection performance and prints PERF lines when
PYOPENLAYERSQT_PERF=1 or PYOPENLAYERSQT_BENCH=1.
"""

from __future__ import annotations

import argparse
import colorsys
import hashlib
import os
import sys
import time
from typing import Sequence

import numpy as np
import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from pyopenlayersqt import FastPointsStyle, OLMapWidget, RangeSliderWidget
from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget


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
        self.setWindowTitle("Fast Points CSV Viewer")
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
        self.current_selection_fids: list[str] = []
        self.table_widget: FeatureTableWidget | None = None
        self._map_selection_conn = None
        self._slider_range_conn = None

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

        self.map_widget = OLMapWidget(center=(0, 0), zoom=2)
        self.map_widget.perfReceived.connect(lambda payload: perf("bridge_event", payload=payload))
        layout.addWidget(self.map_widget, stretch=5)

        self.fast_layer = self.map_widget.add_fast_points_layer(
            name="Data Points",
            selectable=True,
            style=FastPointsStyle(default_color="steelblue", radius=3),
            cell_size_m=self.cli_args.cell_size_m,
        )

        self.slider = RangeSliderWidget()
        self.slider.setEnabled(False)
        layout.addWidget(self.slider)

        self.table_container = QtWidgets.QWidget()
        self.table_layout = QtWidgets.QVBoxLayout(self.table_container)
        self.table_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table_container, stretch=2)

        file_menu = self.menuBar().addMenu("File")
        load_action = QtGui.QAction("Load CSV(s)...", self)
        load_action.triggered.connect(self.load_csv_from_menu)
        file_menu.addAction(load_action)
        file_menu.addAction(save_action)

        status_bar = QtWidgets.QStatusBar(self)
        self.setStatusBar(status_bar)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedWidth(300)
        self.progress_bar.setVisible(False)
        status_bar.addPermanentWidget(self.progress_bar)

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

    def delete_selected_features(self) -> None:
        if not self.current_selection_fids:
            return
        self.fast_layer.remove_points(self.current_selection_fids)
        if self.table_widget is not None:
            keys_to_remove = [
                (self.fast_layer.id, fid) for fid in self.current_selection_fids
            ]
            self.table_widget.remove_keys(keys_to_remove)
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

        self.color_cb.blockSignals(True)
        self.color_cb.clear()
        self.color_cb.addItem("None (Uniform)")
        self.color_cb.addItems(base_columns)
        self.color_cb.blockSignals(False)

        if cli_lat in base_columns and cli_lon in base_columns:
            lat_col, lon_col, time_col = cli_lat, cli_lon, cli_time
        else:
            dialog = CsvImportDialog(base_columns, cli_lat, cli_lon, cli_time, self)
            if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                return
            lat_col, lon_col, time_col = dialog.get_selections()

        self.current_lat_col = lat_col
        self.current_lon_col = lon_col
        self.current_time_col = time_col

        self.centralWidget().setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)

        self.fast_layer.clear()
        self.chunk_list = []
        self.feature_ids = []
        self.current_selection_fids = []
        self.global_fid_counter = 0
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

    def _on_chunk_ready(self, chunk_df: pd.DataFrame) -> None:
        perf_start = time.perf_counter()
        num_rows = len(chunk_df)
        start_idx = self.global_fid_counter
        chunk_fids = [f"pt_{i}" for i in range(start_idx, start_idx + num_rows)]
        chunk_df["_fid"] = chunk_fids

        if self.current_time_col and self.current_time_col != "None":
            if pd.api.types.is_numeric_dtype(chunk_df[self.current_time_col]):
                chunk_df[self.mapped_epoch_col] = chunk_df[self.current_time_col].astype(float)
            else:
                parsed_dates = pd.to_datetime(
                    chunk_df[self.current_time_col], format="mixed", errors="coerce"
                )
                chunk_df[self.mapped_epoch_col] = parsed_dates.astype("int64") / 10**9

        coords_start = time.perf_counter()
        lats = chunk_df[self.current_lat_col].values
        lons = chunk_df[self.current_lon_col].values
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
            coords_ms=round(coords_ms, 2),
            map_add_ms=round(map_ms, 2),
            table_rows_ms=round(table_rows_ms, 2),
            table_append_ms=round(append_ms, 2),
            total_ms=round((time.perf_counter() - perf_start) * 1000.0, 2),
        )

    def _on_load_success(self, error_files: list[str]) -> None:
        if not self.chunk_list:
            self._cleanup_load_ui()
            QtWidgets.QMessageBox.warning(self, "No Data", "No valid data could be loaded.")
            return
        self.statusBar().showMessage("Finalizing UI sync...")
        self.df = pd.concat(self.chunk_list, ignore_index=True)
        self.feature_ids = np.array(self.feature_ids)
        self.fast_layer.redraw()
        self._setup_slider_and_view()
        self._cleanup_load_ui()
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
            t_min = float(self.df[self.mapped_epoch_col].min())
            t_max = float(self.df[self.mapped_epoch_col].max())
            self.slider.setEnabled(True)
            self.slider.set_range(t_min, t_max)
            if self._slider_range_conn:
                self.slider.rangeChanged.disconnect(self._slider_range_conn)
            self._slider_range_conn = self.slider.rangeChanged.connect(self.filter_by_time)

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
                # Preserve the current uniform style by clearing custom colors via IDs.
                return

            def val_to_hex(value):
                hash_int = int(hashlib.md5(str(value).encode("utf-8")).hexdigest(), 16)
                hue = (hash_int % 10000) / 10000.0
                red, green, blue = colorsys.hsv_to_rgb(hue, 0.85, 0.9)
                return f"#{int(red*255):02x}{int(green*255):02x}{int(blue*255):02x}"

            unique_vals = self.df[column_name].astype(str).unique()
            color_map = {value: val_to_hex(value) for value in unique_vals}
            color_list = self.df[column_name].astype(str).map(color_map).tolist()
            self.fast_layer.set_colors(self.feature_ids.tolist(), color_list)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def filter_by_time(self, min_val: float, max_val: float) -> None:
        if self.df is None:
            return
        mask = (self.df[self.mapped_epoch_col] >= min_val) & (
            self.df[self.mapped_epoch_col] <= max_val
        )
        visible_fids = self.df[mask]["_fid"].values.tolist()
        hidden_fids = self.df[~mask]["_fid"].values.tolist()
        self.fast_layer.hide_features(hidden_fids)
        self.fast_layer.show_features(visible_fids)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PyOpenLayersQt CSV FastPoints viewer")
    parser.add_argument("--csv", type=str, nargs="+", default=None)
    parser.add_argument("--lat", type=str, default=None)
    parser.add_argument("--lon", type=str, default=None)
    parser.add_argument("--time", type=str, default=None)
    parser.add_argument("--chunk-size", type=int, default=50_000)
    parser.add_argument("--cell-size-m", type=float, default=50_000.0)
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
