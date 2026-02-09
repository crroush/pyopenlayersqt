"""Reusable high-performance plotting widget built with PySide6 Qt Charts.

This widget complements :class:`FeatureTableWidget` and :class:`OLMapWidget` by
providing native Qt plotting with fast updates, rectangle selection, and map
highlight signaling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
from PySide6 import QtCore
from PySide6.QtCharts import QChart, QChartView, QDateTimeAxis, QLineSeries, QScatterSeries, QValueAxis
from PySide6.QtCore import QDateTime, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtWidgets import QRubberBand, QVBoxLayout, QWidget

FeatureKey = Tuple[str, str]
ColorValue = Union[str, QColor, tuple[int, int, int], tuple[int, int, int, int]]


def _to_qcolor(color: ColorValue) -> QColor:
    """Normalize library color inputs (QColor/name/hex/tuple) to QColor."""
    if isinstance(color, QColor):
        return QColor(color)
    if isinstance(color, str):
        return QColor(color)
    if isinstance(color, tuple) and len(color) == 3:
        return QColor(int(color[0]), int(color[1]), int(color[2]))
    if isinstance(color, tuple) and len(color) == 4:
        return QColor(int(color[0]), int(color[1]), int(color[2]), int(color[3]))
    raise TypeError(f"Unsupported color type: {type(color)}")


@dataclass(frozen=True)
class PlotPointRef:
    """Reference to one point in a trace."""

    trace_id: str
    index: int


@dataclass
class TraceStyle:
    """Visual style for a trace."""

    color: ColorValue = "dodgerblue"
    marker_size: float = 8.0
    line_width: float = 2.0
    selected_color: ColorValue = "orange"
    selected_marker_size: float = 11.0


@dataclass
class TraceData:
    """Internal trace storage."""

    trace_id: str
    x: np.ndarray
    y: np.ndarray
    style: TraceStyle
    mode: str = "scatter"  # scatter | line | both
    timestamps: Optional[np.ndarray] = None
    feature_keys: Optional[List[FeatureKey]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    active_mask: Optional[np.ndarray] = None
    selected_mask: Optional[np.ndarray] = None
    line_series: Optional[QLineSeries] = None
    scatter_series: Optional[QScatterSeries] = None
    selected_series: Optional[QScatterSeries] = None


class _SelectionChartView(QChartView):
    """Chart view with rectangle box selection callback."""

    boxSelected = QtCore.Signal(float, float, float, float, bool)  # x1, x2, y1, y2, additive

    def __init__(self, chart: QChart, parent: Optional[QWidget] = None) -> None:
        super().__init__(chart, parent)
        self._rubber = QRubberBand(QRubberBand.Rectangle, self)
        self._origin = QtCore.QPoint()
        self._dragging = False

        self.setRenderHint(QPainter.Antialiasing, True)
        self.setMouseTracking(True)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._origin = event.position().toPoint()
            self._rubber.setGeometry(QRect(self._origin, QtCore.QSize()))
            self._rubber.show()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            rect = QRect(self._origin, event.position().toPoint()).normalized()
            self._rubber.setGeometry(rect)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            rect = self._rubber.geometry().normalized()
            self._rubber.hide()
            if rect.width() >= 2 and rect.height() >= 2:
                chart = self.chart()
                tl = chart.mapToValue(rect.topLeft())
                br = chart.mapToValue(rect.bottomRight())
                x1, x2 = sorted((tl.x(), br.x()))
                y1, y2 = sorted((tl.y(), br.y()))
                additive = bool(event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier))
                self.boxSelected.emit(x1, x2, y1, y2, additive)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class PlotWidget(QWidget):
    """Qt Charts plotting widget with selection, filtering, and map sync signals."""

    selectionChanged = QtCore.Signal(object)  # List[PlotPointRef]
    highlightFeatureKeys = QtCore.Signal(object)  # List[FeatureKey]
    traceDataChanged = QtCore.Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._chart = QChart()
        self._chart.legend().setVisible(True)

        self._axis_x_value = QValueAxis()
        self._axis_x_datetime = QDateTimeAxis()
        self._axis_x_datetime.setFormat("yyyy-MM-dd HH:mm:ss")
        self._axis_x_datetime.setTickCount(6)
        self._x_axis_mode = "value"  # value | datetime

        self._axis_x = self._axis_x_value
        self._axis_y = QValueAxis()
        self._chart.addAxis(self._axis_x, Qt.AlignBottom)
        self._chart.addAxis(self._axis_y, Qt.AlignLeft)

        self._view = _SelectionChartView(self._chart)
        self._view.boxSelected.connect(self._on_box_select)

        self._traces: Dict[str, TraceData] = {}
        self._selected: List[PlotPointRef] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    def clear(self) -> None:
        """Remove all traces and clear plot state."""
        for trace in self._traces.values():
            self._detach_trace(trace)
        self._traces.clear()
        self._selected.clear()
        self.selectionChanged.emit([])
        self.highlightFeatureKeys.emit([])
        self._update_axes()

    def add_trace(
        self,
        trace_id: str,
        x: Sequence[float],
        y: Sequence[float],
        *,
        mode: str = "scatter",
        style: Optional[TraceStyle] = None,
        timestamps: Optional[Sequence[float]] = None,
        feature_keys: Optional[Sequence[FeatureKey]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a trace (scatter, line, or both)."""
        if mode not in {"scatter", "line", "both"}:
            raise ValueError("mode must be one of: scatter, line, both")
        if trace_id in self._traces:
            raise ValueError(f"Trace '{trace_id}' already exists")

        x_arr = np.asarray(x, dtype=float)
        y_arr = np.asarray(y, dtype=float)
        if x_arr.shape != y_arr.shape:
            raise ValueError("x and y must have the same shape")

        n = x_arr.size
        ts_arr = None
        if timestamps is not None:
            ts_arr = np.asarray(timestamps, dtype=float)
            if ts_arr.shape != x_arr.shape:
                raise ValueError("timestamps must match x/y shape")

        keys = None
        if feature_keys is not None:
            keys = [(str(layer_id), str(feature_id)) for layer_id, feature_id in feature_keys]
            if len(keys) != n:
                raise ValueError("feature_keys length must match x/y")

        trace = TraceData(
            trace_id=str(trace_id),
            x=x_arr,
            y=y_arr,
            style=style or TraceStyle(),
            mode=mode,
            timestamps=ts_arr,
            feature_keys=keys,
            metadata=dict(metadata or {}),
            active_mask=np.ones(n, dtype=bool),
            selected_mask=np.zeros(n, dtype=bool),
        )
        self._traces[trace.trace_id] = trace
        self._sync_x_axis_mode()
        self._create_series(trace)
        self._refresh_trace_series(trace)
        self._update_axes()

    def set_time_window(self, start: float, end: float) -> None:
        """Apply timestamp window to traces that include timestamps."""
        lo, hi = (start, end) if start <= end else (end, start)
        for trace in self._traces.values():
            if trace.timestamps is None:
                continue
            trace.active_mask = (trace.timestamps >= lo) & (trace.timestamps <= hi)
            trace.selected_mask &= trace.active_mask
            self._refresh_trace_series(trace)
            self.traceDataChanged.emit(trace.trace_id)
        self._sync_selected_refs_from_masks()
        self._emit_selection_signals()
        self._update_axes()

    def clear_time_filter(self) -> None:
        """Reset time filter on all timestamp-enabled traces."""
        for trace in self._traces.values():
            if trace.timestamps is None:
                continue
            trace.active_mask = np.ones_like(trace.x, dtype=bool)
            self._refresh_trace_series(trace)
            self.traceDataChanged.emit(trace.trace_id)
        self._sync_x_axis_mode()
        self._update_axes()

    def recolor_selected(self, color: ColorValue) -> None:
        """Recolor selected points by changing selected-marker color per trace."""
        if not self._selected:
            return
        selected_color = _to_qcolor(color)
        touched: set[str] = set()
        for ref in self._selected:
            trace = self._traces.get(ref.trace_id)
            if trace is None:
                continue
            trace.style.selected_color = selected_color
            touched.add(ref.trace_id)
        for trace_id in touched:
            self._refresh_trace_series(self._traces[trace_id])
            self.traceDataChanged.emit(trace_id)

    def delete_selected(self) -> None:
        """Delete all selected samples from traces."""
        if not self._selected:
            return

        touched: set[str] = set()
        for trace_id, trace in self._traces.items():
            keep = ~trace.selected_mask
            if np.all(keep):
                continue
            touched.add(trace_id)

            trace.x = trace.x[keep]
            trace.y = trace.y[keep]
            trace.active_mask = trace.active_mask[keep]
            trace.selected_mask = np.zeros(trace.x.size, dtype=bool)
            if trace.timestamps is not None:
                trace.timestamps = trace.timestamps[keep]
            if trace.feature_keys is not None:
                trace.feature_keys = [k for i, k in enumerate(trace.feature_keys) if keep[i]]

            self._refresh_trace_series(trace)

        self._selected = []
        self.selectionChanged.emit([])
        self.highlightFeatureKeys.emit([])
        for trace_id in touched:
            self.traceDataChanged.emit(trace_id)
        self._sync_x_axis_mode()
        self._update_axes()

    def selected_points(self) -> List[PlotPointRef]:
        """Return selected points as trace/index refs."""
        return list(self._selected)

    def set_selected_points(self, refs: Iterable[PlotPointRef], additive: bool = False) -> None:
        """Programmatically set selection for table/map sync workflows."""
        if not additive:
            for trace in self._traces.values():
                trace.selected_mask[:] = False

        for ref in refs:
            trace = self._traces.get(ref.trace_id)
            if trace is None:
                continue
            idx = int(ref.index)
            if 0 <= idx < trace.selected_mask.size and trace.active_mask[idx]:
                trace.selected_mask[idx] = True

        self._sync_selected_refs_from_masks()
        self._refresh_all_series()
        self._emit_selection_signals()

    def _create_series(self, trace: TraceData) -> None:
        if trace.mode in {"line", "both"}:
            line = QLineSeries()
            pen = line.pen()
            pen.setColor(_to_qcolor(trace.style.color))
            pen.setWidthF(trace.style.line_width)
            line.setPen(pen)
            line.setName(f"{trace.trace_id} (line)")
            self._attach_series(line)
            trace.line_series = line

        if trace.mode in {"scatter", "both"}:
            scatter = QScatterSeries()
            scatter.setColor(_to_qcolor(trace.style.color))
            scatter.setMarkerSize(trace.style.marker_size)
            scatter.setName(f"{trace.trace_id}")
            self._attach_series(scatter)
            trace.scatter_series = scatter

            selected = QScatterSeries()
            selected.setColor(_to_qcolor(trace.style.selected_color))
            selected.setMarkerSize(trace.style.selected_marker_size)
            selected.setName(f"{trace.trace_id} (selected)")
            self._attach_series(selected)
            trace.selected_series = selected

    def _attach_series(self, series) -> None:
        self._chart.addSeries(series)
        series.attachAxis(self._axis_x)
        series.attachAxis(self._axis_y)

    def _detach_trace(self, trace: TraceData) -> None:
        for s in (trace.line_series, trace.scatter_series, trace.selected_series):
            if s is not None:
                self._chart.removeSeries(s)

    def _refresh_trace_series(self, trace: TraceData) -> None:
        x_vals = self._x_values_for_trace(trace)
        active = trace.active_mask
        selected = trace.selected_mask
        unselected = active & ~selected

        if trace.line_series is not None:
            points = [QPointF(float(x), float(y)) for x, y in zip(x_vals[active], trace.y[active])]
            trace.line_series.replace(points)

        if trace.scatter_series is not None:
            points = [QPointF(float(x), float(y)) for x, y in zip(x_vals[unselected], trace.y[unselected])]
            trace.scatter_series.setColor(_to_qcolor(trace.style.color))
            trace.scatter_series.setMarkerSize(trace.style.marker_size)
            trace.scatter_series.replace(points)

        if trace.selected_series is not None:
            points = [QPointF(float(x), float(y)) for x, y in zip(x_vals[selected], trace.y[selected])]
            trace.selected_series.setColor(_to_qcolor(trace.style.selected_color))
            trace.selected_series.setMarkerSize(trace.style.selected_marker_size)
            trace.selected_series.replace(points)

    def _refresh_all_series(self) -> None:
        for trace in self._traces.values():
            self._refresh_trace_series(trace)

    def _sync_selected_refs_from_masks(self) -> None:
        refs: List[PlotPointRef] = []
        for trace_id, trace in self._traces.items():
            indices = np.flatnonzero(trace.selected_mask)
            refs.extend(PlotPointRef(trace_id, int(i)) for i in indices)
        self._selected = refs

    def _emit_selection_signals(self) -> None:
        self.selectionChanged.emit(self.selected_points())

        feature_keys: List[FeatureKey] = []
        for ref in self._selected:
            trace = self._traces.get(ref.trace_id)
            if trace is None or trace.feature_keys is None:
                continue
            if 0 <= ref.index < len(trace.feature_keys):
                feature_keys.append(trace.feature_keys[ref.index])
        self.highlightFeatureKeys.emit(feature_keys)

    def _update_axes(self) -> None:
        xs: List[np.ndarray] = []
        ys: List[np.ndarray] = []
        for trace in self._traces.values():
            mask = trace.active_mask
            if mask is None or not np.any(mask):
                continue
            xs.append(self._x_values_for_trace(trace)[mask])
            ys.append(trace.y[mask])

        if not xs:
            self._axis_x.setRange(0.0, 1.0)
            self._axis_y.setRange(0.0, 1.0)
            return

        x_all = np.concatenate(xs)
        y_all = np.concatenate(ys)

        x_min = float(np.min(x_all))
        x_max = float(np.max(x_all))
        y_min = float(np.min(y_all))
        y_max = float(np.max(y_all))

        if x_min == x_max:
            x_min -= 1.0
            x_max += 1.0
        if y_min == y_max:
            y_min -= 1.0
            y_max += 1.0

        x_pad = (x_max - x_min) * 0.05
        y_pad = (y_max - y_min) * 0.05

        x_lo = x_min - x_pad
        x_hi = x_max + x_pad
        if self._x_axis_mode == "datetime":
            self._axis_x_datetime.setRange(
                QDateTime.fromMSecsSinceEpoch(int(x_lo)),
                QDateTime.fromMSecsSinceEpoch(int(x_hi)),
            )
        else:
            self._axis_x_value.setRange(x_lo, x_hi)
        self._axis_y.setRange(y_min - y_pad, y_max + y_pad)

    def _on_box_select(self, x1: float, x2: float, y1: float, y2: float, additive: bool) -> None:
        if not additive:
            for trace in self._traces.values():
                trace.selected_mask[:] = False

        for trace in self._traces.values():
            x_vals = self._x_values_for_trace(trace)
            in_rect = (
                (x_vals >= x1)
                & (x_vals <= x2)
                & (trace.y >= y1)
                & (trace.y <= y2)
                & trace.active_mask
            )
            trace.selected_mask |= in_rect
            self._refresh_trace_series(trace)

        self._sync_selected_refs_from_masks()
        self._emit_selection_signals()

    def _x_values_for_trace(self, trace: TraceData) -> np.ndarray:
        """Return x values in the currently active axis units."""
        if self._x_axis_mode == "datetime" and trace.timestamps is not None:
            # QDateTimeAxis expects x-values in milliseconds since epoch.
            return trace.timestamps * 1000.0
        return trace.x

    def _desired_x_axis_mode(self) -> str:
        """Use datetime axis when all visible traces are timestamped."""
        if not self._traces:
            return "value"
        if all(trace.timestamps is not None for trace in self._traces.values()):
            return "datetime"
        return "value"

    def _sync_x_axis_mode(self) -> None:
        desired = self._desired_x_axis_mode()
        if desired == self._x_axis_mode:
            return

        old_axis = self._axis_x
        new_axis = self._axis_x_datetime if desired == "datetime" else self._axis_x_value

        for trace in self._traces.values():
            for series in (trace.line_series, trace.scatter_series, trace.selected_series):
                if series is not None:
                    series.detachAxis(old_axis)

        self._chart.removeAxis(old_axis)
        self._chart.addAxis(new_axis, Qt.AlignBottom)

        for trace in self._traces.values():
            for series in (trace.line_series, trace.scatter_series, trace.selected_series):
                if series is not None:
                    series.attachAxis(new_axis)

        self._axis_x = new_axis
        self._x_axis_mode = desired
