"""Reusable, configurable feature table widget for mapping applications.

This module provides a high-performance table for large feature sets using Qt's
model/view architecture (QTableView + QAbstractTableModel).

Unlike QTableWidget, this stays responsive with hundreds of thousands of rows.

Key goals:
  - Reusable across mapping backends (OpenLayers, QGIS, custom).
  - Column schema is configurable (no hard-coded column names).
  - Row objects can be any Python objects (dataclass, dict, custom class).
  - Efficient selection sync with debounced user selection signal.
  - Sortable columns with support for timestamps, numbers, and strings.

Typical usage:

    table = FeatureTableWidget(
        key_fn=lambda row: (row.layer_id, row.feature_id),
        columns=[
            ColumnSpec("Type", lambda r: r.geom_type),
            ColumnSpec("ID", lambda r: r.feature_id),
            ColumnSpec("Lat", lambda r: r.center_lat, fmt=lambda v: f"{v:.6f}"),
            ColumnSpec("Lon", lambda r: r.center_lon, fmt=lambda v: f"{v:.6f}"),
        ],
        sorting_enabled=True,  # Enable sorting (default)
    )

    table.append_rows(rows_iterable)

    # table -> map selection
    table.selectionKeysChanged.connect(on_keys)

    # map -> table selection
    table.select_keys([(layer_id, feature_id), ...])

    # Disable sorting if needed
    table.set_sorting_enabled(False)

Google-style docstrings + PEP8.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from PySide6 import QtCore
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QTableView,
    QVBoxLayout,
    QWidget,
)

FeatureKey = Tuple[str, str]  # (layer_id, feature_id)


ValueGetter = Callable[[Any], Any]
ValueSetter = Callable[[Any, Any], Any]
ValueFormatter = Callable[[Any], str]
KeyFn = Callable[[Any], FeatureKey]
ContextMenuCallback = Callable[["TableContextMenuEvent"], None]


def _perf_enabled() -> bool:
    return (
        os.environ.get("PYOPENLAYERSQT_BENCH", "") == "1"
        or os.environ.get("PYOPENLAYERSQT_PERF", "") == "1"
    )


def _perf_print(payload: dict[str, Any]) -> None:
    if _perf_enabled():
        print("PERF:", payload, flush=True)


def _perf_selection_summary(selection: QtCore.QItemSelection) -> dict[str, Any]:
    """Return cheap diagnostics for a Qt item selection payload."""
    range_count = selection.count()
    row_count = 0
    index_count = 0
    min_row: Optional[int] = None
    max_row: Optional[int] = None
    for selection_range in selection:
        top = selection_range.top()
        bottom = selection_range.bottom()
        left = selection_range.left()
        right = selection_range.right()
        rows = max(0, bottom - top + 1)
        columns = max(0, right - left + 1)
        row_count += rows
        index_count += rows * columns
        min_row = top if min_row is None else min(min_row, top)
        max_row = bottom if max_row is None else max(max_row, bottom)
    return {
        "range_count": range_count,
        "row_count": row_count,
        "index_count": index_count,
        "min_row": min_row,
        "max_row": max_row,
    }


def _selection_rows(selection: QtCore.QItemSelection) -> Iterable[int]:
    """Yield row numbers covered by a Qt item selection payload."""
    for selection_range in selection:
        yield from range(selection_range.top(), selection_range.bottom() + 1)


@dataclass(frozen=True)
class ColumnSpec:
    """Defines one column in the table."""

    name: str
    getter: ValueGetter
    fmt: Optional[ValueFormatter] = None
    tooltip: Optional[Callable[[Any], str]] = None
    sortable: bool = True
    sort_key: Optional[Callable[[Any], Any]] = None
    editable: bool = False
    setter: ValueSetter = None


@dataclass(frozen=True)
class TableContextMenuEvent:
    """Right-click context for the feature table."""

    keys: List[FeatureKey]
    row_indices: List[int]
    rows: List[Any]
    local_pos: QtCore.QPoint
    global_pos: QtCore.QPoint


@dataclass(frozen=True)
class ContextMenuActionSpec:
    """Defines one menu action and how it maps back to GUI code."""

    label: str
    callback: ContextMenuCallback
    enabled_without_selection: bool = False

class ConfigurableTableModel(QtCore.QAbstractTableModel):
    """A configurable table model for arbitrary row objects."""

    def __init__(
        self,
        columns: Sequence[ColumnSpec],
        key_fn: KeyFn,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._columns: List[ColumnSpec] = list(columns)
        self._rows: List[Any] = []
        self._key_fn: KeyFn = key_fn
        self._row_by_key: Dict[FeatureKey, int] = {}
        self._sort_column: int = -1
        self._sort_order: Qt.SortOrder = Qt.AscendingOrder
        self._hidden_keys: set[FeatureKey] = set()  # Track hidden rows
        self._external_selected_keys: set[FeatureKey] = set()
        self._visible_row_indices: Optional[List[int]] = None
        self._visible_row_by_source: Dict[int, int] = {}

    def _source_row(self, row_index: int) -> int:
        if self._visible_row_indices is None:
            return row_index
        if row_index < 0 or row_index >= len(self._visible_row_indices):
            return -1
        return self._visible_row_indices[row_index]

    def rowCount(
        self, parent: QtCore.QModelIndex = QtCore.QModelIndex()
    ) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        if self._visible_row_indices is not None:
            return len(self._visible_row_indices)
        return len(self._rows)

    def columnCount(
        self, parent: QtCore.QModelIndex = QtCore.QModelIndex()
    ) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._columns)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ) -> Optional[str]:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self._columns):
            return self._columns[section].name
        if orientation == Qt.Vertical:
            return str(section + 1)
        return None

    def data(
        self, index: QtCore.QModelIndex, role: int = Qt.DisplayRole
    ):  # noqa: ANN001
        result = None
        if not index.isValid():
            return result
        row_index = index.row()
        source_row = self._source_row(row_index)
        column_index = index.column()
        if (
            source_row < 0
            or source_row >= len(self._rows)
            or column_index < 0
            or column_index >= len(self._columns)
        ):
            return result

        row = self._rows[source_row]
        col = self._columns[column_index]

        if role in (Qt.DisplayRole, Qt.EditRole):
            try:
                value = col.getter(row)
                if col.fmt is not None:
                    try:
                        result = col.fmt(value)
                    except Exception:
                        result = str(value)
                else:
                    result = str(value)
            except Exception:
                result = ""
        elif role == Qt.ToolTipRole and col.tooltip is not None:
            try:
                result = col.tooltip(row)
            except Exception:
                result = None
        elif role == Qt.BackgroundRole and self._external_selected_keys:
            try:
                if self._key_fn(row) in self._external_selected_keys:
                    result = QColor(0, 120, 215, 80)
            except Exception:
                result = None

        return result

    def flags(self, index: QtCore.QModelIndex) -> Qt.ItemFlags:  # noqa: N802
        if not index.isValid():
            return Qt.ItemIsEnabled
        if self._columns[index.column()].editable:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def setData(self, index, value, role=Qt.EditRole):
        """Apply data from an edit to the underlying model"""
        if role == Qt.EditRole:
            source_row = self._source_row(index.row())
            if source_row < 0:
                return False
            row = self._rows[source_row]
            col = self._columns[index.column()]
            if col.setter is None:
                return False
            # update the underlying data
            col.setter(row, value)
            # emit signal to notify the view that data changed
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
            return True
        return False

    @property
    def rows(self) -> Sequence[Any]:
        return self._rows

    def set_schema(
        self, columns: Sequence[ColumnSpec], key_fn: Optional[KeyFn] = None
    ) -> None:
        """Replace column schema (and optionally key function)."""
        self.beginResetModel()
        self._columns = list(columns)
        if key_fn is not None:
            self._key_fn = key_fn
        self._row_by_key = {self._key_fn(r): i for i, r in enumerate(self._rows)}
        self._visible_row_indices = None
        self._visible_row_by_source = {}
        self.endResetModel()

    def clear(self) -> None:
        """Remove all rows."""
        self.beginResetModel()
        self._rows = []
        self._row_by_key = {}
        self._external_selected_keys = set()
        self._visible_row_indices = None
        self._visible_row_by_source = {}
        self.endResetModel()

    def append_rows(self, rows: Iterable[Any]) -> None:
        """Append many rows efficiently."""
        perf_start = time.perf_counter()
        incoming_rows = list(rows)
        if not incoming_rows:
            return

        # Filter out duplicate keys first so beginInsertRows uses the exact range.
        filter_start = time.perf_counter()
        new_rows: List[Any] = []
        for row in incoming_rows:
            key = self._key_fn(row)
            if key in self._row_by_key:
                continue
            new_rows.append(row)
        filter_ms = (time.perf_counter() - filter_start) * 1000.0

        if not new_rows:
            return

        insert_start = time.perf_counter()
        if self._visible_row_indices is not None:
            # A filtered model's view rows are not the same as source rows, so
            # source-position beginInsertRows() calls can be out of range.  Use
            # a reset while preserving the existing visible source-index map;
            # callers that want new rows visible can recompute the filter.
            self.beginResetModel()
            for row in new_rows:
                key = self._key_fn(row)
                self._row_by_key[key] = len(self._rows)
                self._rows.append(row)
            self.endResetModel()
        else:
            start = len(self._rows)
            end = start + len(new_rows) - 1
            self.beginInsertRows(QtCore.QModelIndex(), start, end)
            for row in new_rows:
                key = self._key_fn(row)
                self._row_by_key[key] = len(self._rows)
                self._rows.append(row)
            self.endInsertRows()
        _perf_print(
            {
                "side": "python",
                "operation": "feature_table_append_rows",
                "incoming_count": len(incoming_rows),
                "inserted_count": len(new_rows),
                "total_rows": len(self._rows),
                "times": {
                    "filter_ms": round(filter_ms, 2),
                    "insert_ms": round((time.perf_counter() - insert_start) * 1000.0, 2),
                    "total_ms": round((time.perf_counter() - perf_start) * 1000.0, 2),
                },
            }
        )

    def set_external_selection(self, keys: set[FeatureKey]) -> None:
        self._external_selected_keys = keys

    def remove_where(self, predicate: Callable[[Any], bool]) -> None:
        """Remove rows matching predicate (full reset)."""
        if not self._rows:
            return
        kept = [r for r in self._rows if not predicate(r)]
        self.beginResetModel()
        self._rows = kept
        self._row_by_key = {self._key_fn(r): i for i, r in enumerate(self._rows)}
        self._visible_row_indices = None
        self._visible_row_by_source = {}
        self._external_selected_keys.intersection_update(self._row_by_key)
        self.endResetModel()

    def remove_keys(self, keys: Sequence[FeatureKey]) -> None:
        """Remove rows that match any key in ``keys`` (full reset)."""
        if not self._rows or not keys:
            return

        key_set = {(str(layer_id), str(feature_id)) for layer_id, feature_id in keys}
        if not key_set:
            return

        kept = [r for r in self._rows if self._key_fn(r) not in key_set]
        if len(kept) == len(self._rows):
            return

        self.beginResetModel()
        self._rows = kept
        self._row_by_key = {self._key_fn(r): i for i, r in enumerate(self._rows)}
        self._visible_row_indices = None
        self._visible_row_by_source = {}
        self._external_selected_keys.intersection_update(self._row_by_key)
        self.endResetModel()

    def set_visible_row_indices(self, indices: Optional[Sequence[int]]) -> None:
        """Restrict displayed rows to source row indices, or clear filtering."""
        self.beginResetModel()
        if indices is None:
            self._visible_row_indices = None
            self._visible_row_by_source = {}
        else:
            max_row = len(self._rows)
            visible = [int(i) for i in indices if 0 <= int(i) < max_row]
            self._visible_row_indices = visible
            self._visible_row_by_source = {
                source_row: view_row
                for view_row, source_row in enumerate(visible)
            }
        self.endResetModel()

    def row_for_key(self, key: FeatureKey) -> Optional[int]:
        """Return row index for a key, if present."""
        source_row = self._row_by_key.get(key)
        if source_row is None:
            return None
        if self._visible_row_indices is None:
            return source_row
        return self._visible_row_by_source.get(source_row)

    def row_for(self, layer_id: str, feature_id: str) -> Optional[int]:
        """Convenience lookup by (layer_id, feature_id)."""
        return self.row_for_key((str(layer_id), str(feature_id)))

    def key_for_row(self, row_index: int) -> Optional[FeatureKey]:
        """Return the key for a given row index."""
        source_row = self._source_row(row_index)
        if source_row < 0 or source_row >= len(self._rows):
            return None
        return self._key_fn(self._rows[source_row])

    def _normalized_source_indices(
        self, indices: Optional[Sequence[int]] = None
    ) -> List[int]:
        """Return valid source row indices, or all rows when no filter is given."""
        if indices is None:
            return list(range(len(self._rows)))
        return [int(i) for i in indices if 0 <= int(i) < len(self._rows)]

    def sorted_source_indices(
        self,
        column: int,
        order: Qt.SortOrder = Qt.AscendingOrder,
        indices: Optional[Sequence[int]] = None,
    ) -> List[int]:
        """Return source row indices sorted by a column without reordering rows."""
        if column < 0 or column >= len(self._columns):
            return self._normalized_source_indices(indices)

        col_spec = self._columns[column]
        if not col_spec.sortable:
            return self._normalized_source_indices(indices)

        def make_sort_key(source_row: int) -> Any:
            try:
                value = col_spec.getter(self._rows[source_row])
                if col_spec.sort_key is not None:
                    return col_spec.sort_key(value)
                if value is None:
                    return (1, "")
                try:
                    return (0, float(value))
                except (ValueError, TypeError):
                    pass
                return (0, str(value))
            except (AttributeError, KeyError, TypeError, IndexError):
                return (1, "")

        source_rows = self._normalized_source_indices(indices)
        reverse = order == Qt.DescendingOrder
        source_rows.sort(key=make_sort_key, reverse=reverse)
        return source_rows

    def row_data(self, row_index: int) -> Optional[Any]:
        """Return the underlying row object for a given row index."""
        source_row = self._source_row(row_index)
        if source_row < 0 or source_row >= len(self._rows):
            return None
        return self._rows[source_row]

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:  # noqa: N802
        """Sort the table by the given column."""
        if column < 0 or column >= len(self._columns):
            return

        col_spec = self._columns[column]
        if not col_spec.sortable:
            return

        self._sort_column = column
        self._sort_order = order

        # Create a sort key function that handles various data types
        def make_sort_key(row: Any) -> Any:
            try:
                value = col_spec.getter(row)
                # Use custom sort_key if provided
                if col_spec.sort_key is not None:
                    return col_spec.sort_key(value)
                # Handle None values - sort them to the end
                if value is None:
                    return (1, "")
                # Try to convert to comparable types
                # For numeric strings or actual numbers
                try:
                    return (0, float(value))
                except (ValueError, TypeError):
                    pass
                # For strings (including ISO8601 timestamps)
                return (0, str(value))
            except (AttributeError, KeyError, TypeError):
                # If getter fails, sort to end
                return (1, "")

        self.layoutAboutToBeChanged.emit()

        # Store the persistent indexes before sorting
        persistent_indexes = self.persistentIndexList()
        old_rows = self._rows[:]
        visible_keys = None
        if self._visible_row_indices is not None:
            visible_keys = {
                self._key_fn(old_rows[row])
                for row in self._visible_row_indices
                if 0 <= row < len(old_rows)
            }

        # Sort the rows
        reverse = order == Qt.DescendingOrder
        self._rows.sort(key=make_sort_key, reverse=reverse)

        # Rebuild the key mapping
        self._row_by_key = {self._key_fn(r): i for i, r in enumerate(self._rows)}
        if visible_keys is not None:
            self._visible_row_indices = [
                row
                for row, item in enumerate(self._rows)
                if self._key_fn(item) in visible_keys
            ]
            self._visible_row_by_source = {
                source_row: view_row
                for view_row, source_row in enumerate(self._visible_row_indices)
            }

        # Build a reverse mapping for efficient lookup (O(n) instead of O(n²))
        # old_row_to_new_row = {id(old_rows[i]): i for i in range(len(old_rows))}
        new_row_positions = {id(self._rows[i]): i for i in range(len(self._rows))}

        # Update persistent indexes efficiently
        new_indexes = []
        for old_index in persistent_indexes:
            if not old_index.isValid():
                new_indexes.append(old_index)
                continue
            old_row = old_index.row()
            if old_row < 0 or old_row >= len(old_rows):
                new_indexes.append(old_index)
                continue
            # Find the new position of this row using the mapping
            row_obj_id = id(old_rows[old_row])
            new_row = new_row_positions.get(row_obj_id)
            if new_row is not None:
                new_indexes.append(self.index(new_row, old_index.column()))
            else:
                new_indexes.append(old_index)

        self.changePersistentIndexList(persistent_indexes, new_indexes)
        self.layoutChanged.emit()


class FeatureTableWidget(QWidget):
    """A reusable, configurable table widget."""

    selectionKeysChanged = QtCore.Signal(list)
    contextMenuRequested = QtCore.Signal(object)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        columns: Optional[Sequence[ColumnSpec]] = None,
        key_fn: Optional[KeyFn] = None,
        debounce_ms: int = 90,
        sorting_enabled: bool = True,
    ) -> None:
        super().__init__(parent)

        if key_fn is None:

            def _default_key_fn(row: Any) -> FeatureKey:
                if isinstance(row, dict):
                    return (
                        str(row.get("layer_id", "")),
                        str(row.get("feature_id", "")),
                    )
                return (
                    str(getattr(row, "layer_id", "")),
                    str(getattr(row, "feature_id", "")),
                )

            key_fn = _default_key_fn

        if columns is None:

            def _get(row: Any, attr: str) -> Any:
                if isinstance(row, dict):
                    return row.get(attr, "")
                return getattr(row, attr, "")

            columns = [
                ColumnSpec("Layer", lambda r: _get(r, "layer_kind")),
                ColumnSpec("Type", lambda r: _get(r, "geom_type")),
                ColumnSpec("Feature ID", lambda r: _get(r, "feature_id")),
                ColumnSpec(
                    "Center lat",
                    lambda r: _get(r, "center_lat"),
                    fmt=lambda v: f"{float(v):.6f}" if v != "" else "",
                ),
                ColumnSpec(
                    "Center lon",
                    lambda r: _get(r, "center_lon"),
                    fmt=lambda v: f"{float(v):.6f}" if v != "" else "",
                ),
                ColumnSpec("Layer ID", lambda r: _get(r, "layer_id")),
            ]

        self.model = ConfigurableTableModel(columns=columns, key_fn=key_fn, parent=self)

        self._building_selection = False
        self._pending_emit = False
        self._pending_emit_started_at: Optional[float] = None
        self._selection_change_sequence = 0
        self._context_menu_actions: List[ContextMenuActionSpec] = []
        self._virtual_selected_keys: set[FeatureKey] = set()
        self._virtual_selection_range_threshold = 5000

        self._debounce_timer = QtCore.QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._emit_selection_now)
        self._debounce_ms = int(debounce_ms)

        self.table = QTableView(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSortingEnabled(sorting_enabled)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultSectionSize(18)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)

        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.table.customContextMenuRequested.connect(self._on_custom_context_menu)
        self.dataChanged = self.model.dataChanged

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)

    def set_schema(
        self, columns: Sequence[ColumnSpec], key_fn: Optional[KeyFn] = None
    ) -> None:
        """Update table schema."""
        self.model.set_schema(columns=columns, key_fn=key_fn)

    def set_sorting_enabled(self, enabled: bool) -> None:
        """Enable or disable sorting on the table."""
        self.table.setSortingEnabled(enabled)

    def clear(self) -> None:
        self.model.clear()
        self.clear_selection()

    def append_rows(self, rows: Iterable[Any]) -> None:
        self.model.append_rows(rows)

    def remove_where(self, predicate: Callable[[Any], bool]) -> None:
        self.model.remove_where(predicate)
        self._filter_virtual_selection_to_model()

    def remove_keys(self, keys: Sequence[FeatureKey]) -> None:
        """Remove rows by (layer_id, feature_id) keys."""
        self.model.remove_keys(keys)
        self._filter_virtual_selection_to_model()

    def set_visible_row_indices(self, indices: Optional[Sequence[int]]) -> None:
        """Restrict the displayed rows to source row indices, or clear filtering."""
        self.model.set_visible_row_indices(indices)
        self._filter_virtual_selection_to_model()

    def row_for(self, layer_id: str, feature_id: str) -> Optional[int]:
        """Return row index for (layer_id, feature_id), if present."""
        return self.model.row_for(layer_id, feature_id)

    def row_data(self, row_index: int) -> Optional[Any]:
        """Return the underlying row object for a given row index."""
        return self.model.row_data(row_index)

    def selected_keys(self) -> List[FeatureKey]:
        """Return currently selected keys."""
        perf_start = time.perf_counter()
        if self._virtual_selected_keys:
            self._filter_virtual_selection_to_model()
            keys = list(self._virtual_selected_keys)
            _perf_print(
                {
                    "side": "python",
                    "operation": "feature_table_selected_keys",
                    "selection_count": len(keys),
                    "virtualized": True,
                    "times": {
                        "selected_rows_ms": 0.0,
                        "build_keys_ms": 0.0,
                        "total_ms": round((time.perf_counter() - perf_start) * 1000.0, 2),
                    },
                }
            )
            return keys
        sm = self.table.selectionModel()
        if sm is None:
            return []
        selected_start = time.perf_counter()
        selected_rows = sm.selectedRows(0)
        selected_rows_ms = (time.perf_counter() - selected_start) * 1000.0
        build_start = time.perf_counter()
        keys: List[FeatureKey] = []
        for idx in selected_rows:
            r = idx.row()
            if r < 0 or r >= len(self.model.rows):
                continue
            key = self.model.key_for_row(r)
            if key is not None:
                keys.append(key)
        _perf_print(
            {
                "side": "python",
                "operation": "feature_table_selected_keys",
                "selection_count": len(keys),
                "times": {
                    "selected_rows_ms": round(selected_rows_ms, 2),
                    "build_keys_ms": round((time.perf_counter() - build_start) * 1000.0, 2),
                    "total_ms": round((time.perf_counter() - perf_start) * 1000.0, 2),
                },
            }
        )
        return keys

    def _virtual_selected_row_indices(self) -> List[int]:
        rows: List[int] = []
        for key in self._virtual_selected_keys:
            row_index = self.model.row_for_key(key)
            if row_index is not None:
                rows.append(row_index)
        rows.sort()
        return rows

    def _current_selected_row_indices(self) -> List[int]:
        """Return row indices selected by either virtual or Qt selection state."""
        row_indices = set(self._virtual_selected_row_indices())
        sm = self.table.selectionModel()
        if sm is not None:
            for idx in sm.selectedRows(0):
                row = idx.row()
                if 0 <= row < len(self.model.rows):
                    row_indices.add(row)
        return sorted(row_indices)

    def _filter_virtual_selection_to_model(self) -> None:
        """Drop virtual selection keys that no longer exist in the model."""
        if not self._virtual_selected_keys:
            return
        existing_keys = {
            key
            for key in self._virtual_selected_keys
            if self.model.row_for_key(key) is not None
        }
        if existing_keys == self._virtual_selected_keys:
            return
        self._virtual_selected_keys = existing_keys
        self.model.set_external_selection(existing_keys)
        self.table.viewport().update()

    def selected_rows_data(self) -> List[Any]:
        """Return underlying row objects for all selected rows."""
        if self._virtual_selected_keys:
            return [
                row_data
                for row_index in self._virtual_selected_row_indices()
                if (row_data := self.model.row_data(row_index)) is not None
            ]

        sm = self.table.selectionModel()
        if sm is None:
            return []

        rows: List[Any] = []
        for idx in sm.selectedRows(0):
            row_data = self.model.row_data(idx.row())
            if row_data is not None:
                rows.append(row_data)
        return rows

    def set_context_menu_actions(
        self, actions: Sequence[ContextMenuActionSpec]
    ) -> None:
        """Set right-click actions shown by the built-in context menu."""
        self._context_menu_actions = list(actions)

    def clear_selection(self) -> None:
        self._virtual_selected_keys = set()
        self.model.set_external_selection(set())
        sm = self.table.selectionModel()
        if sm is None:
            return
        self._building_selection = True
        sm.clearSelection()
        self._building_selection = False
        self.table.viewport().update()

    def _select_row_indices(
        self,
        rows: List[int],
        *,
        requested_count: int,
        clear_first: bool,
        operation: str,
        perf_start: float,
        build_start: float,
    ) -> None:
        sm = self.table.selectionModel()
        if sm is None:
            return

        if not clear_first:
            current_rows = self._current_selected_row_indices()
            if current_rows:
                rows = sorted(set(rows).union(current_rows))
        rows.sort()
        matched_count = len(rows)
        selection = QtCore.QItemSelection()
        last_col = max(0, self.model.columnCount() - 1)
        range_count = 0
        if rows:
            range_start = rows[0]
            previous = rows[0]
            for row in rows[1:]:
                if row == previous + 1:
                    previous = row
                    continue
                selection.select(
                    self.model.index(range_start, 0),
                    self.model.index(previous, last_col),
                )
                range_count += 1
                range_start = row
                previous = row
            selection.select(
                self.model.index(range_start, 0),
                self.model.index(previous, last_col),
            )
            range_count += 1
        build_ms = (time.perf_counter() - build_start) * 1000.0

        self._building_selection = True
        apply_start = time.perf_counter()
        virtualized = range_count > self._virtual_selection_range_threshold
        self.table.setUpdatesEnabled(False)
        try:
            if virtualized:
                self._virtual_selected_keys = {
                    key
                    for row in rows
                    if (key := self.model.key_for_row(row)) is not None
                }
                self.model.set_external_selection(self._virtual_selected_keys)
                sm.clearSelection()
                self.table.viewport().update()
            else:
                had_virtual_selection = bool(self._virtual_selected_keys)
                self._virtual_selected_keys = set()
                self.model.set_external_selection(set())
                if clear_first or had_virtual_selection:
                    sm.clearSelection()
                sm.select(
                    selection,
                    QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows,
                )
        finally:
            self.table.setUpdatesEnabled(True)
            self._building_selection = False
        _perf_print(
            {
                "side": "python",
                "operation": operation,
                "requested_count": requested_count,
                "matched_count": matched_count,
                "range_count": range_count,
                "virtualized": virtualized,
                "clear_first": bool(clear_first),
                "times": {
                    "build_selection_ms": round(build_ms, 2),
                    "apply_selection_ms": round(
                        (time.perf_counter() - apply_start) * 1000.0, 2
                    ),
                    "total_ms": round((time.perf_counter() - perf_start) * 1000.0, 2),
                },
            }
        )

    def select_keys(self, keys: Sequence[FeatureKey], clear_first: bool = True) -> None:
        """Programmatically select rows by keys."""
        perf_start = time.perf_counter()
        build_start = time.perf_counter()
        rows = [
            row
            for key in keys
            if (row := self.model.row_for_key(key)) is not None
        ]
        self._select_row_indices(
            rows,
            requested_count=len(keys),
            clear_first=clear_first,
            operation="feature_table_select_keys",
            perf_start=perf_start,
            build_start=build_start,
        )

    def select_feature_ids(
        self, layer_id: str, feature_ids: Sequence[str], clear_first: bool = True
    ) -> None:
        """Select feature IDs for one layer using sorted continuous row ranges."""
        perf_start = time.perf_counter()
        lid = str(layer_id)
        build_start = time.perf_counter()
        rows = [
            row
            for fid in feature_ids
            if (row := self.model.row_for(lid, str(fid))) is not None
        ]
        self._select_row_indices(
            rows,
            requested_count=len(feature_ids),
            clear_first=clear_first,
            operation="feature_table_select_feature_ids",
            perf_start=perf_start,
            build_start=build_start,
        )

    def _on_selection_changed(
        self,
        selected: QtCore.QItemSelection,
        deselected: QtCore.QItemSelection,
    ) -> None:
        perf_start = time.perf_counter()
        if self._building_selection:
            if _perf_enabled():
                _perf_print(
                    {
                        "side": "python",
                        "operation": "feature_table_selection_changed_ignored",
                        "reason": "building_selection",
                        "times": {
                            "total_ms": round(
                                (time.perf_counter() - perf_start) * 1000.0, 2
                            ),
                        },
                    }
                )
            return

        self._selection_change_sequence += 1
        selected_summary = _perf_selection_summary(selected)
        deselected_summary = _perf_selection_summary(deselected)
        cleared_virtual_count = 0
        virtualized_table_selection = False
        virtualize_start = time.perf_counter()
        virtualize_ms = 0.0
        clear_virtual_start = time.perf_counter()
        if self._virtual_selected_keys:
            cleared_virtual_count = len(self._virtual_selected_keys)
            self._virtual_selected_keys = set()
            self.model.set_external_selection(set())
            self.table.viewport().update()
        clear_virtual_ms = (time.perf_counter() - clear_virtual_start) * 1000.0

        if selected_summary["row_count"] > self._virtual_selection_range_threshold:
            virtualized_table_selection = True
            self._virtual_selected_keys = {
                key
                for row in _selection_rows(selected)
                if (key := self.model.key_for_row(row)) is not None
            }
            self.model.set_external_selection(self._virtual_selected_keys)
            self._building_selection = True
            self.table.setUpdatesEnabled(False)
            try:
                sm = self.table.selectionModel()
                if sm is not None:
                    sm.clearSelection()
            finally:
                self.table.setUpdatesEnabled(True)
                self._building_selection = False
            self.table.viewport().update()
            virtualize_ms = (time.perf_counter() - virtualize_start) * 1000.0

        self._pending_emit = True
        self._pending_emit_started_at = time.perf_counter()
        self._debounce_timer.start(self._debounce_ms)
        if _perf_enabled():
            _perf_print(
                {
                    "side": "python",
                    "operation": "feature_table_selection_changed",
                    "sequence": self._selection_change_sequence,
                    "selected": selected_summary,
                    "deselected": deselected_summary,
                    "cleared_virtual_count": cleared_virtual_count,
                    "virtualized_table_selection": virtualized_table_selection,
                    "virtual_selection_count": len(self._virtual_selected_keys),
                    "debounce_ms": self._debounce_ms,
                    "times": {
                        "clear_virtual_ms": round(clear_virtual_ms, 2),
                        "virtualize_ms": round(virtualize_ms, 2),
                        "handler_ms": round(
                            (time.perf_counter() - perf_start) * 1000.0, 2
                        ),
                    },
                }
            )

    def _emit_selection_now(self) -> None:
        if not self._pending_emit:
            return
        perf_start = time.perf_counter()
        pending_age_ms = None
        if self._pending_emit_started_at is not None:
            pending_age_ms = (perf_start - self._pending_emit_started_at) * 1000.0
        self._pending_emit = False
        self._pending_emit_started_at = None
        selected_keys_start = time.perf_counter()
        keys = self.selected_keys()
        selected_keys_ms = (time.perf_counter() - selected_keys_start) * 1000.0
        emit_start = time.perf_counter()
        self.selectionKeysChanged.emit(keys)
        _perf_print(
            {
                "side": "python",
                "operation": "feature_table_emit_selection",
                "sequence": self._selection_change_sequence,
                "selection_count": len(keys),
                "pending_age_ms": (
                    round(pending_age_ms, 2) if pending_age_ms is not None else None
                ),
                "times": {
                    "selected_keys_ms": round(selected_keys_ms, 2),
                    "signal_emit_ms": round(
                        (time.perf_counter() - emit_start) * 1000.0, 2
                    ),
                    "total_ms": round((time.perf_counter() - perf_start) * 1000.0, 2),
                },
            }
        )

    def hide_rows_by_keys(self, keys: Sequence[FeatureKey]) -> None:
        """Hide rows by their keys (rows remain in model but are not displayed)."""
        for key in keys:
            row_idx = self.model.row_for_key(key)
            if row_idx is not None:
                self.table.setRowHidden(row_idx, True)
        self.model._hidden_keys.update(keys)

    def show_rows_by_keys(self, keys: Sequence[FeatureKey]) -> None:
        """Show previously hidden rows by their keys."""
        for key in keys:
            row_idx = self.model.row_for_key(key)
            if row_idx is not None:
                self.table.setRowHidden(row_idx, False)
        self.model._hidden_keys.difference_update(keys)

    def show_all_rows(self) -> None:
        """Show all hidden rows (reset any filtering)."""
        for i in range(len(self.model.rows)):
            self.table.setRowHidden(i, False)
        self.model._hidden_keys.clear()

    def is_row_hidden(self, row_index: int) -> bool:
        """Check if a row is hidden."""
        return self.table.isRowHidden(row_index)

    def _on_custom_context_menu(self, pos: QtCore.QPoint) -> None:
        index = self.table.indexAt(pos)
        sm = self.table.selectionModel()
        if sm is None:
            return

        if index.isValid():
            clicked_key = self.model.key_for_row(index.row())
            clicked_is_virtual = (
                clicked_key is not None and clicked_key in self._virtual_selected_keys
            )
            if not clicked_is_virtual and not sm.isRowSelected(
                index.row(), QtCore.QModelIndex()
            ):
                self.table.selectRow(index.row())

        if self._virtual_selected_keys:
            selected_row_indices = self._virtual_selected_row_indices()
        else:
            selected_row_indices = [idx.row() for idx in sm.selectedRows(0)]

        keys = [
            key
            for row_idx in selected_row_indices
            if (key := self.model.key_for_row(row_idx)) is not None
        ]
        rows = [
            row
            for row_idx in selected_row_indices
            if (row := self.model.row_data(row_idx)) is not None
        ]

        event = TableContextMenuEvent(
            keys=keys,
            row_indices=selected_row_indices,
            rows=rows,
            local_pos=QtCore.QPoint(pos),
            global_pos=self.table.viewport().mapToGlobal(pos),
        )
        self.contextMenuRequested.emit(event)

        if not self._context_menu_actions:
            return

        menu = QMenu(self)
        has_selection = bool(event.keys)
        for action_spec in self._context_menu_actions:
            action = menu.addAction(action_spec.label)
            action.setEnabled(has_selection or action_spec.enabled_without_selection)
            action.triggered.connect(
                lambda _checked=False, callback=action_spec.callback: callback(event)
            )
        menu.exec(event.global_pos)
