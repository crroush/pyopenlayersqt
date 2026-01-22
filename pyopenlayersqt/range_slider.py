"""Reusable dual-handle range slider widget.

This module provides a range slider with two handles for selecting a numeric range.
Supports both numeric values and ISO8601 timestamp strings (converted internally).

Key features:
  - Dual handles for min/max selection
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

from datetime import datetime
from typing import Any, List, Optional, Tuple, Union

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget


class RangeSliderWidget(QWidget):
    """A dual-handle range slider widget for numeric or ISO8601 timestamp ranges.
    
    This widget provides two sliders (min and max) that allow selecting a range.
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
        """
        super().__init__(parent)
        
        # Determine mode: ISO8601 or numeric
        self._is_iso8601 = values is not None
        self._iso_values: List[str] = []
        self._min_numeric: float = 0.0
        self._max_numeric: float = 100.0
        self._step: float = step
        
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
        self._min_slider.setValue(self._slider_min)
        self._max_slider.setValue(self._slider_max)
        self._update_labels()
    
    def _setup_ui(self, label: str) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Label
        self._label = QLabel(label)
        layout.addWidget(self._label)
        
        # Min slider
        min_container = QHBoxLayout()
        min_container.addWidget(QLabel("Min:"))
        self._min_slider = QSlider(Qt.Horizontal)
        self._min_slider.setMinimum(self._slider_min)
        self._min_slider.setMaximum(self._slider_max)
        self._min_slider.valueChanged.connect(self._on_min_changed)
        min_container.addWidget(self._min_slider, 1)
        self._min_label = QLabel()
        self._min_label.setMinimumWidth(120)
        min_container.addWidget(self._min_label)
        layout.addLayout(min_container)
        
        # Max slider
        max_container = QHBoxLayout()
        max_container.addWidget(QLabel("Max:"))
        self._max_slider = QSlider(Qt.Horizontal)
        self._max_slider.setMinimum(self._slider_min)
        self._max_slider.setMaximum(self._slider_max)
        self._max_slider.valueChanged.connect(self._on_max_changed)
        max_container.addWidget(self._max_slider, 1)
        self._max_label = QLabel()
        self._max_label.setMinimumWidth(120)
        max_container.addWidget(self._max_label)
        layout.addLayout(max_container)
    
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
        else:
            # Format numeric value nicely
            if self._step >= 1.0:
                return str(int(numeric_value))
            else:
                return f"{numeric_value:.2f}"
    
    def _on_min_changed(self, slider_val: int) -> None:
        """Handle min slider change."""
        # Ensure min doesn't exceed max
        if slider_val > self._max_slider.value():
            self._min_slider.setValue(self._max_slider.value())
            return
        
        self._update_labels()
        self._emit_range_changed()
    
    def _on_max_changed(self, slider_val: int) -> None:
        """Handle max slider change."""
        # Ensure max doesn't go below min
        if slider_val < self._min_slider.value():
            self._max_slider.setValue(self._min_slider.value())
            return
        
        self._update_labels()
        self._emit_range_changed()
    
    def _update_labels(self) -> None:
        """Update the value labels."""
        min_val = self._slider_to_value(self._min_slider.value())
        max_val = self._slider_to_value(self._max_slider.value())
        
        self._min_label.setText(self._format_value(min_val))
        self._max_label.setText(self._format_value(max_val))
    
    def _emit_range_changed(self) -> None:
        """Emit the rangeChanged signal with current values."""
        min_val = self._slider_to_value(self._min_slider.value())
        max_val = self._slider_to_value(self._max_slider.value())
        
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
        min_val = self._slider_to_value(self._min_slider.value())
        max_val = self._slider_to_value(self._max_slider.value())
        
        if self._is_iso8601:
            return (self._format_value(min_val), self._format_value(max_val))
        else:
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
                self._min_slider.setValue(min_idx)
                self._max_slider.setValue(max_idx)
            except ValueError:
                pass  # Value not in list
        else:
            # Set numeric values
            min_slider = self._value_to_slider(float(min_value))
            max_slider = self._value_to_slider(float(max_value))
            self._min_slider.setValue(min_slider)
            self._max_slider.setValue(max_slider)
        
        self._update_labels()
