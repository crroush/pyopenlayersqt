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
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from PySide6 import QtCore
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableView,
    QVBoxLayout,
    QWidget,
)

FeatureKey = Tuple[str, str]  # (layer_id, feature_id)


ValueGetter = Callable[[Any], Any]
ValueSetter = Callable[[Any, Any], Any]
ValueFormatter = Callable[[Any], str]
KeyFn = Callable[[Any], FeatureKey]


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

    def rowCount(
        self, parent: QtCore.QModelIndex = QtCore.QModelIndex()
    ) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

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
        if not index.isValid():
            return None
        r = index.row()
        c = index.column()
        if r < 0 or r >= len(self._rows) or c < 0 or c >= len(self._columns):
            return None

        row = self._rows[r]
        col = self._columns[c]

        if role in (Qt.DisplayRole, Qt.EditRole):
            try:
                value = col.getter(row)
            except Exception:
                return ""
            if col.fmt is not None:
                try:
                    return col.fmt(value)
                except Exception:
                    return str(value)
            return str(value)

        if role == Qt.ToolTipRole and col.tooltip is not None:
            try:
                return col.tooltip(row)
            except Exception:
                return None

        return None

    def flags(self, index: QtCore.QModelIndex) -> Qt.ItemFlags:  # noqa: N802
        if not index.isValid():
            return Qt.ItemIsEnabled
        if self._columns[index.column()].editable:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def setData(self, index, value, role=Qt.EditRole):
        """Apply data from an edit to the underlying model"""
        if role == Qt.EditRole:
            row = self._rows[index.row()]
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
        self.endResetModel()

    def clear(self) -> None:
        """Remove all rows."""
        self.beginResetModel()
        self._rows = []
        self._row_by_key = {}
        self.endResetModel()

    def append_rows(self, rows: Iterable[Any]) -> None:
        """Append many rows efficiently."""
        new_rows = list(rows)
        if not new_rows:
            return
        start = len(self._rows)
        end = start + len(new_rows) - 1
        self.beginInsertRows(QtCore.QModelIndex(), start, end)
        for r in new_rows:
            k = self._key_fn(r)
            if k in self._row_by_key:
                continue
            self._row_by_key[k] = len(self._rows)
            self._rows.append(r)
        self.endInsertRows()

    def remove_where(self, predicate: Callable[[Any], bool]) -> None:
        """Remove rows matching predicate (full reset)."""
        if not self._rows:
            return
        kept = [r for r in self._rows if not predicate(r)]
        self.beginResetModel()
        self._rows = kept
        self._row_by_key = {self._key_fn(r): i for i, r in enumerate(self._rows)}
        self.endResetModel()

    def row_for_key(self, key: FeatureKey) -> Optional[int]:
        """Return row index for a key, if present."""
        return self._row_by_key.get(key)

    def row_for(self, layer_id: str, feature_id: str) -> Optional[int]:
        """Convenience lookup by (layer_id, feature_id)."""
        return self.row_for_key((str(layer_id), str(feature_id)))

    def key_for_row(self, row_index: int) -> Optional[FeatureKey]:
        """Return the key for a given row index."""
        if row_index < 0 or row_index >= len(self._rows):
            return None
        return self._key_fn(self._rows[row_index])

    def row_data(self, row_index: int) -> Optional[Any]:
        """Return the underlying row object for a given row index."""
        if row_index < 0 or row_index >= len(self._rows):
            return None
        return self._rows[row_index]

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

        # Sort the rows
        reverse = order == Qt.DescendingOrder
        self._rows.sort(key=make_sort_key, reverse=reverse)

        # Rebuild the key mapping
        self._row_by_key = {self._key_fn(r): i for i, r in enumerate(self._rows)}

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
        
        # Performance optimizations for large datasets
        self.table.setUniformRowHeights(True)  # Assume all rows same height
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)  # Smoother scrolling
        
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultSectionSize(18)

        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
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

    def append_rows(self, rows: Iterable[Any]) -> None:
        self.model.append_rows(rows)

    def remove_where(self, predicate: Callable[[Any], bool]) -> None:
        self.model.remove_where(predicate)

    def row_for(self, layer_id: str, feature_id: str) -> Optional[int]:
        """Return row index for (layer_id, feature_id), if present."""
        return self.model.row_for(layer_id, feature_id)

    def row_data(self, row_index: int) -> Optional[Any]:
        """Return the underlying row object for a given row index."""
        return self.model.row_data(row_index)

    def selected_keys(self) -> List[FeatureKey]:
        """Return currently selected keys."""
        sm = self.table.selectionModel()
        if sm is None:
            return []
        selected_rows = sm.selectedRows(0)
        keys: List[FeatureKey] = []
        for idx in selected_rows:
            r = idx.row()
            if r < 0 or r >= len(self.model.rows):
                continue
            key = self.model.key_for_row(r)
            if key is not None:
                keys.append(key)
        return keys

    def clear_selection(self) -> None:
        sm = self.table.selectionModel()
        if sm is None:
            return
        self._building_selection = True
        sm.clearSelection()
        self._building_selection = False

    def select_keys(self, keys: Sequence[FeatureKey], clear_first: bool = True) -> None:
        """Programmatically select rows by keys."""
        sm = self.table.selectionModel()
        if sm is None:
            return

        # Convert keys to row indices
        rows = []
        for key in keys:
            r = self.model.row_for_key(key)
            if r is not None:
                rows.append(r)
        
        if not rows:
            if clear_first:
                self._building_selection = True
                sm.clearSelection()
                self._building_selection = False
            return
        
        # Build selection - one range per row for simplicity
        # (Qt will merge adjacent ranges automatically)
        selection = QtCore.QItemSelection()
        last_col = max(0, self.model.columnCount() - 1)
        
        for row in rows:
            selection.append(
                QtCore.QItemSelectionRange(
                    self.model.index(row, 0),
                    self.model.index(row, last_col)
                )
            )

        # Apply selection
        self._building_selection = True
        try:
            if clear_first:
                sm.clearSelection()
            sm.select(
                selection,
                QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows,
            )
        finally:
            self._building_selection = False

    def _on_selection_changed(self, *_args) -> None:
        if self._building_selection:
            return
        self._pending_emit = True
        self._debounce_timer.start(self._debounce_ms)

    def _emit_selection_now(self) -> None:
        if not self._pending_emit:
            return
        self._pending_emit = False
        self.selectionKeysChanged.emit(self.selected_keys())

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
