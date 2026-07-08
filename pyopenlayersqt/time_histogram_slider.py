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
from typing import Callable, List, Optional, Sequence, Tuple, Union

import numpy as np
from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPaintEvent, QPainter, QPalette, QPen
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
        self._timestamps = np.empty(0, dtype=np.float64)
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

    def setDistributionValues(self, timestamps: Sequence[float]) -> None:
        """Set timestamp values, expressed in parent slider coordinates."""
        values = np.asarray(timestamps, dtype=np.float64)
        values = values[np.isfinite(values)]
        self._timestamps = np.sort(values)
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

        edges = np.arange(
            self._extent_min,
            self._extent_max,
            bin_size,
            dtype=np.float64,
        )
        if edges.size == 0 or edges[0] != self._extent_min:
            edges = np.insert(edges, 0, float(self._extent_min))
        if edges[-1] != self._extent_max:
            edges = np.append(edges, float(self._extent_max))
        if edges.size < 2:
            edges = np.asarray([self._extent_min, self._extent_max], dtype=np.float64)

        if self._timestamps.size:
            lower = np.searchsorted(self._timestamps, edges[:-1], side="left")
            upper = np.searchsorted(self._timestamps, edges[1:], side="left")
            # Include samples exactly on the visible maximum in the final bin.
            upper[-1] = np.searchsorted(self._timestamps, edges[-1], side="right")
            counts = upper - lower
        else:
            counts = np.zeros(edges.size - 1, dtype=np.int64)

        self._bins = [
            (int(edges[i]), int(edges[i + 1]), int(counts[i]))
            for i in range(len(counts))
        ]

    def _is_dark_mode(self) -> bool:
        """Return whether the widget palette is currently dark."""
        return self.palette().color(QPalette.ColorRole.Window).lightness() < 128

    def _color(self, role: str) -> QColor:
        """Return high-contrast colors for light and dark palettes."""
        dark = self._is_dark_mode()
        colors = {
            "plot_border": QColor("#475569") if dark else QColor("#cbd5e1"),
            "plot_bg": QColor("#0b1220") if dark else QColor("#f8fafc"),
            "axis": QColor("#cbd5e1") if dark else QColor("#5b6472"),
            "bar": QColor(56, 189, 248, 220) if dark else QColor(94, 151, 246, 180),
            "filter_fill": (
                QColor(59, 130, 246, 90) if dark else QColor(70, 130, 180, 55)
            ),
            "filter_line": QColor("#60a5fa") if dark else QColor("#1964b4"),
            "overview_bg": QColor("#1e293b") if dark else QColor("#dcdcdc"),
            "extent_fill": (
                QColor(251, 146, 60, 130) if dark else QColor(245, 145, 40, 90)
            ),
            "extent_line": QColor("#fdba74") if dark else QColor("#d76e14"),
        }
        return colors[role]

    def _draw_x_axis(self, painter: QPainter, plot: QRect) -> None:
        """Draw date/time tick marks for the currently visible histogram extent."""
        if not self._show_x_axis or self._axis_formatter is None:
            return

        painter.setPen(QPen(self._color("axis"), 1))
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
            if i == 0:
                label_rect = QRect(plot.left(), axis_y + 6, 110, 16)
                alignment = Qt.AlignLeft | Qt.AlignTop
            elif i == tick_count - 1:
                label_rect = QRect(plot.right() - 110, axis_y + 6, 110, 16)
                alignment = Qt.AlignRight | Qt.AlignTop
            else:
                label_rect = QRect(x - 55, axis_y + 6, 110, 16)
                alignment = Qt.AlignHCenter | Qt.AlignTop
            painter.drawText(label_rect, alignment, label)

    def paintEvent(self, _event: QPaintEvent) -> None:
        """Draw histogram, filter handles, and extent handles."""
        painter = QPainter()
        if not painter.begin(self):
            return
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            plot = self._plot_rect()
            overview = self._overview_rect()

            painter.setPen(QPen(self._color("plot_border"), 1))
            painter.setBrush(self._color("plot_bg"))
            painter.drawRoundedRect(plot, 4, 4)

            max_count = max(1, max((count for _, _, count in self._bins), default=0))
            painter.setPen(Qt.NoPen)
            for start, end, count in self._bins:
                x1 = self._extent_value_to_pos(start)
                x2 = max(x1 + 1, self._extent_value_to_pos(end))
                height = int((count / max_count) * (plot.height() - 8))
                painter.setBrush(self._color("bar"))
                painter.drawRect(
                    QRect(x1, plot.bottom() - height, max(1, x2 - x1 - 1), height)
                )

            filter_left = self._extent_value_to_pos(self._min_value)
            filter_right = self._extent_value_to_pos(self._max_value)
            painter.setBrush(self._color("filter_fill"))
            painter.drawRect(
                QRect(
                    filter_left,
                    plot.top(),
                    max(0, filter_right - filter_left),
                    plot.height(),
                )
            )
            painter.setPen(QPen(self._color("filter_line"), 3))
            for x in (filter_left, filter_right):
                painter.drawLine(x, plot.top(), x, plot.bottom() + 8)

            self._draw_x_axis(painter, plot)

            painter.setPen(Qt.NoPen)
            painter.setBrush(self._color("overview_bg"))
            painter.drawRoundedRect(overview, 4, 4)
            extent_left = self._domain_value_to_pos(self._extent_min)
            extent_right = self._domain_value_to_pos(self._extent_max)
            painter.setBrush(self._color("extent_fill"))
            painter.drawRect(
                QRect(
                    extent_left,
                    overview.top() - 2,
                    max(1, extent_right - extent_left),
                    overview.height() + 4,
                )
            )
            painter.setPen(QPen(self._color("extent_line"), 3))
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
        show_global_range_label: bool = False,
        show_view_label: bool = False,
    ) -> None:
        self._distribution_iso_values: List[str] = values or []
        self._show_x_axis = show_x_axis
        self._show_global_range_label = show_global_range_label
        self._show_view_label = show_view_label
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
        self._extent_label.setStyleSheet("padding: 2px;")
        self._extent_label.setVisible(self._show_view_label)
        layout.addWidget(self._extent_label)

        self._global_label = QLabel()
        self._global_label.setStyleSheet("color: #666; padding: 0 2px;")
        self._global_label.setVisible(self._show_global_range_label)
        layout.addWidget(self._global_label)

        labels_container = QHBoxLayout()
        self._min_label = QLabel()
        self._max_label = QLabel()
        filter_title = QLabel("Filter range:")
        filter_title.setStyleSheet("font-weight: bold;")
        labels_container.addWidget(filter_title)
        labels_container.addWidget(QLabel("Start:"))
        labels_container.addWidget(self._min_label)
        labels_container.addStretch()
        labels_container.addWidget(QLabel("Stop:"))
        labels_container.addWidget(self._max_label)
        layout.addLayout(labels_container)

    def _on_extent_changed(self, _min_slider_val: int, _max_slider_val: int) -> None:
        """Update zoom/aggregation labels when the orange extent changes."""
        self._update_extent_label()

    def _update_labels(self) -> None:
        """Update filter, zoom extent, and global range labels."""
        super()._update_labels()
        self._update_extent_label()
        self._update_global_label()

    def _update_global_label(self) -> None:
        """Show the full available min/max time domain when enabled."""
        if not hasattr(self, "_global_label") or not self._show_global_range_label:
            return
        domain_start = self._format_value(self._slider_to_value(self._slider_min))
        domain_stop = self._format_value(self._slider_to_value(self._slider_max))
        self._global_label.setText(f"Full range: {domain_start} → {domain_stop}")

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
        if (
            not hasattr(self, "_extent_label")
            or not hasattr(self, "_slider")
            or not self._show_view_label
        ):
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
            self._update_global_label()

    def set_distribution_epoch_seconds(self, timestamps: Sequence[float]) -> None:
        """Set histogram distribution values from Unix epoch seconds.

        This avoids formatting large timestamp arrays to ISO8601 strings before
        passing them to the widget. It is useful for CSV/table workflows that
        already store parsed timestamps as numeric epoch seconds.
        """
        if self._iso_values:
            iso_values = [self._timestamp_to_iso8601(float(ts)) for ts in timestamps]
            self.set_distribution_values(iso_values)
            return
        timestamp_values = np.asarray(timestamps, dtype=np.float64)
        slider_values = (
            timestamp_values - self._iso_origin_ts
        ) / self._iso_step_seconds
        self._distribution_iso_values = []
        if hasattr(self, "_slider"):
            self._slider.setDistributionValues(slider_values)
            self._update_extent_label()
            self._update_global_label()

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
        self._update_global_label()
        self.set_distribution_values(self._distribution_iso_values)

    def set_range(
        self, min_value: Union[float, str], max_value: Union[float, str]
    ) -> None:
        super().set_range(min_value, max_value)
        self.set_distribution_values(self._distribution_iso_values)
