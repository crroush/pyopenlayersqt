#!/usr/bin/env python3
"""Interactive Distance Measurement Tool

This example demonstrates the measurement mode feature:
- Enable/disable measurement mode with a button
- Click on map to add measurement points
- Display geodesic distances (great circle distances)
- Clear all measurements
- Visualize measurement path and segments

Useful for measuring distances on the map interactively.
"""

import sys
import json

from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, PointStyle


class MeasurementExample(QtWidgets.QMainWindow):
    """Measurement tool example window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Interactive Distance Measurement Tool")
        self.resize(1200, 800)

        # Create map
        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=11)

        # Add some reference points
        self._add_reference_points()

        # Track measurement state
        self.measurement_enabled = False

        # Connect jsEvent for measurement updates
        self.map_widget.jsEvent.connect(self._on_js_event)

        # Create controls
        controls = self._create_controls()

        # Layout
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(controls)
        layout.addWidget(self.map_widget, stretch=1)
        self.setCentralWidget(container)

    def _add_reference_points(self):
        """Add reference points to the map."""
        layer = self.map_widget.add_vector_layer("landmarks", selectable=False)

        landmarks = [
            (37.7749, -122.4194, "San Francisco City Hall"),
            (37.8199, -122.4783, "Golden Gate Bridge"),
            (37.8088, -122.4098, "Ferry Building"),
        ]

        for lat, lon, name in landmarks:
            layer.add_points(
                [(lat, lon)],
                ids=[name],
                style=PointStyle(
                    radius=8.0,
                    fill_color=QColor("blue"),
                    stroke_color=QColor("darkblue"),
                    stroke_width=2.0
                )
            )

    def _create_controls(self):
        """Create control panel."""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(panel)

        # Instructions
        instructions = QtWidgets.QLabel(
            "Enable measurement mode and click on the map to measure distances. "
            "Each click adds a point and shows cumulative distance."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions, stretch=1)

        # Measurement toggle
        self.measure_btn = QtWidgets.QPushButton("Enable Measurement Mode")
        self.measure_btn.setCheckable(True)
        self.measure_btn.setFixedWidth(200)
        self.measure_btn.clicked.connect(self._toggle_measurement)
        layout.addWidget(self.measure_btn)

        # Clear button
        self.clear_btn = QtWidgets.QPushButton("Clear Measurements")
        self.clear_btn.setFixedWidth(150)
        self.clear_btn.clicked.connect(self._clear_measurements)
        self.clear_btn.setEnabled(False)
        layout.addWidget(self.clear_btn)

        # Distance display
        self.distance_label = QtWidgets.QLabel("Distance: 0.00 km")
        self.distance_label.setStyleSheet(
            "background-color: #e8f4f8; padding: 8px; "
            "font-weight: bold; font-size: 14px; border-radius: 4px;"
        )
        layout.addWidget(self.distance_label)

        return panel

    def _toggle_measurement(self, checked):
        """Toggle measurement mode."""
        self.map_widget.set_measure_mode(checked)

        if checked:
            self.measure_btn.setText("Disable Measurement Mode")
            self.measure_btn.setStyleSheet("background-color: #ff6b6b; color: white;")
            self.clear_btn.setEnabled(True)
        else:
            self.measure_btn.setText("Enable Measurement Mode")
            self.measure_btn.setStyleSheet("")

    def _clear_measurements(self):
        """Clear all measurement points."""
        self.map_widget.clear_measurements()
        self.distance_label.setText("Distance: 0.00 km")

    def _on_js_event(self, event_type, payload_json):
        """Handle JavaScript events from the map."""
        if event_type == "measurement":
            try:
                data = json.loads(payload_json)
                total_km = data.get("total_km", 0.0)
                self.distance_label.setText(f"Distance: {total_km:.2f} km")
            except json.JSONDecodeError:
                pass


def main():
    """Run the measurement tool example."""
    app = QtWidgets.QApplication(sys.argv)
    window = MeasurementExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
