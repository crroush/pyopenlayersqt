#!/usr/bin/env python3
"""Manual CSV FastPoints viewer for profiling streaming load and selection.

This console app mirrors the large-CSV workflow used while investigating
FastPoints selection performance and prints PERF lines when
PYOPENLAYERSQT_PERF=1.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import os
import re
import sys
import time
from typing import Sequence

import numpy as np
from matplotlib.colors import hsv_to_rgb
from PySide6 import QtCore, QtGui, QtWidgets

from pyopenlayersqt import (
    FastGeoPointsStyle,
    FastPointsStyle,
    OLMapWidget,
    RangeSliderWidget,
    WMSOptions,
)
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


def _category_codes_to_packed_rgba(codes: np.ndarray) -> np.ndarray:
    """Map integer category codes to deterministic high-cardinality RGBA colors."""
    code_arr = np.asarray(codes)
    missing_mask = code_arr.astype(np.int64, copy=False) < 0
    code_u32 = np.where(missing_mask, 0, code_arr).astype(np.uint32, copy=False)

    # Turbo is excellent for ordered scalar data, but categorical columns with
    # thousands of values need a much larger apparent palette.  Mix the integer
    # codes through multiplicative hashes, then use the mixed bits as HSV hue,
    # saturation and value.  That spreads neighboring categories across the full
    # 24-bit RGB space instead of walking a single gradient ramp.
    hue_bits = code_u32 * np.uint32(2654435761)
    sat_bits = code_u32 * np.uint32(2246822519)
    val_bits = code_u32 * np.uint32(3266489917)
    hsv = np.empty((len(code_u32), 3), dtype=np.float32)
    hsv[:, 0] = hue_bits.astype(np.float32) / np.float32(2**32)
    hsv[:, 1] = 0.62 + (((sat_bits >> np.uint32(29)) & np.uint32(7)) / 7.0) * 0.33
    hsv[:, 2] = 0.74 + (((val_bits >> np.uint32(29)) & np.uint32(7)) / 7.0) * 0.23

    rgb = np.rint(hsv_to_rgb(hsv) * 255).astype(np.uint32)
    packed = (
        (rgb[:, 0] << np.uint32(24))
        | (rgb[:, 1] << np.uint32(16))
        | (rgb[:, 2] << np.uint32(8))
        | np.uint32(255)
    )
    packed[missing_mask] = np.uint32(0x999999FF)
    return packed.astype(np.uint32, copy=False)


class _OffsetLineIterator:
    """Decode binary CSV lines while tracking each logical record start offset.

    ``csv.reader`` can consume several physical lines for one logical CSV row
    when quoted fields contain embedded newlines.  The loader stores byte
    offsets so the table/export path can reread original rows lazily; those
    offsets must point at logical records rather than every physical line.
    """

    def __init__(self, fh):
        self._fh = fh
        self.record_start: int | None = None

    def __iter__(self):
        return self

    def __next__(self) -> str:
        offset = self._fh.tell()
        line = self._fh.readline()
        if not line:
            raise StopIteration
        if self.record_start is None:
            self.record_start = offset
        return line.decode("utf-8-sig")

    def consume_record_start(self) -> int:
        """Return and clear the byte offset for the last parsed CSV record."""
        if self.record_start is None:
            return self._fh.tell()
        offset = self.record_start
        self.record_start = None
        return offset


def _read_csv_header(path: str) -> list[str]:
    """Read the first CSV row without pulling in a dataframe dependency."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return next(csv.reader(fh))


def _parse_datetime_array(values: np.ndarray) -> np.ndarray:
    """Convert mixed common datetime strings to Unix epoch seconds."""
    fallback_formats = (
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%y %H:%M",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%y %I:%M:%S %p",
        "%m/%d/%y %I:%M %p",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y/%m/%d",
        "%Y-%m-%d",
    )
    out = np.full(values.shape, np.nan, dtype=np.float64)
    for index, value in enumerate(values.astype(str, copy=False)):
        text = value.strip()
        if not text:
            continue
        normalized = text.replace("Z", "+00:00")
        dt: datetime | None = None
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            for fmt in fallback_formats:
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        out[index] = dt.astimezone(timezone.utc).timestamp()
    return out


def _to_float_array(values: np.ndarray) -> np.ndarray:
    """Convert a string/object array to float, coercing invalid values to NaN."""
    out = np.empty(values.shape, dtype=np.float64)
    for index, value in enumerate(values):
        try:
            out[index] = float(value)
        except (TypeError, ValueError):
            out[index] = np.nan
    return out


