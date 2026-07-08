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
        min_val="2024-01-01T00:00:00Z",
        max_val="2024-12-31T23:59:59Z",
        step=3600.0,
        is_iso8601=True,
    )
    slider.rangeChanged.connect(lambda min_v, max_v: filter_by_time(min_v, max_v))

Google-style docstrings + PEP8.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Callable, List, Optional, Tuple, Union

from PySide6.QtCore import Qt, QEvent, Signal, QRect
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
        self._hovered_handle = None  # 'min', 'max', or None
        self._drag_range_start_value: Optional[int] = None
        self._drag_range_initial_min: Optional[int] = None
        self._drag_range_initial_max: Optional[int] = None
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

        value = self._min_value if handle == "min" else self._max_value
        tooltip = self._tooltip_formatter(value)
        if not tooltip:
            return

        global_pos = self.mapToGlobal(self._get_handle_rect(value).center())
        QToolTip.showText(global_pos, tooltip, self, QRect(), 2500)

    def _handle_at_pos(self, event_pos) -> Optional[str]:
        """Return which handle is currently under the given position."""
        min_handle = self._get_handle_rect(self._min_value)
        max_handle = self._get_handle_rect(self._max_value)

        if min_handle.contains(event_pos):
            return "min"
        if max_handle.contains(event_pos):
            return "max"
        return None

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
            self._track_height,
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

    def _get_selected_rect(self) -> QRect:
        """Get the rectangle for the currently selected range segment."""
        track = self._get_track_rect()
        min_pos = self._value_to_pos(self._min_value)
        max_pos = self._value_to_pos(self._max_value)
        return QRect(min_pos, track.top(), max(max_pos - min_pos, 0), track.height())

    def _is_in_selected_range_hit_area(self, event_pos) -> bool:
        """Return True when pointer is within the draggable selected-range region."""
        min_pos = self._value_to_pos(self._min_value)
        max_pos = self._value_to_pos(self._max_value)
        if max_pos <= min_pos:
            return False

        y_center = self.height() // 2
        y_tolerance = self._handle_radius + 6
        return min_pos <= event_pos.x() <= max_pos and (
            y_center - y_tolerance
        ) <= event_pos.y() <= (y_center + y_tolerance)

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
        selected_rect = self._get_selected_rect()
        painter.setBrush(QColor(70, 130, 180))  # Steel blue
        painter.drawRoundedRect(
            selected_rect, self._track_height / 2, self._track_height / 2
        )

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
            hovered_handle = self._handle_at_pos(event.pos())

            if hovered_handle is not None:
                self._dragging_handle = hovered_handle
                self._hovered_handle = hovered_handle
                self._show_handle_tooltip(hovered_handle)
            elif self._is_in_selected_range_hit_area(event.pos()):
                self._dragging_handle = "range"
                self._drag_range_start_value = self._pos_to_value(pos)
                self._drag_range_initial_min = self._min_value
                self._drag_range_initial_max = self._max_value
                self.setCursor(Qt.ClosedHandCursor)
            else:
                # Click on track - move nearest handle
                value = self._pos_to_value(pos)
                min_dist = abs(value - self._min_value)
                max_dist = abs(value - self._max_value)

                if min_dist < max_dist:
                    self.setMinValue(value)
                    self._dragging_handle = "min"
                else:
                    self.setMaxValue(value)
                    self._dragging_handle = "max"

                self._show_handle_tooltip(self._dragging_handle)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move events."""
        if self._dragging_handle:
            pos = event.pos().x()
            value = self._pos_to_value(pos)

            if self._dragging_handle == "min":
                self.setMinValue(value)
            elif self._dragging_handle == "max":
                self.setMaxValue(value)
            elif (
                self._dragging_handle == "range"
                and self._drag_range_start_value is not None
                and self._drag_range_initial_min is not None
                and self._drag_range_initial_max is not None
            ):
                delta = value - self._drag_range_start_value
                span = self._drag_range_initial_max - self._drag_range_initial_min
                new_min = self._drag_range_initial_min + delta
                new_max = self._drag_range_initial_max + delta

                if new_min < self._minimum:
                    new_min = self._minimum
                    new_max = new_min + span
                if new_max > self._maximum:
                    new_max = self._maximum
                    new_min = new_max - span

                if new_min != self._min_value or new_max != self._max_value:
                    self._min_value = int(new_min)
                    self._max_value = int(new_max)
                    self.update()
                    self.rangeChanged.emit(self._min_value, self._max_value)

            if self._dragging_handle in ("min", "max"):
                self._show_handle_tooltip(self._dragging_handle)
        else:
            # Update cursor/tooltip when hovering over handles
            hovered_handle = self._handle_at_pos(event.pos())
            self._hovered_handle = hovered_handle

            if hovered_handle is not None:
                self.setCursor(Qt.PointingHandCursor)
                self._show_handle_tooltip(hovered_handle)
            elif self._is_in_selected_range_hit_area(event.pos()):
                self.setCursor(Qt.OpenHandCursor)
                QToolTip.hideText()
            else:
                self.setCursor(Qt.ArrowCursor)
                QToolTip.hideText()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release events."""
        if event.button() == Qt.LeftButton:
            self._dragging_handle = None
            self._drag_range_start_value = None
            self._drag_range_initial_min = None
            self._drag_range_initial_max = None
            self.setCursor(Qt.ArrowCursor)
            if self._hovered_handle is None:
                QToolTip.hideText()

    def leaveEvent(self, _event: QEvent) -> None:
        """Hide tooltip when leaving the slider widget."""
        self._hovered_handle = None
        if self._dragging_handle is None:
            QToolTip.hideText()


