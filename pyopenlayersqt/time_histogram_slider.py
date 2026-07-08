"""Graphical time-range slider with re-aggregating activity histogram.

The public ``TimeHistogramSliderWidget`` mirrors the ISO8601 behavior of
``RangeSliderWidget`` while replacing the plain range track with a plot that
shows when timestamped data is present. It has four draggable time bars:

* orange extent bars choose the time window used to aggregate the plot;
* blue filter bars choose the emitted start/stop filter range.

Dragging the highlighted blue filter span moves it as a fixed-width selection.
Mouse-wheel zoom changes the extent around the cursor, and every extent change
recomputes histogram bins for the newly visible window. The wrapper keeps
continuous min/max ISO ranges at one-second resolution by default so zooming can
actually produce smaller time buckets instead of being capped by a coarse
automatically chosen range-slider step.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, List, Optional, Tuple, Union

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolTip, QVBoxLayout, QWidget

from .range_slider import RangeSliderWidget


class GraphicalTimeSlider(QWidget):
    """Histogram-backed four-handle time slider."""

    rangeChanged = Signal(int, int)
    extentChanged = Signal(int, int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 100
        self._extent_min = 0
        self._extent_max = 100
        self._min_value = 0
        self._max_value = 100
        self._timestamps: List[float] = []
        self._bins: List[Tuple[int, int, int]] = []
        self._dragging_handle: Optional[str] = None
        self._drag_start_value: Optional[int] = None
        self._drag_initial_min: Optional[int] = None
        self._drag_initial_max: Optional[int] = None
        self._drag_initial_extent_min: Optional[int] = None
        self._drag_initial_extent_max: Optional[int] = None
        self._last_bin_size = 1
        self._handle_hit_width = 10
        self._tooltip_formatter: Optional[Callable[[int], str]] = None
        self._axis_formatter: Optional[Callable[[int], str]] = None
        self._show_x_axis = True
        self.setMinimumHeight(170)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

    def setTooltipFormatter(self, formatter: Optional[Callable[[int], str]]) -> None:
        """Set value formatter used by tooltips."""
        self._tooltip_formatter = formatter

    def setAxisFormatter(self, formatter: Optional[Callable[[int], str]]) -> None:
        """Set formatter used for x-axis tick labels."""
        self._axis_formatter = formatter
        self.update()

    def setShowXAxis(self, show: bool) -> None:
        """Set whether date/time x-axis ticks are drawn below the histogram."""
        self._show_x_axis = show
        self.update()

    def setDistributionValues(self, timestamps: List[float]) -> None:
        """Set timestamp values, expressed in parent slider coordinates."""
        self._timestamps = sorted(timestamps)
        self._reaggregate()
        self.update()

    def setMinimum(self, value: int) -> None:
        """Set the available minimum slider coordinate."""
        self._minimum = value
        self._extent_min = max(self._extent_min, value)
        if self._extent_max <= self._extent_min:
            self._extent_max = self._maximum
        self.setMinValue(max(self._min_value, value))
        self._reaggregate()

    def setMaximum(self, value: int) -> None:
        """Set the available maximum slider coordinate."""
        old_maximum = self._maximum
        self._maximum = value
        if self._extent_max == old_maximum or self._extent_max > value:
            self._extent_max = value
        if self._extent_min >= self._extent_max:
            self._extent_min = self._minimum
        self.setMaxValue(min(self._max_value, value))
        self._reaggregate()

    def minValue(self) -> int:
        """Return selected filter minimum."""
        return self._min_value

    def maxValue(self) -> int:
        """Return selected filter maximum."""
        return self._max_value

    def setMinValue(self, value: int) -> None:
        """Set selected filter minimum."""
        value = max(self._minimum, min(value, self._max_value))
        if value != self._min_value:
            self._min_value = value
            self.update()
            self.rangeChanged.emit(self._min_value, self._max_value)

    def setMaxValue(self, value: int) -> None:
        """Set selected filter maximum."""
        value = min(self._maximum, max(value, self._min_value))
        if value != self._max_value:
            self._max_value = value
            self.update()
            self.rangeChanged.emit(self._min_value, self._max_value)

    def setExtentRange(self, min_value: int, max_value: int) -> None:
        """Set aggregation/zoom extent and re-bin the plot."""
        if max_value <= min_value:
            return
        self._extent_min = max(self._minimum, min_value)
        self._extent_max = min(self._maximum, max_value)
        if self._extent_max <= self._extent_min:
            self._extent_min = self._minimum
            self._extent_max = self._maximum
        self._reaggregate()
        self.update()
        self.extentChanged.emit(self._extent_min, self._extent_max)

    def resetExtent(self) -> None:
        """Reset the aggregation extent to the full available range."""
        self.setExtentRange(self._minimum, self._maximum)

    def _plot_rect(self) -> QRect:
        margin = 14
        reserved_height = 72 if self._show_x_axis else 50
        return QRect(
            margin,
            8,
            max(1, self.width() - 2 * margin),
            max(1, self.height() - reserved_height),
        )

    def _overview_rect(self) -> QRect:
        plot = self._plot_rect()
        gap = 40 if self._show_x_axis else 18
        return QRect(plot.left(), plot.bottom() + gap, plot.width(), 8)

    def _extent_value_to_pos(self, value: int) -> int:
        rect = self._plot_rect()
        if self._extent_max == self._extent_min:
            return rect.left()
        ratio = (value - self._extent_min) / (self._extent_max - self._extent_min)
        return rect.left() + int(max(0.0, min(1.0, ratio)) * rect.width())

    def _extent_pos_to_value(self, pos: int) -> int:
        rect = self._plot_rect()
        ratio = max(0.0, min(1.0, (pos - rect.left()) / max(rect.width(), 1)))
        return self._extent_min + int(ratio * (self._extent_max - self._extent_min))

    def _domain_value_to_pos(self, value: int) -> int:
        rect = self._overview_rect()
        if self._maximum == self._minimum:
            return rect.left()
        ratio = (value - self._minimum) / (self._maximum - self._minimum)
        return rect.left() + int(max(0.0, min(1.0, ratio)) * rect.width())

    def _domain_pos_to_value(self, pos: int) -> int:
        rect = self._overview_rect()
        ratio = max(0.0, min(1.0, (pos - rect.left()) / max(rect.width(), 1)))
        return self._minimum + int(ratio * (self._maximum - self._minimum))

    def _handle_at_pos(self, pos) -> Optional[str]:
        plot = self._plot_rect()
        overview = self._overview_rect()
        for name, value in (
            ("filter_min", self._min_value),
            ("filter_max", self._max_value),
        ):
            x = self._extent_value_to_pos(value)
            if QRect(
                x - self._handle_hit_width,
                plot.top(),
                self._handle_hit_width * 2,
                plot.height() + 10,
            ).contains(pos):
                return name
        if min(
            self._extent_value_to_pos(self._min_value),
            self._extent_value_to_pos(self._max_value),
        ) <= pos.x() <= max(
            self._extent_value_to_pos(self._min_value),
            self._extent_value_to_pos(self._max_value),
        ) and plot.contains(
            pos
        ):
            return "filter_span"
        for name, value in (
            ("extent_min", self._extent_min),
            ("extent_max", self._extent_max),
        ):
            x = self._domain_value_to_pos(value)
            if QRect(
                x - self._handle_hit_width,
                overview.top() - 8,
                self._handle_hit_width * 2,
                24,
            ).contains(pos):
                return name
        extent_left = self._domain_value_to_pos(self._extent_min)
        extent_right = self._domain_value_to_pos(self._extent_max)
        if QRect(
            min(extent_left, extent_right),
            overview.top() - 6,
            abs(extent_right - extent_left),
            overview.height() + 12,
        ).contains(pos):
            return "extent_span"
        return None

    def _show_tooltip(self, value: int) -> None:
        if self._tooltip_formatter is None:
            return
        QToolTip.showText(
            self.mapToGlobal(self._plot_rect().center()),
            self._tooltip_formatter(value),
            self,
            QRect(),
            1800,
        )

    def _reaggregate(self) -> None:
        width_bins = max(4, min(360, self._plot_rect().width() // 3))
        span = max(self._extent_max - self._extent_min, 1)
        bin_size = max(1, -(-span // width_bins))
        self._last_bin_size = bin_size
        counts = {}
        for ts in self._timestamps:
            if self._extent_min <= ts <= self._extent_max:
                offset = ts - self._extent_min
                if ts == self._extent_max:
                    # Keep a sample exactly on the max boundary in the final
                    # real bin instead of assigning it to a zero-width bin that
                    # starts at _extent_max and is never drawn.
                    offset = max(0.0, self._extent_max - self._extent_min - 1e-9)
                start = self._extent_min + int(offset // bin_size) * bin_size
                counts[start] = counts.get(start, 0) + 1

        # Build a complete sequence of bins for the current zoom extent rather
        # than only the bins with data. This makes every extent change redraw the
        # plot at the new fidelity, including gaps between active periods.
        self._bins = []
        bin_start = self._extent_min
        while bin_start <= self._extent_max:
            bin_end = min(bin_start + bin_size, self._extent_max)
            self._bins.append((bin_start, bin_end, counts.get(bin_start, 0)))
            if bin_end == self._extent_max:
                break
            bin_start = bin_end

    def _draw_x_axis(self, painter: QPainter, plot: QRect) -> None:
        """Draw date/time tick marks for the currently visible histogram extent."""
        if not self._show_x_axis or self._axis_formatter is None:
            return

        painter.setPen(QPen(QColor(90, 90, 90), 1))
        axis_y = plot.bottom() + 5
        painter.drawLine(plot.left(), axis_y, plot.right(), axis_y)

        tick_count = 5
        for i in range(tick_count):
            ratio = i / max(tick_count - 1, 1)
            value = int(
                self._extent_min + ratio * (self._extent_max - self._extent_min)
            )
            x = self._extent_value_to_pos(value)
            painter.drawLine(x, axis_y, x, axis_y + 4)
            label = self._axis_formatter(value)
            label_rect = QRect(x - 48, axis_y + 6, 96, 16)
            painter.drawText(label_rect, Qt.AlignHCenter | Qt.AlignTop, label)

    def paintEvent(self, _event: QPaintEvent) -> None:
        """Draw histogram, filter handles, and extent handles."""
        painter = QPainter()
        if not painter.begin(self):
            return
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            plot = self._plot_rect()
            overview = self._overview_rect()

            painter.setPen(QPen(QColor(210, 210, 210), 1))
            painter.setBrush(QColor(248, 250, 252))
            painter.drawRoundedRect(plot, 4, 4)

            max_count = max(1, max((count for _, _, count in self._bins), default=0))
            painter.setPen(Qt.NoPen)
            for start, end, count in self._bins:
                x1 = self._extent_value_to_pos(start)
                x2 = max(x1 + 1, self._extent_value_to_pos(end))
                height = int((count / max_count) * (plot.height() - 8))
                painter.setBrush(QColor(94, 151, 246, 180))
                painter.drawRect(
                    QRect(x1, plot.bottom() - height, max(1, x2 - x1 - 1), height)
                )

            filter_left = self._extent_value_to_pos(self._min_value)
            filter_right = self._extent_value_to_pos(self._max_value)
            painter.setBrush(QColor(70, 130, 180, 55))
            painter.drawRect(
                QRect(
                    filter_left,
                    plot.top(),
                    max(0, filter_right - filter_left),
                    plot.height(),
                )
            )
            painter.setPen(QPen(QColor(25, 100, 180), 3))
            for x in (filter_left, filter_right):
                painter.drawLine(x, plot.top(), x, plot.bottom() + 8)

            self._draw_x_axis(painter, plot)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(220, 220, 220))
            painter.drawRoundedRect(overview, 4, 4)
            extent_left = self._domain_value_to_pos(self._extent_min)
            extent_right = self._domain_value_to_pos(self._extent_max)
            painter.setBrush(QColor(245, 145, 40, 90))
            painter.drawRect(
                QRect(
                    extent_left,
                    overview.top() - 2,
                    max(1, extent_right - extent_left),
                    overview.height() + 4,
                )
            )
            painter.setPen(QPen(QColor(215, 110, 20), 3))
            for x in (extent_left, extent_right):
                painter.drawLine(x, overview.top() - 8, x, overview.bottom() + 8)
        finally:
            painter.end()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reaggregate()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.RightButton:
            self.resetExtent()
            return
        if event.button() != Qt.LeftButton:
            return
        self._dragging_handle = self._handle_at_pos(event.pos())
        if self._dragging_handle is None:
            self._dragging_handle = (
                "filter_min"
                if event.pos().x() < self._extent_value_to_pos(self._min_value)
                else "filter_max"
            )
        if self._dragging_handle in ("extent_min", "extent_max", "extent_span"):
            self._drag_start_value = self._domain_pos_to_value(event.pos().x())
        else:
            self._drag_start_value = self._extent_pos_to_value(event.pos().x())
        self._drag_initial_min = self._min_value
        self._drag_initial_max = self._max_value
        self._drag_initial_extent_min = self._extent_min
        self._drag_initial_extent_max = self._extent_max
        self._apply_drag(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging_handle is not None:
            self._apply_drag(event)
        else:
            self.setCursor(
                Qt.PointingHandCursor
                if self._handle_at_pos(event.pos())
                else Qt.ArrowCursor
            )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging_handle = None
            self._drag_start_value = None
            self._drag_initial_min = None
            self._drag_initial_max = None
            self._drag_initial_extent_min = None
            self._drag_initial_extent_max = None
            QToolTip.hideText()

    def wheelEvent(self, event) -> None:
        cursor_value = self._extent_pos_to_value(
            event.position().x() if hasattr(event, "position") else event.pos().x()
        )
        span = max(1, self._extent_max - self._extent_min)
        zoom_factor = 0.75 if event.angleDelta().y() > 0 else 1.35
        new_span = int(max(1, min(self._maximum - self._minimum, span * zoom_factor)))
        ratio = (cursor_value - self._extent_min) / span
        new_min = int(cursor_value - ratio * new_span)
        new_max = new_min + new_span
        if new_min < self._minimum:
            new_min = self._minimum
            new_max = new_min + new_span
        if new_max > self._maximum:
            new_max = self._maximum
            new_min = new_max - new_span
        self.setExtentRange(new_min, new_max)
        event.accept()

    def _apply_drag(self, event: QMouseEvent) -> None:
        handle = self._dragging_handle
        if handle in ("extent_min", "extent_max", "extent_span"):
            value = self._domain_pos_to_value(event.pos().x())
            if handle == "extent_min":
                self.setExtentRange(value, self._extent_max)
            elif handle == "extent_max":
                self.setExtentRange(self._extent_min, value)
            elif (
                self._drag_start_value is not None
                and self._drag_initial_extent_min is not None
                and self._drag_initial_extent_max is not None
            ):
                delta = value - self._drag_start_value
                span = self._drag_initial_extent_max - self._drag_initial_extent_min
                new_min = self._drag_initial_extent_min + delta
                new_max = self._drag_initial_extent_max + delta
                if new_min < self._minimum:
                    new_min = self._minimum
                    new_max = new_min + span
                if new_max > self._maximum:
                    new_max = self._maximum
                    new_min = new_max - span
                self.setExtentRange(int(new_min), int(new_max))
            self._show_tooltip(value)
            return

        value = self._extent_pos_to_value(event.pos().x())
        if handle == "filter_min":
            self.setMinValue(value)
        elif handle == "filter_max":
            self.setMaxValue(value)
        elif handle == "filter_span" and self._drag_start_value is not None:
            delta = value - self._drag_start_value
            initial_min = (
                self._drag_initial_min
                if self._drag_initial_min is not None
                else self._min_value
            )
            initial_max = (
                self._drag_initial_max
                if self._drag_initial_max is not None
                else self._max_value
            )
            span = initial_max - initial_min
            new_min = initial_min + delta
            new_max = initial_max + delta
            if new_min < self._minimum:
                new_min = self._minimum
                new_max = new_min + span
            if new_max > self._maximum:
                new_max = self._maximum
                new_min = new_max - span
            changed = new_min != self._min_value or new_max != self._max_value
            self._min_value = int(new_min)
            self._max_value = int(new_max)
            if changed:
                self.update()
                self.rangeChanged.emit(self._min_value, self._max_value)
        self._show_tooltip(value)


class TimeHistogramSliderWidget(RangeSliderWidget):
    """Drop-in ISO8601 range slider with an aggregated activity histogram."""

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
        show_x_axis: bool = True,
    ) -> None:
        self._distribution_iso_values: List[str] = values or []
        self._show_x_axis = show_x_axis
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        self._label = QLabel(label)
        layout.addWidget(self._label)

        self._slider = GraphicalTimeSlider()
        self._slider.setMinimum(self._slider_min)
        self._slider.setMaximum(self._slider_max)
        self._slider.setShowXAxis(self._show_x_axis)
        self._slider.setAxisFormatter(self._format_axis_value)
        self._slider.rangeChanged.connect(self._on_range_changed)
        self._slider.extentChanged.connect(self._on_extent_changed)
        if self._show_value_tooltips:
            self._slider.setTooltipFormatter(
                lambda slider_val: self._format_value(self._slider_to_value(slider_val))
            )
        layout.addWidget(self._slider)

        self._extent_label = QLabel()
        self._extent_label.setStyleSheet("color: #7a3f00; padding: 2px;")
        layout.addWidget(self._extent_label)

        labels_container = QHBoxLayout()
        self._min_label = QLabel()
        self._max_label = QLabel()
        filter_title = QLabel("Filter range:")
        filter_title.setStyleSheet("font-weight: bold; color: #195b9b;")
        hint = QLabel(
            "Orange handles adjust the histogram view; blue handles adjust the filter."
        )
        hint.setStyleSheet("color: #666; font-size: 10px;")
        labels_container.addWidget(filter_title)
        labels_container.addWidget(QLabel("Start:"))
        labels_container.addWidget(self._min_label)
        labels_container.addStretch()
        labels_container.addWidget(QLabel("Stop:"))
        labels_container.addWidget(self._max_label)
        layout.addLayout(labels_container)
        layout.addWidget(hint)

    def _on_extent_changed(self, _min_slider_val: int, _max_slider_val: int) -> None:
        """Update zoom/aggregation labels when the orange extent changes."""
        self._update_extent_label()

    def _update_labels(self) -> None:
        """Update filter labels and the zoom extent label."""
        super()._update_labels()
        self._update_extent_label()

    def _format_axis_value(self, slider_value: int) -> str:
        """Format a slider value as a compact date/time axis tick."""
        numeric_value = self._slider_to_value(slider_value)
        if not self._is_iso8601:
            return self._format_value(numeric_value)
        if self._iso_values:
            return self._format_value(numeric_value)
        timestamp = min(
            self._iso_origin_ts + (numeric_value * self._iso_step_seconds),
            self._iso_max_ts,
        )
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return dt.strftime("%m-%d %H:%M")

    def _format_duration(self, seconds: float) -> str:
        """Format an approximate duration for the current histogram bin size."""
        seconds = max(float(seconds), 0.0)
        if seconds < 60:
            return f"{seconds:.0f}s"
        minutes = seconds / 60
        if minutes < 60:
            return f"{minutes:.1f}m" if minutes < 10 else f"{minutes:.0f}m"
        hours = minutes / 60
        if hours < 48:
            return f"{hours:.1f}h" if hours < 10 else f"{hours:.0f}h"
        days = hours / 24
        return f"{days:.1f}d" if days < 10 else f"{days:.0f}d"

    def _update_extent_label(self) -> None:
        """Show the zoom extent that defines the histogram above."""
        if not hasattr(self, "_extent_label") or not hasattr(self, "_slider"):
            return
        extent_min = self._slider._extent_min
        extent_max = self._slider._extent_max
        extent_start = self._format_value(self._slider_to_value(extent_min))
        extent_stop = self._format_value(self._slider_to_value(extent_max))
        bin_seconds = self._slider._last_bin_size * (
            self._iso_step_seconds if self._is_iso8601 and not self._iso_values else 1.0
        )
        self._extent_label.setText(
            f"View: {extent_start} → {extent_stop}  "
            f"Bin: ≈ {self._format_duration(bin_seconds)}"
        )

    def _distribution_timestamps_to_slider_values(
        self, values: List[str]
    ) -> List[float]:
        timestamps = []
        for value in values:
            ts = self._parse_iso8601(value)
            if self._iso_values:
                try:
                    timestamps.append(float(self._iso_values.index(value)))
                except ValueError:
                    continue
            else:
                timestamps.append((ts - self._iso_origin_ts) / self._iso_step_seconds)
        return timestamps

    def set_distribution_values(self, values: List[str]) -> None:
        """Set ISO8601 timestamps used to draw the activity plot."""
        self._distribution_iso_values = list(values)
        if hasattr(self, "_slider"):
            self._slider.setDistributionValues(
                self._distribution_timestamps_to_slider_values(
                    self._distribution_iso_values
                )
            )
            self._update_extent_label()

    def reset_view(self) -> None:
        """Reset the aggregation/zoom extent to the full available time range."""
        self._slider.resetExtent()
        self._update_extent_label()

    def set_values(self, values: List[str]) -> None:
        super().set_values(values)
        self.set_distribution_values(values)

    def set_available_range(
        self,
        min_value: Union[float, str],
        max_value: Union[float, str],
        step: Optional[float] = None,
    ) -> None:
        # Unlike the plain range slider, the graphical histogram needs the
        # coordinate system to retain enough temporal precision for subsequent
        # zooms. Default to one-second buckets unless callers explicitly request
        # a coarser step.
        super().set_available_range(min_value, max_value, 1.0 if step is None else step)
        self._slider.resetExtent()
        self.set_distribution_values(self._distribution_iso_values)

    def set_range(
        self, min_value: Union[float, str], max_value: Union[float, str]
    ) -> None:
        super().set_range(min_value, max_value)
        self.set_distribution_values(self._distribution_iso_values)