def _factorize_values(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return integer category codes and unique values for arbitrary CSV values."""
    unique_values, codes = np.unique(
        values.astype(str, copy=False), return_inverse=True
    )
    return codes.astype(np.int64, copy=False), unique_values


def _numeric_aware_sort_values(values: np.ndarray) -> tuple[np.ndarray, bool]:
    """Return sortable values, using numeric order when cells are numeric.

    CSV values are strings, but cached table sorting should still match the old
    dataframe behavior for numeric columns.  If every non-empty value parses as
    a finite float, the returned array sorts numerically; otherwise it falls
    back to text sorting.
    """
    text_values = values.astype(str, copy=False)
    numeric_values = _to_float_array(text_values)
    non_empty = np.char.strip(text_values) != ""
    if np.all(np.isfinite(numeric_values[non_empty])):
        sort_values = numeric_values.copy()
        sort_values[~np.isfinite(sort_values)] = np.inf
        return sort_values, True
    return text_values, False


class CsvColumnIndex:
    """Compact categorical index for one CSV column.

    The CSV app uses these indexes for color-by, keyword filtering, and large
    sortable tables.  One uint32 code per row plus the unique value list is far
    smaller than keeping every raw string cell in memory for multi-million-row
    CSVs.
    """

    def __init__(self) -> None:
        self._code_by_value: dict[str, int] = {}
        self._unique_values: list[str] = []
        self._code_chunks: list[np.ndarray] = []
        self.codes: np.ndarray | None = None
        self.unique_values: np.ndarray = np.empty(0, dtype=str)
        self._sort_cache: dict[bool, np.ndarray] = {}

    def add_values(self, values: np.ndarray) -> None:
        """Add a loaded CSV chunk to the index."""
        if self.codes is not None and not self._code_by_value:
            # Appending another file after an index was finalized means the
            # lookup dictionary has been dropped.  Rebuild it from unique
            # values so appended chunks reuse existing category codes.
            self._code_by_value = {
                str(value): index for index, value in enumerate(self._unique_values)
            }
        self._sort_cache = {}
        chunk_uniques, inverse = np.unique(
            values.astype(str, copy=False), return_inverse=True
        )
        mapped_codes = np.empty(len(chunk_uniques), dtype=np.uint32)
        for unique_index, value in enumerate(chunk_uniques):
            text = str(value)
            code = self._code_by_value.get(text)
            if code is None:
                code = len(self._unique_values)
                self._code_by_value[text] = code
                self._unique_values.append(text)
            mapped_codes[unique_index] = code
        self._code_chunks.append(mapped_codes[inverse].astype(np.uint32, copy=False))

    def finalize(self) -> None:
        """Merge pending chunk codes into a row-aligned code array."""
        code_chunks = []
        if self.codes is not None:
            code_chunks.append(self.codes)
        code_chunks.extend(self._code_chunks)
        self.codes = (
            np.concatenate(code_chunks).astype(np.uint32, copy=False)
            if code_chunks
            else np.empty(0, dtype=np.uint32)
        )
        self.unique_values = np.asarray(self._unique_values, dtype=str)
        self._code_chunks = []
        self._code_by_value = {}

    def sorted_indices(self, descending: bool = False) -> np.ndarray:
        """Return source row indices ordered by this indexed column."""
        cached = self._sort_cache.get(descending)
        if cached is not None:
            return cached
        if self.codes is None:
            self.finalize()
        if self.unique_values.size:
            unique_sort_values, _is_numeric = _numeric_aware_sort_values(
                self.unique_values
            )
            sorted_codes = np.argsort(unique_sort_values, kind="stable")
            rank_by_code = np.empty_like(sorted_codes)
            rank_by_code[sorted_codes] = np.arange(
                len(sorted_codes), dtype=sorted_codes.dtype
            )
            sort_values = rank_by_code[self.codes]
        else:
            sort_values = self.codes
        indices = np.argsort(sort_values, kind="stable").astype(np.uint32, copy=False)
        if descending:
            indices = indices[::-1].copy()
        self._sort_cache[descending] = indices
        return indices


class CsvTable:
    """Small column-oriented table for CSV data used by csv_plotter.

    Loaded chunks keep only derived columns (coordinates, ids, parsed time) in
    memory. Original CSV cell values are read lazily from source file offsets
    when the table view, keyword filtering, color-by, or export needs them.
    """

    def __init__(
        self,
        columns: Sequence[str],
        data: np.ndarray | None = None,
        source_paths: Sequence[str] | None = None,
        source_offsets: np.ndarray | None = None,
    ):
        self._columns = list(columns)
        self._data = None if data is None else np.asarray(data)
        self._source_paths = list(source_paths or [])
        self._source_offsets = (
            np.asarray(source_offsets, dtype=np.uint64)
            if source_offsets is not None
            else np.empty(0, dtype=np.uint64)
        )
        self._extra_columns: dict[str, np.ndarray] = {}
        self._column_indexes: dict[str, CsvColumnIndex] = {}
        self._layer_id = ""

    @property
    def columns(self) -> list[str]:
        return [*self._columns, *self._extra_columns]

    def __len__(self) -> int:
        if self._data is not None:
            return int(self._data.shape[0])
        if self._extra_columns:
            return len(next(iter(self._extra_columns.values())))
        return int(self._source_offsets.shape[0])

    def __contains__(self, column: str) -> bool:
        return column in self._columns or column in self._extra_columns

    def __getitem__(self, column: str) -> np.ndarray:
        """Return a full column from memory or the source CSV file."""
        if column in self._extra_columns:
            return self._extra_columns[column]
        if self._data is not None:
            return self._data[:, self._columns.index(column)]
        return self._read_source_column(column)

    def __setitem__(self, column: str, values: Sequence[object] | np.ndarray) -> None:
        arr = np.asarray(values)
        if column in self._extra_columns:
            self._extra_columns[column] = arr
        elif self._data is not None and column in self._columns:
            self._data[:, self._columns.index(column)] = arr
        else:
            self._extra_columns[column] = arr

    def get_cell(self, row_index: int, column: str, default: object = None) -> object:
        """Return one table cell for the virtual FeatureTable provider."""
        if column in self._extra_columns:
            return self._extra_columns[column][row_index]
        if self._data is not None:
            return self._data[row_index, self._columns.index(column)]
        try:
            return self._read_source_row(row_index)[self._columns.index(column)]
        except (IndexError, ValueError):
            return default

    def filtered(self, mask: np.ndarray) -> "CsvTable":
        """Return a source-backed table containing only rows selected by mask."""
        filtered = CsvTable(
            self._columns,
            None if self._data is None else self._data[mask].copy(),
            self._source_paths,
            self._source_offsets[mask].copy(),
        )
        filtered._extra_columns = {
            key: values[mask].copy() for key, values in self._extra_columns.items()
        }
        return filtered

    @classmethod
    def from_source_rows(
        cls, columns: Sequence[str], source_path: str, offsets: np.ndarray
    ) -> "CsvTable":
        return cls(columns, None, [source_path], offsets)

    @classmethod
    def concat(cls, chunks: Sequence["CsvTable"]) -> "CsvTable":
        """Concatenate loaded chunks without materializing raw CSV strings."""
        if not chunks:
            return cls([], np.empty((0, 0), dtype=str))
        if all(chunk._data is not None for chunk in chunks):
            data = np.vstack([chunk._data for chunk in chunks])
        else:
            data = None
        paths: list[str] = []
        offsets: list[np.ndarray] = []
        for chunk in chunks:
            path_base = len(paths)
            paths.extend(chunk._source_paths)
            if chunk._source_offsets.size:
                if len(chunk._source_paths) != 1:
                    offsets.append(chunk._source_offsets)
                else:
                    # Single-file chunks store only byte offsets while loading.
                    # Final concatenated tables need [file_id, offset] pairs so
                    # lazy row reads can seek into the correct source file.
                    file_ids = np.full(len(chunk), path_base, dtype=np.uint32)
                    offsets.append(
                        np.column_stack((file_ids, chunk._source_offsets)).astype(
                            np.uint64, copy=False
                        )
                    )
        source_offsets = np.vstack(offsets) if offsets else None
        table = cls(chunks[0]._columns, data, paths, source_offsets)
        extra_keys = set().union(*(chunk._extra_columns.keys() for chunk in chunks))
        table._extra_columns = {
            key: np.concatenate([chunk._extra_columns[key] for chunk in chunks])
            for key in extra_keys
        }
        return table

    def set_column_indexes(self, indexes: dict[str, CsvColumnIndex]) -> None:
        self._column_indexes = indexes

    def factorized_column(self, column: str) -> tuple[np.ndarray, np.ndarray, bool]:
        """Return categorical row codes and unique values for a column."""
        index = self._column_indexes.get(column)
        if index is not None:
            if index.codes is None:
                index.finalize()
            return index.codes, index.unique_values, True
        codes, unique_values = _factorize_values(self[column])
        return codes, unique_values, False

    def sorted_source_indices(
        self,
        column: str,
        descending: bool = False,
        indices: Sequence[int] | np.ndarray | None = None,
    ) -> list[int]:
        """Return provider source rows sorted by a column.

        The feature table calls this when the user clicks a sortable header.
        Indexed columns use cached row-code ordering; non-indexed columns fall
        back to reading the requested values and sorting them directly.
        """
        index = self._column_indexes.get(column)
        if index is None:
            values = self[column]
            source_indices = (
                np.arange(len(self), dtype=np.uint32)
                if indices is None
                else np.asarray(indices, dtype=np.uint32)
            )
            sort_values, _is_numeric = _numeric_aware_sort_values(
                values[source_indices]
            )
            order = np.argsort(sort_values, kind="stable")
            if descending:
                order = order[::-1]
            return source_indices[order].astype(np.uint32, copy=False).tolist()

        sorted_indices = index.sorted_indices(descending)
        if indices is not None:
            visible = np.zeros(len(self), dtype=bool)
            visible[np.asarray(indices, dtype=np.uint32)] = True
            sorted_indices = sorted_indices[visible[sorted_indices]]
        return sorted_indices.astype(np.uint32, copy=False).tolist()

    def set_layer_id(self, layer_id: str) -> None:
        self._layer_id = str(layer_id)

    def row_count(self) -> int:
        return len(self)

    def data(self, source_row: int, _column: int, column_spec: ColumnSpec) -> object:
        return self.get_cell(source_row, column_spec.name, "")

    def key(self, source_row: int) -> tuple[str, str]:
        return (self._layer_id, f"pt_{source_row}")

    def row_for_key(self, key: tuple[str, str]) -> int | None:
        """Resolve a FeatureTable/Map feature key back to a provider row."""
        layer_id, feature_id = key
        if self._layer_id and str(layer_id) != self._layer_id:
            return None
        if not str(feature_id).startswith("pt_"):
            return None
        try:
            row = int(str(feature_id)[3:])
        except ValueError:
            return None
        if 0 <= row < len(self):
            return row
        return None

    def row_data(self, source_row: int) -> dict[str, object]:
        row = {
            column: self.get_cell(source_row, column, "") for column in self._columns
        }
        row.update({"_layer_id": self._layer_id, "_feature_id": f"pt_{source_row}"})
        return row

    def write_csv(self, path: str, excluded_columns: set[str] | None = None) -> None:
        """Write original CSV columns for selected/exported rows."""
        excluded_columns = excluded_columns or set()
        columns = [column for column in self._columns if column not in excluded_columns]
        column_indices = [self._columns.index(col) for col in columns]
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(columns)
            if self._data is not None:
                writer.writerows(self._data[:, column_indices])
            else:
                for row_index in range(len(self)):
                    row = self._read_source_row(row_index)
                    writer.writerow(
                        [
                            row[index] if index < len(row) else ""
                            for index in column_indices
                        ]
                    )

    def _read_source_column(self, column: str) -> np.ndarray:
        """Read one CSV column in source-row order without reopening per row."""
        column_index = self._columns.index(column)
        values = np.empty(len(self), dtype=object)
        row_index = 0
        while row_index < len(self):
            # Rows can come from multiple appended CSV files.  Process all
            # contiguous rows for the same source file with one open handle so
            # full-column operations avoid millions of open/close calls.
            if self._source_offsets.ndim == 2:
                file_id = int(self._source_offsets[row_index, 0])
            else:
                file_id = 0

            with open(self._source_paths[file_id], "rb") as fh:
                while row_index < len(self):
                    if self._source_offsets.ndim == 2:
                        next_file_id = int(self._source_offsets[row_index, 0])
                        offset = int(self._source_offsets[row_index, 1])
                    else:
                        next_file_id = 0
                        offset = int(self._source_offsets[row_index])
                    if next_file_id != file_id:
                        break

                    fh.seek(offset)
                    row = next(csv.reader(_OffsetLineIterator(fh)))
                    values[row_index] = (
                        row[column_index] if column_index < len(row) else ""
                    )
                    row_index += 1
                    if row_index and row_index % 50_000 == 0:
                        QtWidgets.QApplication.processEvents()
        return values

    def _read_source_row(self, row_index: int) -> list[str]:
        """Reread one original CSV record for table display or export."""
        if self._source_offsets.ndim == 2:
            file_id = int(self._source_offsets[row_index, 0])
            offset = int(self._source_offsets[row_index, 1])
        else:
            file_id = 0
            offset = int(self._source_offsets[row_index])
        with open(self._source_paths[file_id], "rb") as fh:
            fh.seek(offset)
            return next(csv.reader(_OffsetLineIterator(fh)))


def perf_enabled() -> bool:
    return os.environ.get("PYOPENLAYERSQT_PERF", "") == "1"


def perf(message: str, **fields: object) -> None:
    if not perf_enabled():
        return
    suffix = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"PERF: app {message}" + (f" {suffix}" if suffix else ""), flush=True)


class CsvLoaderThread(QtCore.QThread):
    """Background thread that streams raw CSV chunks to the GUI thread.

    The thread performs file I/O and CSV tokenization only.  The GUI thread owns
    Qt objects, map layer updates, coordinate coercion, and table-provider
    compaction in ``_on_chunk_ready``.
    """

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
                    if _read_csv_header(path) != self.base_columns:
                        error_files.append(file_name)
                        bytes_finished += file_size
                        self.progress_update.emit(
                            min(int((bytes_finished / total_bytes) * 100), 100)
                        )
                        continue

                    with open(path, "rb") as fh:
                        # Skip the header row here; the GUI thread already read
                        # it to configure columns.  Keep the file in binary mode
                        # so byte offsets remain seekable after csv.reader
                        # consumes records.
                        fh.readline()
                        line_iter = _OffsetLineIterator(fh)
                        reader = csv.reader(line_iter)
                        while True:
                            offsets: list[int] = []
                            rows: list[list[str]] = []
                            for _ in range(self.chunk_size):
                                try:
                                    row = next(reader)
                                except StopIteration:
                                    break
                                offset = line_iter.consume_record_start()
                                if not row:
                                    continue
                                if len(row) < len(self.base_columns):
                                    # pandas.read_csv tolerated omitted
                                    # trailing optional cells.  Preserve that
                                    # behavior by padding them as empty strings.
                                    row = [
                                        *row,
                                        *([""] * (len(self.base_columns) - len(row))),
                                    ]
                                elif len(row) > len(self.base_columns):
                                    raise ValueError(
                                        "CSV row has unexpected column count"
                                    )
                                offsets.append(offset)
                                rows.append(row)
                            if not rows:
                                break
                            data = np.asarray(rows, dtype=str)
                            if data.ndim == 1:
                                data = data.reshape(1, -1)
                            chunk = CsvTable(
                                self.base_columns,
                                data,
                                source_paths=[path],
                                source_offsets=np.asarray(offsets, dtype=np.uint64),
                            )
                            self.chunk_ready.emit(chunk)
                            current_bytes = bytes_finished + fh.tell()
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
        default_sma: str | None = None,
        default_smi: str | None = None,
        default_tilt: str | None = None,
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

        self.sma_cb = QtWidgets.QComboBox()
        self.sma_cb.addItem("None")
        self.sma_cb.addItems(columns)
        self._set_default(self.sma_cb, default_sma, [])

        self.smi_cb = QtWidgets.QComboBox()
        self.smi_cb.addItem("None")
        self.smi_cb.addItems(columns)
        self._set_default(self.smi_cb, default_smi, [])

        self.tilt_cb = QtWidgets.QComboBox()
        self.tilt_cb.addItem("None")
        self.tilt_cb.addItems(columns)
        self._set_default(self.tilt_cb, default_tilt, [])

        layout.addRow("Latitude Column:", self.lat_cb)
        layout.addRow("Longitude Column:", self.lon_cb)
        layout.addRow("Time Column:", self.time_cb)
        layout.addRow("SMA Column:", self.sma_cb)
        layout.addRow("SMI Column:", self.smi_cb)
        layout.addRow("Tilt Column:", self.tilt_cb)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_default(
        self,
        combo_box: QtWidgets.QComboBox,
        explicit_default: str | None,
        auto_matches: list[str],
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

    def get_selections(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.lat_cb.currentText(),
            self.lon_cb.currentText(),
            self.time_cb.currentText(),
            self.sma_cb.currentText(),
            self.smi_cb.currentText(),
            self.tilt_cb.currentText(),
        )


class PyOpenLayersCsvApp(QtWidgets.QMainWindow):
    def __init__(self, cli_args: argparse.Namespace):
        super().__init__()
        self.setWindowTitle("CSV Viewer")
        self.resize(1200, 800)
        self.cli_args = cli_args

        self.df: CsvTable | None = None
        self.chunk_list: list[CsvTable] = []
        self._column_indexers: dict[str, CsvColumnIndex] = {}
        self.global_fid_counter = 0
        self.current_lat_col: str | None = None
        self.current_lon_col: str | None = None
        self.current_time_col: str | None = None
        self.current_sma_col: str | None = None
        self.current_smi_col: str | None = None
        self.current_tilt_col: str | None = None
        self._using_ellipses = False
        self._ellipses_visible = True
        self._osm_visible = True
        self._osm_url = self.cli_args.osm_url
        self._osm_opacity = float(self.cli_args.osm_opacity)
        self._wms_url = self.cli_args.wms_url
        self._wms_layers = self.cli_args.wms_layers
        self._wms_opacity = float(self.cli_args.wms_opacity)
        self._wms_visible = bool(self._wms_url)
        self._dark_mode = True
        self._map_background_color = "#0f172a"
        self._countries_visible = True
        self._country_stroke_color = "#64748b"
        self._default_palette = QtWidgets.QApplication.palette()
        self.wms_layer = None
        self.mapped_epoch_col = "_slider_epoch_time"
        self.feature_ids: list[str] | np.ndarray = []
        self._visible_mask: np.ndarray | None = None
        self._deleted_mask: np.ndarray | None = None
        self._keyword_mask: np.ndarray | None = None
        self._keyword_filter: tuple[str, str] | None = None
        self._append_prior_row_count = 0
        self._append_prior_visible_mask: np.ndarray | None = None
        self._append_prior_deleted_mask: np.ndarray | None = None
        self._append_prior_keyword_filter: tuple[str, str] | None = None
        self.current_selection_fids: list[str] = []
        self.table_widget: FeatureTableWidget | None = None
        self._map_selection_conn = None
        self._slider_range_conn = None
        self._table_sort_column: int | None = None
        self._table_sort_order = QtCore.Qt.SortOrder.AscendingOrder
        self._pending_time_filter: tuple[float, float] | None = None
        self._time_filter_range: tuple[float, float] | None = None
        self._last_chunk_redraw_time = 0.0
        self._csv_load_started_at: float | None = None
        self._time_filter_timer = QtCore.QTimer(self)
        self._time_filter_timer.setSingleShot(True)
        self._time_filter_timer.setInterval(50)
        self._time_filter_timer.timeout.connect(self._apply_pending_time_filter)
        self._pending_cli_csv: (
            tuple[
                Sequence[str] | str,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
            ]
            | None
        ) = None

        self._apply_qt_dark_mode(self._dark_mode)
        self._setup_ui()
        if self.cli_args.csv:
            self._pending_cli_csv = (
                self.cli_args.csv,
                self.cli_args.lat,
                self.cli_args.lon,
                self.cli_args.time,
                self.cli_args.sma,
                self.cli_args.smi,
                self.cli_args.tilt,
            )
            self.map_widget.ready.connect(self._process_pending_cli_csv)
            QtCore.QTimer.singleShot(0, self._process_pending_cli_csv)

    def _apply_qt_dark_mode(self, enabled: bool) -> None:
        """Apply or restore the global Qt application palette."""
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        if not enabled:
            app.setPalette(self._default_palette)
            return
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#111827"))
        palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#e5e7eb"))
        palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#0f172a"))
        palette.setColor(
            QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#1f2937")
        )
        palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor("#111827"))
        palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor("#e5e7eb"))
        palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("#e5e7eb"))
        palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#1f2937"))
        palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#e5e7eb"))
        palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor("#ffffff"))
        palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#2563eb"))
        palette.setColor(
            QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff")
        )
        app.setPalette(palette)

    def _set_global_dark_mode(self, enabled: bool) -> None:
        """Set both the Qt GUI palette and map colors for dark/light mode."""
        self._dark_mode = bool(enabled)
        self._apply_qt_dark_mode(self._dark_mode)
        if self._dark_mode:
            self._map_background_color = "#0f172a"
            self._country_stroke_color = "#64748b"
        else:
            self._map_background_color = "#ffffff"
            self._country_stroke_color = "#334155"
        if hasattr(self, "map_widget"):
            self.map_widget.set_map_background_color(self._map_background_color)
            if self._countries_visible:
                self.map_widget.set_country_boundaries_visible(
                    True, self._country_stroke_color
                )

    def _process_pending_cli_csv(self) -> None:
        if self._pending_cli_csv is None:
            return
        if not getattr(self.map_widget, "_js_ready", False):
            return
        paths, lat_col, lon_col, time_col, sma_col, smi_col, tilt_col = (
            self._pending_cli_csv
        )
        self._pending_cli_csv = None
        self.process_csv(paths, lat_col, lon_col, time_col, sma_col, smi_col, tilt_col)

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

        self.map_widget = OLMapWidget(
            center=(0, 0),
            zoom=2,
            show_osm_layer=self._osm_visible,
            osm_url=self._osm_url,
            map_background_color=self._map_background_color,
            show_country_boundaries=self._countries_visible,
            country_boundaries_stroke_color=self._country_stroke_color,
        )
        self.map_widget.set_base_opacity(self._osm_opacity)
        self.map_widget.set_map_background_color(self._map_background_color)
        self.map_widget.set_base_visible(self._osm_visible)
        self.map_widget.set_country_boundaries_visible(
            self._countries_visible, self._country_stroke_color
        )
        self.map_widget.perfReceived.connect(
            lambda payload: perf("bridge_event", payload=payload)
        )
        map_layout.addWidget(self.map_widget, stretch=1)
        self._apply_wms_settings(show_errors=False)

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

        map_menu = self.menuBar().addMenu("Map")
        self.dark_mode_action = QtGui.QAction("Dark Mode", self)
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.setChecked(self._dark_mode)
        self.dark_mode_action.triggered.connect(self.toggle_dark_mode)
        map_menu.addAction(self.dark_mode_action)
        map_menu.addSeparator()

        layer_settings_action = QtGui.QAction("Base/WMS Settings...", self)
        layer_settings_action.triggered.connect(self.open_layer_settings_dialog)
        map_menu.addAction(layer_settings_action)
        map_menu.addSeparator()

        self.osm_visible_action = QtGui.QAction("Show OSM/XYZ Base", self)
        self.osm_visible_action.setCheckable(True)
        self.osm_visible_action.setChecked(self._osm_visible)
        self.osm_visible_action.triggered.connect(self.toggle_osm_layer)
        map_menu.addAction(self.osm_visible_action)

        self.wms_visible_action = QtGui.QAction("Show WMS Overlay", self)
        self.wms_visible_action.setCheckable(True)
        self.wms_visible_action.setChecked(self._wms_visible)
        self.wms_visible_action.triggered.connect(self.toggle_wms_layer)
        map_menu.addAction(self.wms_visible_action)

        self.countries_visible_action = QtGui.QAction("Show Countries", self)
        self.countries_visible_action.setCheckable(True)
        self.countries_visible_action.setChecked(self._countries_visible)
        self.countries_visible_action.triggered.connect(self.toggle_country_boundaries)
        map_menu.addAction(self.countries_visible_action)

        country_color_action = QtGui.QAction("Country Stroke Color...", self)
        country_color_action.triggered.connect(self.choose_country_stroke_color)
        map_menu.addAction(country_color_action)

        background_color_action = QtGui.QAction("Background Color...", self)
        background_color_action.triggered.connect(self.choose_background_color)
        map_menu.addAction(background_color_action)
        map_menu.addSeparator()

        self.ellipses_action = QtGui.QAction("Show Ellipses", self)
        self.ellipses_action.setCheckable(True)
        self.ellipses_action.setChecked(True)
        self.ellipses_action.triggered.connect(self.toggle_ellipses)
        map_menu.addAction(self.ellipses_action)

        selection_menu = self.menuBar().addMenu("Selection")
        show_only_selected_action = QtGui.QAction("Show Only Selected", self)
        show_only_selected_action.triggered.connect(self.show_only_selected_features)
        hide_selected_action = QtGui.QAction("Hide Selected", self)
        hide_selected_action.triggered.connect(self.hide_selected_features)
        show_all_action = QtGui.QAction("Show All", self)
        show_all_action.triggered.connect(self.show_all_features)
        selection_menu.addAction(show_only_selected_action)
        selection_menu.addAction(hide_selected_action)
        selection_menu.addAction(show_all_action)

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
        self._column_indexers = {}
        self.feature_ids = []
        self._visible_mask = None
        self._deleted_mask = None
        self._keyword_mask = None
        self._keyword_filter = None
        self._append_prior_row_count = 0
        self._append_prior_visible_mask = None
        self._append_prior_deleted_mask = None
        self._append_prior_keyword_filter = None
        self.current_selection_fids = []
        self._last_chunk_redraw_time = 0.0
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

    def _apply_wms_settings(self, show_errors: bool = True) -> None:
        """Create/update/remove the optional WMS overlay from stored settings."""
        url = (self._wms_url or "").strip()
        layers = (self._wms_layers or "").strip()
        if not self._wms_visible or not url:
            if self.wms_layer is not None:
                self.wms_layer.remove()
                self.wms_layer = None
            return
        if not layers:
            if self.wms_layer is not None:
                self.wms_layer.remove()
                self.wms_layer = None
            if show_errors:
                QtWidgets.QMessageBox.warning(
                    self, "Missing WMS Layers", "Please provide WMS layer name(s)."
                )
            return
        params = {"LAYERS": layers, "TILED": True}
        if self.wms_layer is not None:
            self.wms_layer.remove()
        self.wms_layer = self.map_widget.add_wms(
            WMSOptions(url=url, params=params, opacity=self._wms_opacity),
            name="WMS Overlay",
        )

    def open_layer_settings_dialog(self) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Base/WMS Settings")
        dialog.setMinimumWidth(780)
        if self._dark_mode:
            dialog.setStyleSheet("""
                QDialog, QWidget {
                    background-color: #111827;
                    color: #e5e7eb;
                }
                QLineEdit {
                    background-color: #0f172a;
                    border: 1px solid #64748b;
                    border-radius: 4px;
                    color: #f8fafc;
                    padding: 5px 7px;
                    selection-background-color: #2563eb;
                    selection-color: #ffffff;
                }
                QLineEdit:focus {
                    border: 1px solid #93c5fd;
                }
                QPushButton {
                    background-color: #1f2937;
                    border: 1px solid #64748b;
                    border-radius: 4px;
                    color: #e5e7eb;
                    padding: 5px 10px;
                }
                QPushButton:hover {
                    background-color: #374151;
                }
                QCheckBox, QLabel {
                    color: #e5e7eb;
                }
                QSlider::groove:horizontal {
                    background: #334155;
                    border-radius: 3px;
                    height: 6px;
                }
                QSlider::sub-page:horizontal {
                    background: #2563eb;
                    border-radius: 3px;
                    height: 6px;
                }
                QSlider::handle:horizontal {
                    background: #e5e7eb;
                    border: 1px solid #93c5fd;
                    border-radius: 7px;
                    margin: -5px 0;
                    width: 14px;
                }
                """)
        form = QtWidgets.QFormLayout(dialog)
        form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )

        def configure_url_edit(edit: QtWidgets.QLineEdit) -> None:
            """Make long OSM/WMS URLs easier to inspect and edit."""
            edit.setMinimumWidth(620)
            edit.setClearButtonEnabled(True)
            edit.setPlaceholderText("https://...")

        def opacity_slider(value: float) -> tuple[QtWidgets.QWidget, QtWidgets.QSlider]:
            """Return a slider row for opacity and keep a percentage label updated."""
            row = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setSingleStep(5)
            slider.setPageStep(10)
            slider.setValue(int(round(max(0.0, min(1.0, value)) * 100)))
            label = QtWidgets.QLabel(f"{slider.value()}%")
            label.setMinimumWidth(42)
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            slider.valueChanged.connect(
                lambda new_value: label.setText(f"{new_value}%")
            )
            layout.addWidget(slider, 1)
            layout.addWidget(label)
            return row, slider

        osm_visible = QtWidgets.QCheckBox("Show OSM/XYZ base layer")
        osm_visible.setChecked(self._osm_visible)
        osm_url_edit = QtWidgets.QLineEdit(self._osm_url or "")
        configure_url_edit(osm_url_edit)
        osm_opacity_row, osm_opacity_slider = opacity_slider(self._osm_opacity)

        wms_visible = QtWidgets.QCheckBox("Show WMS overlay")
        wms_visible.setChecked(self._wms_visible)
        wms_url_edit = QtWidgets.QLineEdit(self._wms_url or "")
        configure_url_edit(wms_url_edit)
        wms_layers_edit = QtWidgets.QLineEdit(self._wms_layers or "")
        configure_url_edit(wms_layers_edit)
        wms_layers_edit.setPlaceholderText("layer_a,layer_b")
        wms_opacity_row, wms_opacity_slider = opacity_slider(self._wms_opacity)

        original_osm_opacity = self._osm_opacity
        original_wms_opacity = self._wms_opacity

        def apply_osm_opacity(value: int) -> None:
            """Preview OSM/XYZ opacity as the user moves the slider."""
            self.map_widget.set_base_opacity(value / 100.0)

        def apply_wms_opacity(value: int) -> None:
            """Preview WMS opacity as the user moves the slider."""
            if self.wms_layer is not None:
                self.wms_layer.set_opacity(value / 100.0)

        osm_opacity_slider.valueChanged.connect(apply_osm_opacity)
        wms_opacity_slider.valueChanged.connect(apply_wms_opacity)

        background_edit = QtWidgets.QLineEdit(self._map_background_color)
        background_edit.setMinimumWidth(180)
        background_button = QtWidgets.QPushButton("Pick...")

        def pick_background_color() -> None:
            current = QtGui.QColor(background_edit.text().strip() or "#0f172a")
            picked = QtWidgets.QColorDialog.getColor(
                current, dialog, "Map background color"
            )
            if picked.isValid():
                background_edit.setText(picked.name())

        background_button.clicked.connect(pick_background_color)
        background_row = QtWidgets.QWidget()
        background_layout = QtWidgets.QHBoxLayout(background_row)
        background_layout.setContentsMargins(0, 0, 0, 0)
        background_layout.addWidget(background_edit)
        background_layout.addWidget(background_button)

        countries_visible = QtWidgets.QCheckBox("Show country boundaries")
        countries_visible.setChecked(self._countries_visible)
        country_stroke_edit = QtWidgets.QLineEdit(self._country_stroke_color)
        country_stroke_edit.setMinimumWidth(180)
        country_stroke_button = QtWidgets.QPushButton("Pick...")

        def pick_country_stroke_color() -> None:
            current = QtGui.QColor(country_stroke_edit.text().strip() or "#334155")
            picked = QtWidgets.QColorDialog.getColor(
                current, dialog, "Country boundary stroke color"
            )
            if picked.isValid():
                country_stroke_edit.setText(picked.name())

        country_stroke_button.clicked.connect(pick_country_stroke_color)
        country_stroke_row = QtWidgets.QWidget()
        country_stroke_layout = QtWidgets.QHBoxLayout(country_stroke_row)
        country_stroke_layout.setContentsMargins(0, 0, 0, 0)
        country_stroke_layout.addWidget(country_stroke_edit)
        country_stroke_layout.addWidget(country_stroke_button)

        form.addRow(osm_visible)
        form.addRow("OSM/XYZ URL:", osm_url_edit)
        form.addRow("OSM opacity:", osm_opacity_row)
        form.addRow(wms_visible)
        form.addRow("WMS URL:", wms_url_edit)
        form.addRow("WMS layer(s):", wms_layers_edit)
        form.addRow("WMS opacity:", wms_opacity_row)
        form.addRow("Map background color:", background_row)
        form.addRow(countries_visible)
        form.addRow("Country stroke color:", country_stroke_row)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addWidget(buttons)

        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            self.map_widget.set_base_opacity(original_osm_opacity)
            if self.wms_layer is not None:
                self.wms_layer.set_opacity(original_wms_opacity)
            return
        self._osm_visible = osm_visible.isChecked()
        self._osm_url = osm_url_edit.text().strip() or None
        self._osm_opacity = osm_opacity_slider.value() / 100.0
        self._wms_visible = wms_visible.isChecked()
        self._wms_url = wms_url_edit.text().strip() or None
        self._wms_layers = wms_layers_edit.text().strip() or None
        self._wms_opacity = wms_opacity_slider.value() / 100.0
        self._map_background_color = background_edit.text().strip() or "#0f172a"
        self._countries_visible = countries_visible.isChecked()
        self._country_stroke_color = country_stroke_edit.text().strip() or "#334155"
        self.map_widget.set_base_url(self._osm_url)
        self.map_widget.set_base_visible(self._osm_visible)
        self.map_widget.set_base_opacity(self._osm_opacity)
        self.map_widget.set_map_background_color(self._map_background_color)
        self._apply_wms_settings()
        if self._wms_visible and (not self._wms_url or not self._wms_layers):
            self._wms_visible = False
        self.map_widget.set_country_boundaries_visible(
            self._countries_visible, self._country_stroke_color
        )
        self._sync_map_menu_actions()

    def _sync_map_menu_actions(self) -> None:
        """Keep checkable Map menu actions aligned with layer state."""
        self.dark_mode_action.setChecked(self._dark_mode)
        self.osm_visible_action.setChecked(self._osm_visible)
        self.wms_visible_action.setChecked(self._wms_visible)
        self.countries_visible_action.setChecked(self._countries_visible)

    def toggle_dark_mode(self, checked: bool) -> None:
        """Toggle global dark mode for both Qt widgets and the map."""
        self._set_global_dark_mode(bool(checked))
        self._sync_map_menu_actions()

    def toggle_osm_layer(self, checked: bool) -> None:
        """Toggle the OSM/XYZ base layer from the Map menu."""
        self._osm_visible = bool(checked)
        self.map_widget.set_base_visible(self._osm_visible)

    def toggle_wms_layer(self, checked: bool) -> None:
        """Toggle the optional WMS overlay from the Map menu."""
        self._wms_visible = bool(checked)
        self._apply_wms_settings(show_errors=checked)
        if self._wms_visible and (not self._wms_url or not self._wms_layers):
            self._wms_visible = False
        self._sync_map_menu_actions()

    def toggle_country_boundaries(self, checked: bool) -> None:
        """Toggle bundled country boundaries from the Map menu."""
        self._countries_visible = bool(checked)
        self.map_widget.set_country_boundaries_visible(
            self._countries_visible, self._country_stroke_color
        )

    def choose_country_stroke_color(self) -> None:
        """Pick and apply the country boundary stroke color from the Map menu."""
        current = QtGui.QColor(self._country_stroke_color or "#334155")
        picked = QtWidgets.QColorDialog.getColor(
            current, self, "Country boundary stroke color"
        )
        if not picked.isValid():
            return
        self._country_stroke_color = picked.name()
        if self._countries_visible:
            self.map_widget.set_country_boundaries_visible(
                True, self._country_stroke_color
            )

    def choose_background_color(self) -> None:
        """Pick and apply the overall map background color from the Map menu."""
        current = QtGui.QColor(self._map_background_color or "#0f172a")
        picked = QtWidgets.QColorDialog.getColor(current, self, "Map background color")
        if not picked.isValid():
            return
        self._map_background_color = picked.name()
        self.map_widget.set_map_background_color(self._map_background_color)

    def toggle_ellipses(self, checked: bool) -> None:
        self._ellipses_visible = bool(checked)
        if self._using_ellipses:
            self.fast_layer.set_ellipses_visible(self._ellipses_visible)

    def show_only_selected_features(self) -> None:
        indices = self._feature_ids_to_row_indices(self.current_selection_fids)
        if indices.size:
            if self.df is not None:
                self._visible_mask = np.zeros(len(self.df), dtype=bool)
                self._visible_mask[indices] = True
            self.fast_layer.show_only_indices(indices)
            self._sync_table_visible_rows()

    def hide_selected_features(self) -> None:
        indices = self._feature_ids_to_row_indices(self.current_selection_fids)
        if indices.size:
            if self.df is not None:
                if self._visible_mask is None or len(self._visible_mask) != len(
                    self.df
                ):
                    self._visible_mask = np.ones(len(self.df), dtype=bool)
                self._visible_mask[indices] = False
            self.fast_layer.hide_indices(indices)
            self._sync_table_visible_rows()

    def show_all_features(self) -> None:
        if self.df is not None:
            self._visible_mask = np.ones(len(self.df), dtype=bool)
        self.fast_layer.show_all_features()
        self._sync_table_visible_rows()

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
                self,
                "No Selection",
                "Please select points on the map or in the table first.",
            )
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Selected Data", "", "CSV Files (*.csv)"
        )
        if not path:
            return
        selected = set(self.current_selection_fids)
        mask = np.fromiter((fid in selected for fid in self.df["_fid"]), dtype=bool)
        export_table = self.df.filtered(mask)
        export_table.write_csv(path, excluded_columns={"_fid", self.mapped_epoch_col})
        QtWidgets.QMessageBox.information(
            self,
            "Success",
            f"Successfully saved {len(export_table)} records to:\n{path}",
        )

    def load_csv_from_menu(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Open CSV Data", "", "CSV Files (*.csv)"
        )
        if paths:
            self.process_csv(paths)

    def _configure_point_layer(
        self,
        sma_col: str | None,
        smi_col: str | None,
        tilt_col: str | None,
    ) -> None:
        """Switch between FastPoints and FastGeoPoints based on ellipse columns."""
        sma_col = None if sma_col in (None, "", "None") else sma_col
        smi_col = None if smi_col in (None, "", "None") else smi_col
        tilt_col = None if tilt_col in (None, "", "None") else tilt_col
        use_ellipses = bool(sma_col and smi_col and tilt_col)
        if use_ellipses == self._using_ellipses:
            self.current_sma_col = sma_col
            self.current_smi_col = smi_col
            self.current_tilt_col = tilt_col
            return

        self.fast_layer.remove()
        if use_ellipses:
            self.fast_layer = self.map_widget.add_fast_geopoints_layer(
                name="Data Points",
                selectable=True,
                style=FastGeoPointsStyle(default_color="steelblue", point_radius=3),
                cell_size_m=self.cli_args.cell_size_m,
                show_ellipses=self._ellipses_visible,
            )
        else:
            self.fast_layer = self.map_widget.add_fast_points_layer(
                name="Data Points",
                selectable=True,
                style=FastPointsStyle(default_color="steelblue", radius=3),
                cell_size_m=self.cli_args.cell_size_m,
            )
        self._using_ellipses = use_ellipses
        self.current_sma_col = sma_col
        self.current_smi_col = smi_col
        self.current_tilt_col = tilt_col

    def process_csv(
        self,
        paths: str | Sequence[str],
        cli_lat: str | None = None,
        cli_lon: str | None = None,
        cli_time: str | None = None,
        cli_sma: str | None = None,
        cli_smi: str | None = None,
        cli_tilt: str | None = None,
    ) -> None:
        """Start a CSV load or append flow after validating schema/mappings."""
        if isinstance(paths, str):
            paths = [paths]
        if not paths:
            return

        first_file = paths[0]
        base_columns = _read_csv_header(first_file)
        # File > Open appends to the current dataset when the schema matches.
        # If it does not match, bail out before clearing the current map/table.
        if self.df is not None and list(self.df._columns) != list(base_columns):
            QtWidgets.QMessageBox.warning(
                self,
                "Schema Mismatch",
                (
                    "The selected CSV columns do not match the currently loaded "
                    "data, so the existing data was left unchanged."
                ),
            )
            return

        mismatched_files = [
            os.path.basename(path)
            for path in paths[1:]
            if _read_csv_header(path) != base_columns
        ]
        if mismatched_files:
            preserved_text = (
                "the existing data was left unchanged"
                if self.df is not None
                else "nothing was loaded"
            )
            QtWidgets.QMessageBox.warning(
                self,
                "Schema Mismatch",
                (
                    "The selected CSV files do not all have the same columns, so "
                    f"{preserved_text}.\n\n" + "\n".join(mismatched_files)
                ),
            )
            return

        append_to_existing = self.df is not None
        if append_to_existing:
            # Appended files must use the same coordinate/time/ellipse mapping
            # as the existing dataset; otherwise old and new rows would be
            # interpreted differently inside one layer/table provider.
            lat_col = self.current_lat_col
            lon_col = self.current_lon_col
            time_col = self.current_time_col
            sma_col = self.current_sma_col
            smi_col = self.current_smi_col
            tilt_col = self.current_tilt_col
        else:
            cli_time_valid = cli_time in (None, "", "None") or cli_time in base_columns
            cli_ellipse_values = (cli_sma, cli_smi, cli_tilt)
            cli_ellipse_empty = all(
                value in (None, "", "None") for value in cli_ellipse_values
            )
            cli_ellipse_valid = cli_ellipse_empty or all(
                value in base_columns for value in cli_ellipse_values
            )
            if (
                cli_lat in base_columns
                and cli_lon in base_columns
                and cli_time_valid
                and cli_ellipse_valid
            ):
                lat_col, lon_col, time_col = cli_lat, cli_lon, cli_time
                sma_col, smi_col, tilt_col = cli_sma, cli_smi, cli_tilt
            else:
                dialog = CsvImportDialog(
                    base_columns,
                    cli_lat,
                    cli_lon,
                    cli_time,
                    cli_sma,
                    cli_smi,
                    cli_tilt,
                    self,
                )
                if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                    return
                lat_col, lon_col, time_col, sma_col, smi_col, tilt_col = (
                    dialog.get_selections()
                )

        self.current_lat_col = lat_col
        self.current_lon_col = lon_col
        self.current_time_col = time_col
        if not append_to_existing:
            self._configure_point_layer(sma_col, smi_col, tilt_col)
            self._configure_column_controls(base_columns)

        self.centralWidget().setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)

        self._last_chunk_redraw_time = time.perf_counter()
        if append_to_existing:
            self._append_prior_row_count = len(self.df)
            self._append_prior_visible_mask = (
                self._visible_mask.copy()
                if self._visible_mask is not None
                and len(self._visible_mask) == self._append_prior_row_count
                else None
            )
            self._append_prior_deleted_mask = (
                self._deleted_mask.copy()
                if self._deleted_mask is not None
                and len(self._deleted_mask) == self._append_prior_row_count
                else None
            )
            self._append_prior_keyword_filter = self._keyword_filter
            # Successful loads store feature_ids as an ndarray for compactness.
            # Convert back to a list while streaming appended chunks so
            # _on_chunk_ready can extend it cheaply.
            if not isinstance(self.feature_ids, list):
                self.feature_ids = list(self.feature_ids)
            if not self._column_indexers:
                self._column_indexers = {
                    column: CsvColumnIndex() for column in base_columns
                }
        else:
            self._append_prior_row_count = 0
            self._append_prior_visible_mask = None
            self._append_prior_deleted_mask = None
            self._append_prior_keyword_filter = None
            self.fast_layer.clear()
            self._reset_loaded_data_state()
            self._last_chunk_redraw_time = time.perf_counter()
            self._column_indexers = {
                column: CsvColumnIndex() for column in base_columns
            }
            self._initialize_empty_table(base_columns)

        self.loader_thread = CsvLoaderThread(
            paths, base_columns, self.cli_args.chunk_size
        )
        self.loader_thread.chunk_ready.connect(self._on_chunk_ready)
        self.loader_thread.progress_update.connect(self.progress_bar.setValue)
        self.loader_thread.status_update.connect(self.statusBar().showMessage)
        self.loader_thread.finished_success.connect(self._on_load_success)
        self.loader_thread.finished_error.connect(self._on_load_error)
        self._csv_load_started_at = time.perf_counter()
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
            if self._using_ellipses:
                self.map_widget.set_fast_geopoints_selection(self.fast_layer.id, fids)
            else:
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

        self._map_selection_conn = self.map_widget.selectionChanged.connect(
            on_map_selection
        )

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
        if (
            self._table_sort_column == column
            and self._table_sort_order == QtCore.Qt.SortOrder.AscendingOrder
        ):
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

    def _on_chunk_ready(self, chunk_df: CsvTable) -> None:
        """Convert one raw CSV chunk into map arrays and provider metadata."""
        perf_start = time.perf_counter()
        incoming_rows = len(chunk_df)

        if self.current_time_col and self.current_time_col != "None":
            # Numeric epoch values should stay numeric.  Only cells that fail
            # numeric parsing fall back to mixed datetime string parsing.
            raw_time_values = chunk_df[self.current_time_col]
            numeric_times = _to_float_array(raw_time_values)
            invalid_numeric = ~np.isfinite(numeric_times)
            if np.any(invalid_numeric):
                parsed_times = _parse_datetime_array(raw_time_values)
                numeric_times[invalid_numeric] = parsed_times[invalid_numeric]
            chunk_df[self.mapped_epoch_col] = numeric_times

        coords_start = time.perf_counter()
        lats = _to_float_array(chunk_df[self.current_lat_col])
        lons = _to_float_array(chunk_df[self.current_lon_col])
        valid_coords = np.isfinite(lats) & np.isfinite(lons)
        skipped_invalid_coords = int(incoming_rows - np.count_nonzero(valid_coords))
        ellipse_values = None
        if self._using_ellipses:
            # Ellipse arrays are kept parallel to lat/lon.  If coordinate
            # filtering removes a row, the ellipse row must be removed too.
            sma_values = _to_float_array(chunk_df[self.current_sma_col])
            smi_values = _to_float_array(chunk_df[self.current_smi_col])
            tilt_values = _to_float_array(chunk_df[self.current_tilt_col])
            ellipse_values = (sma_values, smi_values, tilt_values)
        if skipped_invalid_coords:
            chunk_df = chunk_df.filtered(valid_coords)
            lats = lats[valid_coords]
            lons = lons[valid_coords]
            if ellipse_values is not None:
                ellipse_values = tuple(
                    values[valid_coords] for values in ellipse_values
                )
        num_rows = len(chunk_df)
        if num_rows == 0:
            perf(
                "chunk_ready_skipped",
                rows=incoming_rows,
                skipped_invalid_coords=skipped_invalid_coords,
            )
            return

        index_start = time.perf_counter()
        for column, indexer in self._column_indexers.items():
            # Index while raw cells are still in memory.  After this point the
            # retained chunk is compacted to source offsets plus derived arrays.
            indexer.add_values(chunk_df[column])
        index_ms = (time.perf_counter() - index_start) * 1000.0

        source_paths = chunk_df._source_paths
        source_offsets = chunk_df._source_offsets
        epoch_values = (
            chunk_df[self.mapped_epoch_col]
            if self.mapped_epoch_col in chunk_df.columns
            else None
        )
        chunk_df = CsvTable(
            chunk_df._columns,
            data=None,
            source_paths=source_paths,
            source_offsets=source_offsets,
        )
        # Retained chunks keep map-critical arrays in memory and lazily reread
        # other CSV cells from the source file when the table/export path needs
        # them.  This keeps large CSV loads from storing all raw strings twice.
        chunk_df[self.current_lat_col] = lats
        chunk_df[self.current_lon_col] = lons
        if epoch_values is not None:
            chunk_df[self.mapped_epoch_col] = epoch_values
        start_idx = self.global_fid_counter
        chunk_fids = [f"pt_{i}" for i in range(start_idx, start_idx + num_rows)]
        chunk_df["_fid"] = chunk_fids
        coords = np.column_stack((lats, lons))
        coords_ms = (time.perf_counter() - coords_start) * 1000.0

        map_start = time.perf_counter()
        if ellipse_values is not None:
            sma_values, smi_values, tilt_values = ellipse_values
            self.fast_layer.add_points_with_ellipses(
                coords=coords,
                sma_m=sma_values,
                smi_m=smi_values,
                tilt_deg=tilt_values,
                ids=chunk_fids,
                redraw=False,
            )
        else:
            self.fast_layer.add_points(coords=coords, ids=chunk_fids, redraw=False)
        now = time.perf_counter()
        redraw_requested = False
        if now - self._last_chunk_redraw_time >= 0.75:
            self.fast_layer.redraw()
            self._last_chunk_redraw_time = now
            redraw_requested = True
        map_ms = (time.perf_counter() - map_start) * 1000.0

        table_rows_ms = 0.0
        append_ms = 0.0

        self.chunk_list.append(chunk_df)
        self.feature_ids.extend(chunk_fids)
        self.global_fid_counter += num_rows
        perf(
            "chunk_ready",
            rows=num_rows,
            incoming_rows=incoming_rows,
            skipped_invalid_coords=skipped_invalid_coords,
            index_ms=round(index_ms, 2),
            coords_ms=round(coords_ms, 2),
            map_add_ms=round(map_ms, 2),
            redraw_requested=redraw_requested,
            table_rows_ms=round(table_rows_ms, 2),
            table_append_ms=round(append_ms, 2),
            total_ms=round((time.perf_counter() - perf_start) * 1000.0, 2),
        )

    def _on_load_success(self, error_files: list[str]) -> None:
        if not self.chunk_list:
            elapsed_s = self._elapsed_csv_load_seconds()
            self._reset_loaded_data_state()
            self._cleanup_load_ui()
            QtWidgets.QMessageBox.warning(
                self, "No Data", "No valid data could be loaded."
            )
            self.statusBar().showMessage(f"No valid data loaded in {elapsed_s:.2f}s.")
            return
        self.statusBar().showMessage("Finalizing UI sync...")
        self.df = CsvTable.concat(self.chunk_list)
        index_start = time.perf_counter()
        for indexer in self._column_indexers.values():
            indexer.finalize()
        self.df.set_column_indexes(self._column_indexers)
        perf(
            "column_indexes_finalized",
            column_count=len(self._column_indexers),
            elapsed_ms=round((time.perf_counter() - index_start) * 1000.0, 2),
        )
        self.df.set_layer_id(self.fast_layer.id)
        self.feature_ids = np.array(self.feature_ids)
        if self.table_widget is not None:
            self.table_widget.set_row_provider(self.df)
        append_row_count = self._append_prior_row_count
        appended_rows = max(0, len(self.df) - append_row_count)
        appended_to_existing = append_row_count > 0
        if appended_to_existing:
            old_visible = (
                self._append_prior_visible_mask
                if self._append_prior_visible_mask is not None
                and len(self._append_prior_visible_mask) == append_row_count
                else np.ones(append_row_count, dtype=bool)
            )
            old_deleted = (
                self._append_prior_deleted_mask
                if self._append_prior_deleted_mask is not None
                and len(self._append_prior_deleted_mask) == append_row_count
                else np.zeros(append_row_count, dtype=bool)
            )
            self._visible_mask = np.concatenate(
                [old_visible, np.ones(appended_rows, dtype=bool)]
            )
            self._deleted_mask = np.concatenate(
                [old_deleted, np.zeros(appended_rows, dtype=bool)]
            )
            self._keyword_filter = self._append_prior_keyword_filter
            if self._keyword_filter is not None:
                column_name, pattern = self._keyword_filter
                self._keyword_mask = self._build_keyword_mask(column_name, pattern)
            else:
                self._keyword_mask = None
            self._apply_visibility_mask(
                self._visible_mask & self._combined_filter_mask(),
                "append_preserve_visibility",
                appended_rows=appended_rows,
            )
        else:
            self._visible_mask = np.ones(len(self.df), dtype=bool)
            self._deleted_mask = np.zeros(len(self.df), dtype=bool)
            self._keyword_mask = None
            self._keyword_filter = None
        self._append_prior_row_count = 0
        self._append_prior_visible_mask = None
        self._append_prior_deleted_mask = None
        self._append_prior_keyword_filter = None
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
                    "and were skipped:\n\n" + "\n".join(error_files)
                ),
            )
        elapsed_s = self._elapsed_csv_load_seconds()
        self.statusBar().showMessage(
            f"Successfully loaded {len(self.df):,} points in {elapsed_s:.2f}s.",
            10000,
        )
        perf(
            "csv_load_complete",
            rows=len(self.df),
            elapsed_ms=round(elapsed_s * 1000.0, 2),
        )

    def _on_load_error(self, error_msg: str) -> None:
        elapsed_s = self._elapsed_csv_load_seconds()
        self._reset_loaded_data_state()
        self._cleanup_load_ui()
        QtWidgets.QMessageBox.critical(self, "Error Loading Data", error_msg)
        self.statusBar().showMessage(f"Load failed after {elapsed_s:.2f}s.")

    def _elapsed_csv_load_seconds(self) -> float:
        if self._csv_load_started_at is None:
            return 0.0
        elapsed_s = time.perf_counter() - self._csv_load_started_at
        self._csv_load_started_at = None
        return elapsed_s

    def _cleanup_load_ui(self) -> None:
        QtWidgets.QApplication.restoreOverrideCursor()
        self.progress_bar.setVisible(False)
        self.centralWidget().setEnabled(True)

    def _setup_slider_and_view(self) -> None:
        if self.df is None:
            return
        if self.current_time_col != "None" and self.mapped_epoch_col in self.df.columns:
            time_values = self.df[self.mapped_epoch_col]
            valid_times = time_values[np.isfinite(time_values)]
            if valid_times.size == 0:
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

        lats = _to_float_array(self.df[self.current_lat_col])
        lons = _to_float_array(self.df[self.current_lon_col])
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

            stage_start = time.perf_counter()
            codes, unique_values, used_cached_index = self.df.factorized_column(
                column_name
            )
            factorize_ms = (time.perf_counter() - stage_start) * 1000.0

            stage_start = time.perf_counter()
            packed_colors = _category_codes_to_packed_rgba(codes)
            color_map_ms = (time.perf_counter() - stage_start) * 1000.0

            stage_start = time.perf_counter()
            self.fast_layer.set_all_packed_colors(packed_colors)
            send_ms = (time.perf_counter() - stage_start) * 1000.0
            perf(
                "color_by",
                column=column_name,
                category_count=len(unique_values),
                row_count=len(codes),
                cached_index=used_cached_index,
                factorize_ms=round(factorize_ms, 2),
                color_map_ms=round(color_map_ms, 2),
                send_ms=round(send_ms, 2),
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
        return [term.strip() for term in re.split(r"\s+or\s+", pattern) if term.strip()]

    def _match_keyword_values(self, values: np.ndarray, pattern: str) -> np.ndarray:
        """Return which unique values match a keyword/wildcard expression."""
        text_values = np.char.lower(values.astype(str, copy=False))
        mask = np.zeros(len(text_values), dtype=bool)
        for term in self._keyword_terms(pattern):
            lowered = term.lower()
            if any(char in lowered for char in "*?"):
                regex = re.compile(_wildcard_term_to_regex(lowered))
                term_mask = np.fromiter(
                    (bool(regex.match(str(value))) for value in text_values),
                    dtype=bool,
                    count=len(text_values),
                )
            else:
                term_mask = np.char.find(text_values, lowered) >= 0
            mask |= term_mask
        return mask

    def _build_keyword_mask(self, column_name: str, pattern: str) -> np.ndarray:
        """Return rows whose selected column matches the keyword expression."""
        if self.df is None:
            return np.empty(0, dtype=bool)
        if column_name not in self.df.columns:
            return np.zeros(len(self.df), dtype=bool)
        # Match against unique values and expand through row codes.  This avoids
        # rereading millions of source CSV strings for each keyword filter.
        codes, unique_values, _used_cached_index = self.df.factorized_column(
            column_name
        )
        if len(codes) != len(self.df):
            return np.zeros(len(self.df), dtype=bool)
        unique_matches = self._match_keyword_values(unique_values, pattern)
        return unique_matches[codes]

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
            time_values = self.df[self.mapped_epoch_col].astype(float, copy=False)
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

        # Compute only the transition from the previous mask to the new mask so
        # JS receives a compact hide/show update instead of a full row list for
        # every filter change.
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
    parser.add_argument("--sma", type=str, default=None)
    parser.add_argument("--smi", type=str, default=None)
    parser.add_argument("--tilt", type=str, default=None)
    parser.add_argument("--osm-url", type=str, default=None)
    parser.add_argument("--osm-opacity", type=float, default=1.0)
    parser.add_argument("--wms-url", type=str, default=None)
    parser.add_argument("--wms-layers", type=str, default=None)
    parser.add_argument("--wms-opacity", type=float, default=1.0)
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
