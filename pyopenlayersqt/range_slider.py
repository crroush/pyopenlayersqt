"""Reusable dual-handle range slider widget.

This module provides a range slider with two handles for selecting a numeric range.
Supports both numeric values and ISO8601 timestamp strings (converted internally).

Key features:
  - Single slider track with two draggable handles
  - Configurable range and step size
  - Signal emission on range changes
  - Special ISO8601 timestamp support (automatic conversion)
  - Clean, modern styling

Typical usage:

    # Numeric range
    slider = RangeSliderWidget(min_val=0, max_val=100, step=1)
    slider.rangeChanged.connect(lambda min_v, max_v: print(f"{min_v} - {max_v}"))

    # ISO8601 timestamps
    slider = RangeSliderWidget(
        values=["2024-01-01T00:00:00Z", "2024-12-31T23:59:59Z"],
        step=86400  # 1 day in seconds
    )
    slider.rangeChanged.connect(lambda min_v, max_v: filter_by_time(min_v, max_v))

Google-style docstrings + PEP8.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Tuple, Union

from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QPainter, QPen, QColor, QPaintEvent, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolTip, QVBoxLayout, QWidget

class DualHandleSlider(QWidget):
    """A single slider widget with two draggable handles for min/max selection."""

    rangeChanged = Signal(int, int)  # (min_value, max_value)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 100
        self._min_value = 0
        self._max_value = 100
        self._handle_radius = 8
        self._track_height = 4
        self._dragging_handle = None  # 'min', 'max', or None
        self._tooltip_formatter: Optional[Callable[[int], str]] = None

        self.setMinimumHeight(40)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

    def setTooltipFormatter(self, formatter: Optional[Callable[[int], str]]) -> None:
        """Set a formatter used to display handle values as tooltips."""
        self._tooltip_formatter = formatter

    def _show_handle_tooltip(self, handle: str) -> None:
        """Show a tooltip for the current value of a handle."""
        if self._tooltip_formatter is None:
            return

        value = self._min_value if handle == 'min' else self._max_value
        tooltip = self._tooltip_formatter(value)
        if not tooltip:
            return

        global_pos = self.mapToGlobal(self._get_handle_rect(value).center())
        QToolTip.showText(global_pos, tooltip, self)

    def setMinimum(self, value: int) -> None:
        """Set the minimum value of the slider range."""
        self._minimum = value
        if self._min_value < value:
            self._min_value = value
        if self._max_value < value:
            self._max_value = value
        self.update()

    def setMaximum(self, value: int) -> None:
        """Set the maximum value of the slider range."""
        self._maximum = value
        if self._min_value > value:
            self._min_value = value
        if self._max_value > value:
            self._max_value = value
        self.update()

    def setMinValue(self, value: int) -> None:
        """Set the current minimum selected value."""
        value = max(self._minimum, min(value, self._max_value))
        if value != self._min_value:
            self._min_value = value
            self.update()
            self.rangeChanged.emit(self._min_value, self._max_value)

    def setMaxValue(self, value: int) -> None:
        """Set the current maximum selected value."""
        value = min(self._maximum, max(value, self._min_value))
        if value != self._max_value:
            self._max_value = value
            self.update()
            self.rangeChanged.emit(self._min_value, self._max_value)

    def minValue(self) -> int:
        """Get the current minimum selected value."""
        return self._min_value

    def maxValue(self) -> int:
        """Get the current maximum selected value."""
        return self._max_value

    def _get_track_rect(self) -> QRect:
        """Get the rectangle for the slider track."""
        margin = self._handle_radius + 5
        return QRect(
            margin,
            (self.height() - self._track_height) // 2,
            self.width() - 2 * margin,
            self._track_height
        )

    def _value_to_pos(self, value: int) -> int:
        """Convert a value to pixel position."""
        track = self._get_track_rect()
        if self._maximum == self._minimum:
            return track.left()
        ratio = (value - self._minimum) / (self._maximum - self._minimum)
        return track.left() + int(ratio * track.width())

    def _pos_to_value(self, pos: int) -> int:
        """Convert pixel position to value."""
        track = self._get_track_rect()
        if track.width() == 0:
            return self._minimum
        ratio = (pos - track.left()) / track.width()
        ratio = max(0.0, min(1.0, ratio))
        return self._minimum + int(ratio * (self._maximum - self._minimum))

    def _get_handle_rect(self, value: int) -> QRect:
        """Get the rectangle for a handle at the given value."""
        x = self._value_to_pos(value)
        y = self.height() // 2
        r = self._handle_radius
        return QRect(x - r, y - r, 2 * r, 2 * r)

    def paintEvent(self, _event: QPaintEvent) -> None:
        """Paint the slider."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track = self._get_track_rect()

        # Draw background track
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(200, 200, 200))
        painter.drawRoundedRect(track, self._track_height / 2, self._track_height / 2)

        # Draw selected range
        min_pos = self._value_to_pos(self._min_value)
        max_pos = self._value_to_pos(self._max_value)
        selected_rect = QRect(
            min_pos,
            track.top(),
            max_pos - min_pos,
            track.height()
        )
        painter.setBrush(QColor(70, 130, 180))  # Steel blue
        painter.drawRoundedRect(selected_rect, self._track_height / 2, self._track_height / 2)

        # Draw handles
        for value, _ in [(self._min_value, False), (self._max_value, True)]:
            handle_rect = self._get_handle_rect(value)

            # Handle shadow
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 30))
            shadow_rect = handle_rect.adjusted(1, 1, 1, 1)
            painter.drawEllipse(shadow_rect)

            # Handle
            painter.setBrush(QColor(255, 255, 255))
            painter.setPen(QPen(QColor(100, 100, 100), 2))
            painter.drawEllipse(handle_rect)

            # Inner dot
            painter.setBrush(QColor(70, 130, 180))
            painter.setPen(Qt.NoPen)
            inner_rect = handle_rect.adjusted(4, 4, -4, -4)
            painter.drawEllipse(inner_rect)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press events."""
        if event.button() == Qt.LeftButton:
            pos = event.pos().x()

            # Check if clicking on handles
            min_handle = self._get_handle_rect(self._min_value)
            max_handle = self._get_handle_rect(self._max_value)

            if min_handle.contains(event.pos()):
                self._dragging_handle = 'min'
                self._show_handle_tooltip('min')
            elif max_handle.contains(event.pos()):
                self._dragging_handle = 'max'
                self._show_handle_tooltip('max')
            else:
                # Click on track - move nearest handle
                value = self._pos_to_value(pos)
                min_dist = abs(value - self._min_value)
                max_dist = abs(value - self._max_value)

                if min_dist < max_dist:
                    self.setMinValue(value)
                    self._dragging_handle = 'min'
                else:
                    self.setMaxValue(value)
                    self._dragging_handle = 'max'

                self._show_handle_tooltip(self._dragging_handle)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move events."""
        if self._dragging_handle:
            pos = event.pos().x()
            value = self._pos_to_value(pos)

            if self._dragging_handle == 'min':
                self.setMinValue(value)
            elif self._dragging_handle == 'max':
                self.setMaxValue(value)

            self._show_handle_tooltip(self._dragging_handle)
        else:
            # Update cursor when hovering over handles
            min_handle = self._get_handle_rect(self._min_value)
            max_handle = self._get_handle_rect(self._max_value)

            if min_handle.contains(event.pos()) or max_handle.contains(event.pos()):
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release events."""
        if event.button() == Qt.LeftButton:
            self._dragging_handle = None
            QToolTip.hideText()


class RangeSliderWidget(QWidget):
    """A dual-handle range slider widget for numeric or ISO8601 timestamp ranges.

    This widget provides a single slider with two handles for selecting a range.
    Values can be numeric or ISO8601 timestamp strings (automatically converted).

    Signals:
        rangeChanged(object, object): Emitted when range changes.
            For numeric mode: (min_val: float, max_val: float)
            For ISO8601 mode: (min_str: str, max_str: str)
    """

    rangeChanged = Signal(object, object)  # (min_value, max_value)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        step: float = 1.0,
        values: Optional[List[str]] = None,
        label: str = "Range",
        show_value_tooltips: bool = False,
    ) -> None:
        """Initialize the range slider.

        Args:
            parent: Parent widget.
            min_val: Minimum numeric value (for numeric mode).
            max_val: Maximum numeric value (for numeric mode).
            step: Step size for numeric values.
            values: List of ISO8601 timestamp strings (for timestamp mode).
                   If provided, overrides min_val/max_val/step.
            label: Label text to display above the slider.
            show_value_tooltips: Whether to show value tooltips while dragging handles.
        """
        super().__init__(parent)

        # Determine mode: ISO8601 or numeric
        self._is_iso8601 = values is not None
        self._iso_values: List[str] = []
        self._min_numeric: float = 0.0
        self._max_numeric: float = 100.0
        self._step: float = step
        self._show_value_tooltips = show_value_tooltips

        if self._is_iso8601:
            # ISO8601 mode: convert timestamps to indices
            self._iso_values = sorted(values)
            self._min_numeric = 0.0
            self._max_numeric = float(len(self._iso_values) - 1)
            self._step = 1.0
        else:
            # Numeric mode
            self._min_numeric = float(min_val) if min_val is not None else 0.0
            self._max_numeric = float(max_val) if max_val is not None else 100.0
            self._step = float(step)

        # Convert to slider integer range (sliders work with integers)
        self._slider_min = 0
        self._slider_max = int((self._max_numeric - self._min_numeric) / self._step)

        # Create UI
        self._setup_ui(label)

        # Initialize to full range
        self._slider.setMinValue(self._slider_min)
        self._slider.setMaxValue(self._slider_max)
        self._update_labels()

    def _setup_ui(self, label: str) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Label
        self._label = QLabel(label)
        layout.addWidget(self._label)

        # Single dual-handle slider
        self._slider = DualHandleSlider()
        self._slider.setMinimum(self._slider_min)
        self._slider.setMaximum(self._slider_max)
        self._slider.rangeChanged.connect(self._on_range_changed)
        if self._show_value_tooltips:
            self._slider.setTooltipFormatter(
                lambda slider_val: self._format_value(self._slider_to_value(slider_val))
            )
        layout.addWidget(self._slider)

        # Value labels
        labels_container = QHBoxLayout()
        self._min_label = QLabel()
        self._max_label = QLabel()
        labels_container.addWidget(QLabel("Min:"))
        labels_container.addWidget(self._min_label)
        labels_container.addStretch()
        labels_container.addWidget(QLabel("Max:"))
        labels_container.addWidget(self._max_label)
        layout.addLayout(labels_container)

    def _slider_to_value(self, slider_val: int) -> float:
        """Convert slider position to numeric value."""
        return self._min_numeric + (slider_val * self._step)

    def _value_to_slider(self, value: float) -> int:
        """Convert numeric value to slider position."""
        return int((value - self._min_numeric) / self._step)

    def _format_value(self, numeric_value: float) -> str:
        """Format a numeric value for display."""
        if self._is_iso8601:
            idx = int(numeric_value)
            if 0 <= idx < len(self._iso_values):
                return self._iso_values[idx]
            return ""
        # Format numeric value nicely
        if self._step >= 1.0:
            return str(int(numeric_value))
        return f"{numeric_value:.2f}"

    def _on_range_changed(self, _min_slider_val: int, _max_slider_val: int) -> None:
        """Handle range change from the dual-handle slider."""
        self._update_labels()
        self._emit_range_changed()

    def _update_labels(self) -> None:
        """Update the value labels."""
        min_val = self._slider_to_value(self._slider.minValue())
        max_val = self._slider_to_value(self._slider.maxValue())

        self._min_label.setText(self._format_value(min_val))
        self._max_label.setText(self._format_value(max_val))

    def _emit_range_changed(self) -> None:
        """Emit the rangeChanged signal with current values."""
        min_val = self._slider_to_value(self._slider.minValue())
        max_val = self._slider_to_value(self._slider.maxValue())

        if self._is_iso8601:
            # Emit ISO8601 strings
            min_str = self._format_value(min_val)
            max_str = self._format_value(max_val)
            self.rangeChanged.emit(min_str, max_str)
        else:
            # Emit numeric values
            self.rangeChanged.emit(min_val, max_val)

    def get_range(self) -> Tuple[Any, Any]:
        """Get the current range.

        Returns:
            Tuple of (min_value, max_value).
            For ISO8601 mode: (str, str)
            For numeric mode: (float, float)
        """
        min_val = self._slider_to_value(self._slider.minValue())
        max_val = self._slider_to_value(self._slider.maxValue())

        if self._is_iso8601:
            return (self._format_value(min_val), self._format_value(max_val))
        return (min_val, max_val)

    def set_range(self, min_value: Union[float, str], max_value: Union[float, str]) -> None:
        """Set the current range programmatically.

        Args:
            min_value: Minimum value (float for numeric mode, str for ISO8601).
            max_value: Maximum value (float for numeric mode, str for ISO8601).
        """
        if self._is_iso8601:
            # Find indices for ISO8601 values
            try:
                min_idx = self._iso_values.index(str(min_value))
                max_idx = self._iso_values.index(str(max_value))
                self._slider.setMinValue(min_idx)
                self._slider.setMaxValue(max_idx)
            except ValueError:
                pass  # Value not in list
        else:
            # Set numeric values
            min_slider = self._value_to_slider(float(min_value))
            max_slider = self._value_to_slider(float(max_value))
            self._slider.setMinValue(min_slider)
            self._slider.setMaxValue(max_slider)

        self._update_labels()
