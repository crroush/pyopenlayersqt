"""High-performance plotting widget with bidirectional selection synchronization.

This module provides a PyQtGraph-based plotting widget that integrates with the
existing map and table infrastructure through shared selection keys.

Key features:
  - Support for 200k+ points with high performance
  - Time-series and scatter plot modes
  - Multiple traces with configurable styling
  - Interactive selection (click, box, ctrl+click)
  - Bidirectional sync with map and table via (layer_id, feature_id) keys
  - Zoom/pan capabilities
  - Selection actions (delete, color change)

Typical usage:

    plot = PlotWidget()

    # Set data
    plot.set_data(
        data_rows=rows,
        key_fn=lambda r: (r.get("layer_id"), r.get("feature_id")),
        x_field="timestamp",
        y_field="value"
    )

    # Selection sync with map/table
    plot.selectionKeysChanged.connect(on_plot_selection)
    plot.select_keys([(layer_id, feature_id), ...])

Google-style docstrings + PEP8.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple
from datetime import datetime

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QGroupBox,
    QColorDialog,
    QFormLayout,
)

FeatureKey = Tuple[str, str]  # (layer_id, feature_id)
KeyFn = Callable[[Any], FeatureKey]


@dataclass
class TraceStyle:
    """Styling configuration for a plot trace."""

    color: str = "#1f77b4"  # Default matplotlib blue
    width: float = 1.0
    symbol: Optional[str] = None  # None, 'o', 's', 't', 'd', '+', 'x'
    symbol_size: float = 5.0
    symbol_brush: Optional[str] = None  # Use pen color if None
    line_style: str = "solid"  # solid, dash, dot, dashdot

    def to_pen(self) -> pg.mkPen:
        """Convert to PyQtGraph pen."""
        style_map = {
            "solid": QtCore.Qt.SolidLine,
            "dash": QtCore.Qt.DashLine,
            "dot": QtCore.Qt.DotLine,
            "dashdot": QtCore.Qt.DashDotLine,
        }
        return pg.mkPen(
            color=self.color,
            width=self.width,
            style=style_map.get(self.line_style, QtCore.Qt.SolidLine),
        )

    def to_symbol_brush(self) -> Optional[pg.mkBrush]:
        """Convert to PyQtGraph brush for symbols."""
        if self.symbol is None:
            return None
        color = self.symbol_brush if self.symbol_brush else self.color
        return pg.mkBrush(color)


class PlotWidget(QWidget):
    """High-performance plotting widget with selection synchronization.

    Attributes:
        selectionKeysChanged: Signal emitted when selection changes.
            Emits list of (layer_id, feature_id) tuples.
    """

    selectionKeysChanged = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the plot widget.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)

        # Data storage
        self._data_rows: List[Any] = []
        self._key_fn: Optional[KeyFn] = None
        self._x_field: Optional[str] = None
        self._y_field: Optional[str] = None
        self._color_field: Optional[str] = None

        # Index mappings
        self._key_to_index: Dict[FeatureKey, int] = {}
        self._index_to_key: Dict[int, FeatureKey] = {}

        # Plot index mappings (for valid data points only)
        self._valid_indices: List[int] = []
        self._valid_key_to_plot_index: Dict[FeatureKey, int] = {}
        self._plot_index_to_key: Dict[int, FeatureKey] = {}

        # Cached plot data (to avoid re-extraction on every selection change)
        self._cached_x_data: Optional[np.ndarray] = None
        self._cached_y_data: Optional[np.ndarray] = None

        # Selection state
        self._selected_keys: Set[FeatureKey] = set()
        self._building_selection = False

        # Debounce timer for selection events
        self._debounce_timer = QtCore.QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._emit_selection_now)
        self._debounce_ms = 90
        self._pending_emit = False

        # Plot items
        self._scatter_item: Optional[pg.ScatterPlotItem] = None
        self._selected_scatter: Optional[pg.ScatterPlotItem] = None

        # UI setup
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)

        # Enable auto-range on initial setup
        self.plot_widget.enableAutoRange()

        # Add plot to layout
        layout.addWidget(self.plot_widget)

        # Get plot item for interaction
        self.plot_item = self.plot_widget.getPlotItem()

        # Enable mouse interaction for zoom and pan
        self.plot_widget.setMouseEnabled(x=True, y=True)

        # Enable mouse wheel zoom
        self.plot_item.vb.setMouseEnabled(x=True, y=True)

        # Right-click drag for box zoom (default PyQtGraph behavior)
        # Left-click drag for pan (default PyQtGraph behavior)
        # Scroll wheel for zoom (default PyQtGraph behavior)

        # Add reset view button to plot
        self.plot_widget.plotItem.showButtons()

        # For box selection, we'll use a LinearRegionItem approach
        # or implement custom mouse handling
        self._box_selection_mode = False
        self._box_start = None
        self._box_rect_item = None

        # Setup selection region (box select)
        self._setup_selection()

    def _setup_selection(self) -> None:
        """Setup selection interaction handlers."""
        # Connect click event for point selection
        self._scatter_item = None
        self._last_clicked_pos = None

        # Box selection using ROI
        self._selection_roi = None
        self._box_selecting = False
        self._box_start = None

        # Override mouse handling for box selection with Shift key
        # Store original mouse press event
        self._original_mousePressEvent = self.plot_item.vb.mousePressEvent
        self._original_mouseMoveEvent = self.plot_item.vb.mouseMoveEvent
        self._original_mouseReleaseEvent = self.plot_item.vb.mouseReleaseEvent

        # Install custom mouse event handlers
        self.plot_item.vb.mousePressEvent = self._custom_mousePressEvent
        self.plot_item.vb.mouseMoveEvent = self._custom_mouseMoveEvent
        self.plot_item.vb.mouseReleaseEvent = self._custom_mouseReleaseEvent

    def _custom_mousePressEvent(self, ev):
        """Custom mouse press handler for box selection."""
        modifiers = QtGui.QGuiApplication.keyboardModifiers()
        ctrl_pressed = bool(modifiers & Qt.ControlModifier)

        if ev.button() == QtCore.Qt.LeftButton and not ctrl_pressed:
            # Start box selection with left-click (Ctrl+Left for pan)
            self._box_selecting = True
            self._box_start = self.plot_item.vb.mapSceneToView(ev.scenePos())

            # Create selection ROI
            if self._selection_roi is not None:
                self.plot_item.removeItem(self._selection_roi)

            self._selection_roi = pg.ROI(
                [self._box_start.x(), self._box_start.y()],
                [0, 0],
                pen=pg.mkPen(color='r', width=2, style=QtCore.Qt.DashLine),
                movable=False,
                resizable=False
            )
            self.plot_item.addItem(self._selection_roi)
            ev.accept()
        else:
            # Use default behavior for pan (Ctrl+Left) and zoom (Right)
            self._original_mousePressEvent(ev)

    def _custom_mouseMoveEvent(self, ev):
        """Custom mouse move handler for box selection."""
        if self._box_selecting and self._box_start is not None:
            current_pos = self.plot_item.vb.mapSceneToView(ev.scenePos())
            width = current_pos.x() - self._box_start.x()
            height = current_pos.y() - self._box_start.y()

            self._selection_roi.setSize([width, height])
            ev.accept()
        else:
            self._original_mouseMoveEvent(ev)

    def _custom_mouseReleaseEvent(self, ev):
        """Custom mouse release handler for box selection."""
        modifiers = QtGui.QGuiApplication.keyboardModifiers()
        shift_pressed = bool(modifiers & Qt.ShiftModifier)

        if self._box_selecting:
            self._box_selecting = False

            if self._box_start is not None and self._selection_roi is not None:
                current_pos = self.plot_item.vb.mapSceneToView(ev.scenePos())

                x_min = min(self._box_start.x(), current_pos.x())
                x_max = max(self._box_start.x(), current_pos.x())
                y_min = min(self._box_start.y(), current_pos.y())
                y_max = max(self._box_start.y(), current_pos.y())

                # Select points in box (Shift to add to selection)
                self.select_points_in_box(
                    x_min, x_max, y_min, y_max, add_to_selection=shift_pressed
                )

                # Remove the ROI
                self.plot_item.removeItem(self._selection_roi)
                self._selection_roi = None

            self._box_start = None
            ev.accept()
        else:
            self._original_mouseReleaseEvent(ev)

    def set_data(
        self,
        data_rows: Sequence[Any],
        key_fn: KeyFn,
        x_field: str,
        y_field: str,
        color_field: Optional[str] = None,
        trace_style: Optional[TraceStyle] = None,
    ) -> None:
        """Set data for the plot.

        Args:
            data_rows: Sequence of data objects (dicts, dataclasses, etc.)
            key_fn: Function to extract (layer_id, feature_id) from a row
            x_field: Field name for X-axis values
            y_field: Field name for Y-axis values
            color_field: Optional field for coloring points
            trace_style: Style configuration for the trace
        """
        self._data_rows = list(data_rows)
        self._key_fn = key_fn
        self._x_field = x_field
        self._y_field = y_field
        self._color_field = color_field

        if trace_style is None:
            trace_style = TraceStyle()

        # Build key mappings
        self._key_to_index = {}
        self._index_to_key = {}
        for i, row in enumerate(self._data_rows):
            key = key_fn(row)
            self._key_to_index[key] = i
            self._index_to_key[i] = key

        # Extract data and build valid indices mapping
        x_data, y_data, valid_indices = self._extract_plot_data()

        if len(x_data) == 0:
            self.clear_plot()
            return

        # Cache the extracted data for performance
        self._cached_x_data = x_data
        self._cached_y_data = y_data

        # Update index mappings to only include valid data points
        self._valid_indices = valid_indices
        self._valid_key_to_plot_index = {}
        self._plot_index_to_key = {}
        for plot_idx, data_idx in enumerate(valid_indices):
            key = self._index_to_key.get(data_idx)
            if key:
                self._valid_key_to_plot_index[key] = plot_idx
                self._plot_index_to_key[plot_idx] = key

        # Clear existing plot items
        self.plot_item.clear()

        # Determine plot type
        is_time_series = self._is_time_series(x_data)

        # Create scatter plot
        pen = trace_style.to_pen()
        symbol = trace_style.symbol if trace_style.symbol else 'o'
        symbol_size = trace_style.symbol_size
        symbol_brush = trace_style.to_symbol_brush()

        # Create main scatter plot item
        self._scatter_item = pg.ScatterPlotItem(
            x=x_data,
            y=y_data,
            pen=pen,
            brush=symbol_brush,
            symbol=symbol,
            size=symbol_size,
        )

        # Connect click handler
        self._scatter_item.sigClicked.connect(self._on_points_clicked)

        self.plot_item.addItem(self._scatter_item)

        # Setup axis labels
        self.plot_item.setLabel('bottom', self._x_field)
        self.plot_item.setLabel('left', self._y_field)

        # If time series, configure X axis
        if is_time_series:
            axis = pg.DateAxisItem(orientation='bottom')
            self.plot_item.setAxisItems({'bottom': axis})

        # Auto-range
        self.plot_widget.autoRange()

        # Create overlay for selected points
        self._update_selection_overlay()

    def _extract_plot_data(self) -> Tuple[np.ndarray, np.ndarray, List[int]]:
        """Extract X and Y data from rows.

        Returns:
            Tuple of (x_data, y_data, valid_indices) as numpy arrays and list.
            valid_indices contains the original row indices that have valid data.
        """
        x_data = []
        y_data = []
        valid_indices = []

        for i, row in enumerate(self._data_rows):
            try:
                # Extract X value
                if isinstance(row, dict):
                    x_val = row.get(self._x_field)
                    y_val = row.get(self._y_field)
                else:
                    x_val = getattr(row, self._x_field, None)
                    y_val = getattr(row, self._y_field, None)

                # Convert X if datetime
                if isinstance(x_val, (datetime, np.datetime64)):
                    if hasattr(x_val, 'timestamp'):
                        x_val = x_val.timestamp()
                    else:
                        x_val = float(x_val.astype(int) / 1e9)
                elif isinstance(x_val, str):
                    # Try to parse as datetime
                    try:
                        dt = datetime.fromisoformat(x_val.replace('Z', '+00:00'))
                        x_val = dt.timestamp()
                    except (ValueError, TypeError):
                        x_val = float(x_val)
                else:
                    x_val = float(x_val)

                y_val = float(y_val)

                x_data.append(x_val)
                y_data.append(y_val)
                valid_indices.append(i)
            except (ValueError, TypeError, AttributeError):
                # Skip invalid data points
                continue

        return np.array(x_data), np.array(y_data), valid_indices

    def _is_time_series(self, x_data: np.ndarray) -> bool:
        """Detect if X data represents a time series.

        Args:
            x_data: X-axis data

        Returns:
            True if data appears to be timestamps
        """
        if len(x_data) == 0:
            return False

        # Check if field name suggests time
        time_keywords = ['time', 'date', 'timestamp', 'ts', 'datetime']
        if self._x_field and any(kw in self._x_field.lower() for kw in time_keywords):
            return True

        # Check if values are in reasonable timestamp range
        # (Unix timestamps are typically large numbers > 1e9)
        if np.min(x_data) > 1e9:
            return True

        return False

    def _on_points_clicked(
        self, _scatter_item: pg.ScatterPlotItem, points: Sequence, _ev
    ) -> None:
        """Handle point click events.

        Args:
            scatter_item: The scatter plot item
            points: List of clicked point(s)
            ev: Mouse event
        """
        if len(points) == 0:
            return

        # Get modifiers
        modifiers = QtGui.QGuiApplication.keyboardModifiers()
        ctrl_pressed = bool(modifiers & Qt.ControlModifier)

        # Get clicked point indices (plot indices, not data indices)
        clicked_keys = []
        for point in points:
            plot_idx = point.index()
            if plot_idx in self._plot_index_to_key:
                clicked_keys.append(self._plot_index_to_key[plot_idx])

        if len(clicked_keys) == 0:
            return

        # Update selection
        if ctrl_pressed:
            # Toggle selection
            for key in clicked_keys:
                if key in self._selected_keys:
                    self._selected_keys.discard(key)
                else:
                    self._selected_keys.add(key)
        else:
            # Replace selection
            self._selected_keys = set(clicked_keys)

        # Update visual and emit signal
        self._update_selection_overlay()
        self._trigger_selection_changed()

    def _update_selection_overlay(self) -> None:
        """Update the visual overlay for selected points."""
        # Remove old selected scatter if exists
        if self._selected_scatter is not None:
            self.plot_item.removeItem(self._selected_scatter)
            self._selected_scatter = None

        if len(self._selected_keys) == 0:
            return

        # Get selected plot indices (indices in the x_data/y_data arrays)
        selected_plot_indices = [
            self._valid_key_to_plot_index[key]
            for key in self._selected_keys
            if key in self._valid_key_to_plot_index
        ]

        if len(selected_plot_indices) == 0:
            return

        # Use cached data for performance instead of re-extracting
        if self._cached_x_data is None or self._cached_y_data is None:
            return

        # Get selected points using plot indices
        selected_x = self._cached_x_data[selected_plot_indices]
        selected_y = self._cached_y_data[selected_plot_indices]

        # Create highlight scatter
        self._selected_scatter = pg.ScatterPlotItem(
            x=selected_x,
            y=selected_y,
            pen=pg.mkPen(color='#ff0000', width=2),
            brush=pg.mkBrush(255, 0, 0, 100),
            symbol='o',
            size=10,
        )

        self.plot_item.addItem(self._selected_scatter)

    def _trigger_selection_changed(self) -> None:
        """Trigger debounced selection change emission."""
        if self._building_selection:
            return
        self._pending_emit = True
        self._debounce_timer.start(self._debounce_ms)

    def _emit_selection_now(self) -> None:
        """Emit the selection changed signal now."""
        if not self._pending_emit:
            return
        self._pending_emit = False
        self.selectionKeysChanged.emit(list(self._selected_keys))

    def select_keys(self, keys: Sequence[FeatureKey], clear_first: bool = True) -> None:
        """Programmatically select points by keys.

        Args:
            keys: Sequence of (layer_id, feature_id) tuples to select
            clear_first: If True, clear existing selection first
        """
        self._building_selection = True

        if clear_first:
            self._selected_keys.clear()

        for key in keys:
            if key in self._key_to_index:
                self._selected_keys.add(key)

        self._update_selection_overlay()
        self._building_selection = False

    def selected_keys(self) -> List[FeatureKey]:
        """Get currently selected keys.

        Returns:
            List of (layer_id, feature_id) tuples
        """
        return list(self._selected_keys)

    def clear_selection(self) -> None:
        """Clear all selections."""
        self._building_selection = True
        self._selected_keys.clear()
        self._update_selection_overlay()
        self._building_selection = False

    def select_points_in_box(
        self,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        add_to_selection: bool = False
    ) -> None:
        """Select points within a box region.

        Args:
            x_min: Minimum X coordinate
            x_max: Maximum X coordinate
            y_min: Minimum Y coordinate
            y_max: Maximum Y coordinate
            add_to_selection: If True, add to existing selection; if False, replace
        """
        if not self._data_rows or not self._key_fn:
            return

        # Extract all data
        x_data, y_data, _ = self._extract_plot_data()

        if len(x_data) == 0:
            return

        # Find points in box (using plot indices)
        in_box = (
            (x_data >= x_min) & (x_data <= x_max) &
            (y_data >= y_min) & (y_data <= y_max)
        )
        selected_plot_indices = np.where(in_box)[0]

        # Convert plot indices to keys
        selected_keys = [
            self._plot_index_to_key[int(plot_idx)]
            for plot_idx in selected_plot_indices
            if int(plot_idx) in self._plot_index_to_key
        ]

        # Update selection
        if not add_to_selection:
            self._selected_keys.clear()

        self._selected_keys.update(selected_keys)

        # Update visual and emit
        self._update_selection_overlay()
        self._trigger_selection_changed()

    def clear_plot(self) -> None:
        """Clear all plot data and selections."""
        self.plot_item.clear()
        self._data_rows = []
        self._key_to_index = {}
        self._index_to_key = {}
        self._selected_keys.clear()
        self._scatter_item = None
        self._selected_scatter = None
        self._cached_x_data = None
        self._cached_y_data = None

    def delete_selected(self) -> List[FeatureKey]:
        """Delete selected points from the plot.

        Returns:
            List of deleted keys for external cleanup
        """
        if len(self._selected_keys) == 0:
            return []

        deleted_keys = list(self._selected_keys)

        # Remove from data rows
        indices_to_remove = sorted(
            [self._key_to_index[key] for key in deleted_keys if key in self._key_to_index],
            reverse=True
        )

        for idx in indices_to_remove:
            del self._data_rows[idx]

        # Rebuild mappings
        self._key_to_index = {}
        self._index_to_key = {}
        for i, row in enumerate(self._data_rows):
            if self._key_fn:
                key = self._key_fn(row)
                self._key_to_index[key] = i
                self._index_to_key[i] = key

        # Clear selection
        self._selected_keys.clear()

        # Refresh plot
        if self._x_field and self._y_field and self._key_fn:
            self.set_data(
                self._data_rows,
                self._key_fn,
                self._x_field,
                self._y_field,
                self._color_field
            )

        return deleted_keys

    def recolor_selected(self, color: str) -> None:
        """Change color of selected points.

        Args:
            color: New color as hex string (e.g., '#ff0000')
        """
        # This is a simplified implementation
        # For full multi-color support, we'd need to track per-point colors
        # For now, update the selection overlay color
        if self._selected_scatter is not None:
            self.plot_item.removeItem(self._selected_scatter)

        if len(self._selected_keys) == 0:
            return

        selected_plot_indices = [
            self._valid_key_to_plot_index[key]
            for key in self._selected_keys
            if key in self._valid_key_to_plot_index
        ]

        if len(selected_plot_indices) == 0:
            return

        # Use cached data for performance
        if self._cached_x_data is None or self._cached_y_data is None:
            return

        selected_x = self._cached_x_data[selected_plot_indices]
        selected_y = self._cached_y_data[selected_plot_indices]

        self._selected_scatter = pg.ScatterPlotItem(
            x=selected_x,
            y=selected_y,
            pen=pg.mkPen(color=color, width=2),
            brush=pg.mkBrush(color),
            symbol='o',
            size=10,
        )

        self.plot_item.addItem(self._selected_scatter)


class PlotControlWidget(QWidget):
    """Control panel for plot configuration.

    Provides UI controls for:
    - Field selection (X, Y axes)
    - Trace styling
    - Plot actions (clear, delete selected, etc.)
    """

    dataRequested = Signal(str, str)  # (x_field, y_field)
    clearRequested = Signal()
    deleteSelectedRequested = Signal()
    colorSelectedRequested = Signal(str)  # color

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the control widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the user interface."""
        layout = QVBoxLayout(self)

        # Field selection group
        field_group = QGroupBox("Data Fields")
        field_layout = QFormLayout(field_group)

        self.x_field_combo = QComboBox()
        self.y_field_combo = QComboBox()

        field_layout.addRow("X-axis:", self.x_field_combo)
        field_layout.addRow("Y-axis:", self.y_field_combo)

        self.update_plot_btn = QPushButton("Update Plot")
        self.update_plot_btn.clicked.connect(self._on_update_plot)
        field_layout.addRow("", self.update_plot_btn)

        layout.addWidget(field_group)

        # Actions group
        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout(actions_group)

        self.clear_btn = QPushButton("Clear Plot")
        self.clear_btn.clicked.connect(self._on_clear)
        actions_layout.addWidget(self.clear_btn)

        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.clicked.connect(self._on_delete)
        actions_layout.addWidget(self.delete_btn)

        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Color Selected:"))
        self.color_btn = QPushButton()
        self.color_btn.setStyleSheet("background-color: #ff0000")
        self.color_btn.setMaximumWidth(60)
        self.color_btn.clicked.connect(self._on_choose_color)
        color_row.addWidget(self.color_btn)
        color_row.addStretch()
        actions_layout.addLayout(color_row)

        layout.addWidget(actions_group)

        # Interaction help
        help_label = QLabel(
            "<b>Plot Interaction:</b><br/>"
            "• Click: Select point<br/>"
            "• Ctrl+Click: Toggle multi-select<br/>"
            "• <b>Left-Drag: Box select</b><br/>"
            "• <b>Shift+Drag: Add to selection</b><br/>"
            "• Ctrl+Drag: Pan<br/>"
            "• Right-Drag: Box zoom<br/>"
            "• Mouse wheel: Zoom<br/>"
            "• 'A' button: Auto-range"
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            "padding: 10px; background-color: #f0f0f0; "
            "border-radius: 3px; font-size: 9pt;"
        )
        layout.addWidget(help_label)

        layout.addStretch()

    def set_available_fields(self, fields: Sequence[str]) -> None:
        """Set available fields for X and Y selection.

        Args:
            fields: List of field names
        """
        self.x_field_combo.clear()
        self.y_field_combo.clear()

        for field in fields:
            self.x_field_combo.addItem(field)
            self.y_field_combo.addItem(field)

        # Auto-select reasonable defaults
        if len(fields) >= 2:
            self.x_field_combo.setCurrentIndex(0)
            self.y_field_combo.setCurrentIndex(1)

    def _on_update_plot(self) -> None:
        """Handle update plot button click."""
        x_field = self.x_field_combo.currentText()
        y_field = self.y_field_combo.currentText()

        if x_field and y_field:
            self.dataRequested.emit(x_field, y_field)

    def _on_clear(self) -> None:
        """Handle clear button click."""
        self.clearRequested.emit()

    def _on_delete(self) -> None:
        """Handle delete button click."""
        self.deleteSelectedRequested.emit()

    def _on_choose_color(self) -> None:
        """Handle color selection for points."""
        color = QColorDialog.getColor()
        if color.isValid():
            self.color_btn.setStyleSheet(f"background-color: {color.name()}")
            self.colorSelectedRequested.emit(color.name())
