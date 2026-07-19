#!/usr/bin/env python3
"""Handle Ctrl/Shift and ordinary held-key map clicks without JavaScript.

Click anywhere to display its coordinates.  Hold T while clicking to add a
yellow target marker, or hold Ctrl+T to add an orange priority target marker.
"""

from __future__ import annotations

import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import MapClickEvent, OLMapWidget, PointStyle


class ModifiedMapClickDemo(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Modified Map Click Demo")
        self.resize(1000, 700)

        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=11)
        self.target_layer = self.map_widget.add_vector_layer("targets")
        self._target_count = 0

        instructions = QtWidgets.QLabel(
            "Click the map to inspect coordinates. Hold <b>T</b> while clicking "
            "to add a yellow target. Hold <b>Ctrl+T</b> to add an orange priority "
            "target. No custom JavaScript is required."
        )
        instructions.setWordWrap(True)
        self.status = QtWidgets.QLabel("Click the map to begin.")
        clear_button = QtWidgets.QPushButton("Clear targets")
        clear_button.clicked.connect(self._clear_targets)

        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(instructions, 1)
        controls.addWidget(clear_button)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.status)
        layout.addWidget(self.map_widget, 1)

        # Observe every click with the typed Qt signal.
        self.map_widget.mapClicked.connect(self._show_click)
        # Register filtered callbacks for application actions.
        self.map_widget.on_map_click(self._add_target, keys="t")
        self.map_widget.on_map_click(
            self._add_priority_target, modifiers="ctrl", keys="t"
        )

    def _show_click(self, event: MapClickEvent) -> None:
        modifiers = [
            name
            for name, held in (
                ("Ctrl", event.ctrl_key),
                ("Meta", event.meta_key),
                ("Shift", event.shift_key),
                ("Alt", event.alt_key),
            )
            if held
        ]
        held_keys = ", ".join(sorted(event.keys)) or "none"
        modifier_text = "+".join(modifiers) or "none"
        self.status.setText(
            f"Lat: {event.lat:.6f}, Lon: {event.lon:.6f} | "
            f"modifiers: {modifier_text} | held keys: {held_keys}"
        )

    def _add_target(self, event: MapClickEvent) -> None:
        """Add a normal target unless the priority callback handles it too."""
        if event.ctrl_key:
            return
        self._add_point(event, "#ffff00", "target")

    def _add_priority_target(self, event: MapClickEvent) -> None:
        self._add_point(event, "#ff8c00", "priority-target")

    def _add_point(self, event: MapClickEvent, color: str, prefix: str) -> None:
        self._target_count += 1
        self.target_layer.add_points(
            [(event.lat, event.lon)],
            ids=[f"{prefix}-{self._target_count}"],
            style=PointStyle(
                radius=7.0,
                fill_color=QColor(color),
                stroke_color=QColor("#111111"),
                stroke_width=2.0,
            ),
        )

    def _clear_targets(self) -> None:
        self.target_layer.clear()
        self._target_count = 0
        self.status.setText("Targets cleared.")


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    window = ModifiedMapClickDemo()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