class GraphicalTimeSlider(QWidget):
    """Interactive histogram-backed time range slider with zooming."""

    rangeChanged = Signal(int, int)
    viewChanged = Signal(int, int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 100
        self._view_min = 0
        self._view_max = 100
        self._min_value = 0
        self._max_value = 100
        self._timestamps: List[float] = []
        self._bins: List[Tuple[int, int, int]] = []
        self._dragging_handle = None
        self._handle_radius = 7
        self._tooltip_formatter: Optional[Callable[[int], str]] = None
        self.setMinimumHeight(110)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

    def setTooltipFormatter(self, formatter: Optional[Callable[[int], str]]) -> None:
        self._tooltip_formatter = formatter

    def setDistributionValues(self, timestamps: List[float]) -> None:
        self._timestamps = sorted(timestamps)
        self._reaggregate()
        self.update()

    def setMinimum(self, value: int) -> None:
        self._minimum = value
        self._view_min = max(self._view_min, value)
        self.setMinValue(max(self._min_value, value))
        self._reaggregate()

    def setMaximum(self, value: int) -> None:
        old_maximum = self._maximum
        self._maximum = value
        if self._view_max == old_maximum or self._view_max > value:
            self._view_max = value
        self.setMaxValue(min(self._max_value, value))
        self._reaggregate()

    def setViewRange(self, min_value: int, max_value: int) -> None:
        if max_value <= min_value:
            return
        self._view_min = max(self._minimum, min_value)
        self._view_max = min(self._maximum, max_value)
        self._reaggregate()
        self.update()
        self.viewChanged.emit(self._view_min, self._view_max)

    def resetView(self) -> None:
        self.setViewRange(self._minimum, self._maximum)

    def setMinValue(self, value: int) -> None:
        value = max(self._minimum, min(value, self._max_value))
        if value != self._min_value:
            self._min_value = value
            self.update()
            self.rangeChanged.emit(self._min_value, self._max_value)

    def setMaxValue(self, value: int) -> None:
        value = min(self._maximum, max(value, self._min_value))
        if value != self._max_value:
            self._max_value = value
            self.update()
            self.rangeChanged.emit(self._min_value, self._max_value)

    def minValue(self) -> int:
        return self._min_value

    def maxValue(self) -> int:
        return self._max_value

    def _plot_rect(self) -> QRect:
        margin = self._handle_radius + 5
        return QRect(
            margin, 8, max(1, self.width() - 2 * margin), max(1, self.height() - 30)
        )

    def _value_to_pos(self, value: int) -> int:
        rect = self._plot_rect()
        if self._view_max == self._view_min:
            return rect.left()
        ratio = (value - self._view_min) / (self._view_max - self._view_min)
        return rect.left() + int(max(0.0, min(1.0, ratio)) * rect.width())

    def _pos_to_value(self, pos: int) -> int:
        rect = self._plot_rect()
        ratio = (pos - rect.left()) / max(rect.width(), 1)
        ratio = max(0.0, min(1.0, ratio))
        return self._view_min + int(ratio * (self._view_max - self._view_min))

    def _handle_at_pos(self, pos) -> Optional[str]:
        y = self._plot_rect().bottom() + 8
        for name, value in (("min", self._min_value), ("max", self._max_value)):
            x = self._value_to_pos(value)
            if QRect(x - 9, y - 9, 18, 18).contains(pos):
                return name
        return None

    def _show_tooltip(self, handle: str) -> None:
        if self._tooltip_formatter is None:
            return
        value = self._min_value if handle == "min" else self._max_value
        QToolTip.showText(
            self.mapToGlobal(self._plot_rect().center()),
            self._tooltip_formatter(value),
            self,
            QRect(),
            1800,
        )

    def _reaggregate(self) -> None:
        width_bins = max(20, min(240, self._plot_rect().width() // 4))
        span = max(self._view_max - self._view_min, 1)
        bin_size = max(1, math.ceil(span / width_bins))
        counts = {}
        for ts in self._timestamps:
            if self._view_min <= ts <= self._view_max:
                start = (
                    self._view_min + int((ts - self._view_min) // bin_size) * bin_size
                )
                counts[start] = counts.get(start, 0) + 1
        self._bins = [
            (start, min(start + bin_size, self._view_max), count)
            for start, count in sorted(counts.items())
        ]

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self._plot_rect()
        painter.setPen(QPen(QColor(210, 210, 210), 1))
        painter.setBrush(QColor(248, 250, 252))
        painter.drawRoundedRect(rect, 4, 4)
        max_count = max((count for _, _, count in self._bins), default=1)
        painter.setPen(Qt.NoPen)
        for start, end, count in self._bins:
            x1 = self._value_to_pos(start)
            x2 = max(x1 + 1, self._value_to_pos(end))
            height = int((count / max_count) * (rect.height() - 8))
            bar = QRect(x1, rect.bottom() - height, max(1, x2 - x1 - 1), height)
            painter.setBrush(QColor(94, 151, 246, 180))
            painter.drawRect(bar)
        sel_left = self._value_to_pos(self._min_value)
        sel_right = self._value_to_pos(self._max_value)
        painter.setBrush(QColor(70, 130, 180, 50))
        painter.drawRect(
            QRect(sel_left, rect.top(), max(0, sel_right - sel_left), rect.height())
        )
        painter.setPen(QPen(QColor(55, 100, 145), 2))
        for value in (self._min_value, self._max_value):
            x = self._value_to_pos(value)
            painter.drawLine(x, rect.top(), x, rect.bottom() + 8)
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(
                x - self._handle_radius,
                rect.bottom() + 1,
                self._handle_radius * 2,
                self._handle_radius * 2,
            )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reaggregate()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            handle = self._handle_at_pos(event.pos())
            value = self._pos_to_value(event.pos().x())
            if handle is None:
                handle = (
                    "min"
                    if abs(value - self._min_value) < abs(value - self._max_value)
                    else "max"
                )
            self._dragging_handle = handle
            if handle == "min":
                self.setMinValue(value)
            else:
                self.setMaxValue(value)
            self._show_tooltip(handle)
        elif event.button() == Qt.RightButton:
            self.resetView()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging_handle == "min":
            self.setMinValue(self._pos_to_value(event.pos().x()))
            self._show_tooltip("min")
        elif self._dragging_handle == "max":
            self.setMaxValue(self._pos_to_value(event.pos().x()))
            self._show_tooltip("max")
        else:
            self.setCursor(
                Qt.PointingHandCursor
                if self._handle_at_pos(event.pos())
                else Qt.ArrowCursor
            )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging_handle = None
            QToolTip.hideText()

    def wheelEvent(self, event) -> None:
        if self._maximum <= self._minimum:
            return
        cursor_value = self._pos_to_value(
            event.position().x() if hasattr(event, "position") else event.pos().x()
        )
        span = self._view_max - self._view_min
        zoom_factor = 0.75 if event.angleDelta().y() > 0 else 1.35
        new_span = int(max(1, min(self._maximum - self._minimum, span * zoom_factor)))
        ratio = (cursor_value - self._view_min) / max(span, 1)
        new_min = int(cursor_value - ratio * new_span)
        new_max = new_min + new_span
        if new_min < self._minimum:
            new_min = self._minimum
            new_max = new_min + new_span
        if new_max > self._maximum:
            new_max = self._maximum
            new_min = new_max - new_span
        self.setViewRange(new_min, new_max)
        event.accept()


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
        min_val: Optional[Union[float, str]] = None,
        max_val: Optional[Union[float, str]] = None,
        step: float = 1.0,
        values: Optional[List[str]] = None,
        is_iso8601: bool = False,
        label: str = "Range",
        show_value_tooltips: bool = False,
    ) -> None:
        """Initialize the range slider.

        Args:
            parent: Parent widget.
            min_val: Minimum value for the slider's available range.
                     Numeric mode expects a number; ISO8601 mode expects a timestamp string.
            max_val: Maximum value for the slider's available range.
                     Numeric mode expects a number; ISO8601 mode expects a timestamp string.
            step: Numeric step size for numeric mode, or step size in seconds for ISO8601.
            values: List of ISO8601 timestamp strings (for timestamp mode).
                   If provided, these explicit values define timestamp positions.
            is_iso8601: Whether the slider should operate in ISO8601 timestamp mode.
            label: Label text to display above the slider.
            show_value_tooltips: Whether to show value tooltips while dragging handles.
        """
        super().__init__(parent)

        # Determine mode at construction time
        self._is_iso8601 = is_iso8601
        self._iso_values: List[str] = []
        self._min_numeric: float = 0.0
        self._max_numeric: float = 100.0
        self._step: float = step
        self._show_value_tooltips = show_value_tooltips
        self._value_formatter: Optional[Callable[[float], str]] = None
        self._iso_origin_ts: float = 0.0
        self._iso_max_ts: float = 0.0
        self._iso_step_seconds: float = 1.0

        if self._is_iso8601:
            if values is not None:
                self._configure_iso_values(values)
            else:
                iso_min = (
                    str(min_val) if min_val is not None else "1970-01-01T00:00:00Z"
                )
                iso_max = str(max_val) if max_val is not None else iso_min
                iso_step_seconds = step if step > 0 else None
                self._configure_iso_range(
                    min_value=iso_min,
                    max_value=iso_max,
                    step_seconds=iso_step_seconds,
                )
        else:
            # Numeric mode
            self._configure_numeric_range(
                min_val=float(min_val) if min_val is not None else None,
                max_val=float(max_val) if max_val is not None else None,
                step=step,
            )

        # Convert to slider integer range (sliders work with integers).
        # ISO range configuration may use a ceiling max slot so the true max
        # timestamp is still reachable when the step does not divide evenly.
        if not self._is_iso8601:
            self._slider_min = 0
            self._slider_max = int((self._max_numeric - self._min_numeric) / self._step)

        # Create UI
        self._setup_ui(label)

        # Initialize to full range
        self._slider.setMinValue(self._slider_min)
        self._slider.setMaxValue(self._slider_max)
        self._update_labels()

    def _configure_numeric_range(
        self,
        min_val: Optional[float],
        max_val: Optional[float],
        step: float,
    ) -> None:
        """Configure the internal numeric range."""
        self._min_numeric = float(min_val) if min_val is not None else 0.0
        self._max_numeric = float(max_val) if max_val is not None else 100.0
        self._step = float(step)
        self._slider_min = 0
        self._slider_max = int((self._max_numeric - self._min_numeric) / self._step)

    def _configure_iso_values(self, values: List[str]) -> None:
        """Configure ISO8601 values and map them to slider indices."""
        self._iso_values = sorted(set(values))
        self._iso_origin_ts = (
            self._parse_iso8601(self._iso_values[0]) if self._iso_values else 0.0
        )
        self._iso_max_ts = (
            self._parse_iso8601(self._iso_values[-1]) if self._iso_values else 0.0
        )
        self._min_numeric = 0.0
        self._max_numeric = float(max(len(self._iso_values) - 1, 0))
        self._step = 1.0
        self._slider_min = 0
        self._slider_max = int(self._max_numeric)

    def _parse_iso8601(self, value: str) -> float:
        """Parse an ISO8601 string and return a UTC timestamp in seconds."""
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).timestamp()

    def _timestamp_to_iso8601(self, timestamp: float) -> str:
        """Convert a UTC timestamp in seconds to an ISO8601 string with Z suffix."""
        return (
            datetime.fromtimestamp(timestamp, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _configure_iso_range(
        self,
        min_value: str,
        max_value: str,
        step_seconds: Optional[float] = None,
        target_steps: int = 400,
    ) -> None:
        """Configure ISO8601 mode from min/max bounds instead of explicit values."""
        min_ts = self._parse_iso8601(min_value)
        max_ts = self._parse_iso8601(max_value)
        if max_ts < min_ts:
            min_ts, max_ts = max_ts, min_ts

        range_seconds = max_ts - min_ts
        computed_step = step_seconds
        if computed_step is None:
            computed_step = self._choose_iso_step_seconds(range_seconds, target_steps)

        self._iso_values = []
        self._iso_origin_ts = min_ts
        self._iso_max_ts = max_ts
        self._iso_step_seconds = float(computed_step)
        self._min_numeric = 0.0
        self._max_numeric = (
            range_seconds / self._iso_step_seconds
            if self._iso_step_seconds > 0
            else 0.0
        )
        self._step = 1.0
        self._slider_min = 0
        self._slider_max = int(math.ceil(max(self._max_numeric, 0.0)))

    def _choose_iso_step_seconds(
        self, range_seconds: float, target_steps: int = 400
    ) -> float:
        """Pick a human-friendly ISO8601 step size in seconds."""
        if range_seconds <= 0:
            return 1.0

        ideal = range_seconds / max(target_steps, 1)
        candidate_steps = [
            1,
            5,
            10,
            15,
            30,
            60,
            5 * 60,
            10 * 60,
            15 * 60,
            30 * 60,
            60 * 60,
            2 * 60 * 60,
            3 * 60 * 60,
            6 * 60 * 60,
            12 * 60 * 60,
            24 * 60 * 60,
            2 * 24 * 60 * 60,
            7 * 24 * 60 * 60,
            14 * 24 * 60 * 60,
            30 * 24 * 60 * 60,
        ]
        for step in candidate_steps:
            if step >= ideal:
                return float(step)
        return float(candidate_steps[-1])

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

    def set_value_formatter(self, formatter: Optional[Callable[[float], str]]) -> None:
        """Set a formatter for numeric labels and handle tooltips."""
        self._value_formatter = formatter
        self._update_labels()
        if self._show_value_tooltips:
            self._slider.setTooltipFormatter(
                lambda slider_val: self._format_value(self._slider_to_value(slider_val))
            )

    def set_available_range(
        self,
        min_value: Union[float, str],
        max_value: Union[float, str],
        step: Optional[float] = None,
    ) -> None:
        """Replace available bounds and select the full new range."""
        if self._is_iso8601 or isinstance(min_value, str) or isinstance(max_value, str):
            self._is_iso8601 = True
            self._configure_iso_range(
                min_value=str(min_value),
                max_value=str(max_value),
                step_seconds=step,
            )
            self._slider.setMinimum(self._slider_min)
            self._slider.setMaximum(self._slider_max)
            self._slider.setMinValue(self._slider_min)
            self._slider.setMaxValue(self._slider_max)
            self._update_labels()
            return

        self._is_iso8601 = False
        self._configure_numeric_range(
            min_val=float(min_value),
            max_val=float(max_value),
            step=float(step) if step is not None else self._step,
        )
        self._slider.setMinimum(self._slider_min)
        self._slider.setMaximum(self._slider_max)
        self._slider.setMinValue(self._slider_min)
        self._slider.setMaxValue(self._slider_max)
        self._update_labels()

    def _format_value(self, numeric_value: float) -> str:
        """Format a numeric value for display."""
        if self._value_formatter is not None:
            return self._value_formatter(numeric_value)
        if self._is_iso8601:
            idx = int(numeric_value)
            if self._iso_values:
                if 0 <= idx < len(self._iso_values):
                    return self._iso_values[idx]
                return ""
            timestamp = self._iso_origin_ts + (idx * self._iso_step_seconds)
            return self._timestamp_to_iso8601(min(timestamp, self._iso_max_ts))
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

    def reset_range(self) -> None:
        """Reset the slider to its full available range."""
        self._slider.setMinValue(self._slider_min)
        self._slider.setMaxValue(self._slider_max)
        self._update_labels()

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

    def set_range(
        self, min_value: Union[float, str], max_value: Union[float, str]
    ) -> None:
        """Set the current range programmatically.

        Args:
            min_value: Minimum value (float for numeric mode, str for ISO8601).
            max_value: Maximum value (float for numeric mode, str for ISO8601).

        Notes:
            If called with values outside the current available bounds, the widget
            will automatically expand/reconfigure its available range to include
            the requested values.
        """
        if self._is_iso8601:
            # Find indices for ISO8601 values
            if self._iso_values:
                try:
                    min_idx = self._iso_values.index(str(min_value))
                    max_idx = self._iso_values.index(str(max_value))
                    self._slider.setMinValue(min_idx)
                    self._slider.setMaxValue(max_idx)
                except ValueError:
                    pass  # Value not in list
            else:
                min_ts = self._parse_iso8601(str(min_value))
                max_ts = self._parse_iso8601(str(max_value))

                current_min_ts = self._iso_origin_ts
                current_max_ts = self._iso_max_ts
                if (
                    self._slider_max == 0
                    or min_ts < current_min_ts
                    or max_ts > current_max_ts
                ):
                    self._configure_iso_range(
                        min_value=str(min_value),
                        max_value=str(max_value),
                        step_seconds=None,
                    )
                    self._slider.setMinimum(self._slider_min)
                    self._slider.setMaximum(self._slider_max)

                min_idx = int((min_ts - self._iso_origin_ts) / self._iso_step_seconds)
                max_idx = int(
                    math.ceil((max_ts - self._iso_origin_ts) / self._iso_step_seconds)
                )
                self._slider.setMinValue(min_idx)
                self._slider.setMaxValue(max_idx)
        else:
            # Set numeric values
            min_num = float(min_value)
            max_num = float(max_value)
            if min_num < self._min_numeric or max_num > self._max_numeric:
                resolved_min = min(min_num, max_num)
                resolved_max = max(min_num, max_num)
                self._configure_numeric_range(
                    min_val=resolved_min,
                    max_val=resolved_max,
                    step=self._step,
                )
                self._slider.setMinimum(self._slider_min)
                self._slider.setMaximum(self._slider_max)

            min_slider = self._value_to_slider(min_num)
            max_slider = self._value_to_slider(max_num)
            self._slider.setMinValue(min_slider)
            self._slider.setMaxValue(max_slider)

        self._update_labels()

    def set_values(self, values: List[str]) -> None:
        """Set ISO8601 timestamp values after widget construction.

        This method enables constructing a slider before timestamp data is available
        and switching it into ISO8601 mode once values are loaded.

        Args:
            values: List of ISO8601 timestamp strings.
        """
        self._is_iso8601 = True
        self._configure_iso_values(values)
        self._slider.setMinimum(self._slider_min)
        self._slider.setMaximum(self._slider_max)
        self.reset_range()


class TimeHistogramSliderWidget(RangeSliderWidget):
    """Drop-in ISO8601 range slider with an aggregated activity histogram.

    The widget keeps the same public API and ``rangeChanged`` signal as
    :class:`RangeSliderWidget`, but replaces the plain track with a time-based
    histogram. Mouse-wheel zooming changes the plotted time window and the
    histogram is re-aggregated for the visible window, exposing more detail as
    users zoom in. Right-click the plot to reset the plotted window.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        min_val: Optional[str] = None,
        max_val: Optional[str] = None,
        step: float = 1.0,
        values: Optional[List[str]] = None,
        label: str = "Time Range",
        show_value_tooltips: bool = False,
    ) -> None:
        self._distribution_iso_values: List[str] = values or []
        super().__init__(
            parent=parent,
            min_val=min_val,
            max_val=max_val,
            step=step,
            values=values,
            is_iso8601=True,
            label=label,
            show_value_tooltips=show_value_tooltips,
        )
        if values:
            self.set_distribution_values(values)

    def _setup_ui(self, label: str) -> None:
        """Set up the histogram time-slider user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self._label = QLabel(label)
        layout.addWidget(self._label)

        self._slider = GraphicalTimeSlider()
        self._slider.setMinimum(self._slider_min)
        self._slider.setMaximum(self._slider_max)
        self._slider.rangeChanged.connect(self._on_range_changed)
        if self._show_value_tooltips:
            self._slider.setTooltipFormatter(
                lambda slider_val: self._format_value(self._slider_to_value(slider_val))
            )
        layout.addWidget(self._slider)

        labels_container = QHBoxLayout()
        self._min_label = QLabel()
        self._max_label = QLabel()
        hint = QLabel("Wheel: zoom/re-aggregate • Right-click: reset zoom")
        hint.setStyleSheet("color: #666; font-size: 10px;")
        labels_container.addWidget(QLabel("Start:"))
        labels_container.addWidget(self._min_label)
        labels_container.addStretch()
        labels_container.addWidget(QLabel("Stop:"))
        labels_container.addWidget(self._max_label)
        layout.addLayout(labels_container)
        layout.addWidget(hint)

    def _distribution_timestamps_to_slider_values(
        self, values: List[str]
    ) -> List[float]:
        """Convert ISO8601 distribution values into current slider coordinates."""
        timestamps = []
        for value in values:
            ts = self._parse_iso8601(value)
            if self._iso_values:
                # Explicit values map to their sorted index.
                try:
                    timestamps.append(float(self._iso_values.index(value)))
                except ValueError:
                    continue
            else:
                timestamps.append((ts - self._iso_origin_ts) / self._iso_step_seconds)
        return timestamps

    def set_distribution_values(self, values: List[str]) -> None:
        """Set ISO8601 timestamps used to draw the activity histogram."""
        self._distribution_iso_values = list(values)
        if hasattr(self, "_slider"):
            self._slider.setDistributionValues(
                self._distribution_timestamps_to_slider_values(
                    self._distribution_iso_values
                )
            )

    def reset_view(self) -> None:
        """Reset the histogram zoom window to the full available time range."""
        self._slider.resetView()

    def set_values(self, values: List[str]) -> None:
        """Set available values and use them as the histogram distribution."""
        super().set_values(values)
        self.set_distribution_values(values)

    def set_available_range(
        self,
        min_value: Union[float, str],
        max_value: Union[float, str],
        step: Optional[float] = None,
    ) -> None:
        """Replace available time bounds and re-bin existing histogram data."""
        super().set_available_range(min_value, max_value, step)
        self._slider.resetView()
        self.set_distribution_values(self._distribution_iso_values)

    def set_range(
        self, min_value: Union[float, str], max_value: Union[float, str]
    ) -> None:
        """Set the selected time range and keep the histogram data in sync."""
        super().set_range(min_value, max_value)
        self.set_distribution_values(self._distribution_iso_values)
