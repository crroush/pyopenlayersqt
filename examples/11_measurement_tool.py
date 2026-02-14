#!/usr/bin/env python3
"""Interactive Distance Measurement Tool

This example demonstrates the measurement mode feature with a clean callback API:
- Enable/disable measurement mode with a button
- Click on map to add measurement points
- View per-segment and total geodesic distance in a side panel
- Delete all measurements with Clear button
- Visualize measurement path and segments

Features demonstrated:
- set_measure_mode() to enable/disable measurement
- on_measurement_updated() callback registration
- measurementUpdated signal for structured updates
- clear_measurements() to delete all measurement points
"""

import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, PointStyle, MeasurementUpdate


class MeasurementExample(QtWidgets.QMainWindow):
    """Measurement tool example window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Interactive Distance Measurement Tool")
        self.resize(1300, 800)

        self._segments_m: list[float] = []

        # Create map
        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=11)

        # Add some reference points
        self._add_reference_points()

        # Structured measurement callback (clean API)
        self.map_widget.on_measurement_updated(self._on_measurement_updated)

        # Create UI
        controls = self._create_controls()
        summary_panel = self._create_summary_panel()

        map_container = QtWidgets.QWidget()
        map_layout = QtWidgets.QVBoxLayout(map_container)
        map_layout.addWidget(controls)
        map_layout.addWidget(self.map_widget, stretch=1)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(map_container)
        splitter.addWidget(summary_panel)
        splitter.setSizes([980, 320])

        self.setCentralWidget(splitter)

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
                    stroke_width=2.0,
                ),
            )

    def _create_controls(self):
        """Create top control panel."""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(panel)

        instructions = QtWidgets.QLabel(
            "Enable measurement mode and click on the map to add points. "
            "The side panel will show each segment distance and the running total."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions, stretch=1)

        self.measure_btn = QtWidgets.QPushButton("Enable Measurement Mode")
        self.measure_btn.setCheckable(True)
        self.measure_btn.setFixedWidth(220)
        self.measure_btn.clicked.connect(self._toggle_measurement)
        layout.addWidget(self.measure_btn)

        self.clear_btn = QtWidgets.QPushButton("Clear Measurements")
        self.clear_btn.setFixedWidth(160)
        self.clear_btn.clicked.connect(self._clear_measurements)
        self.clear_btn.setEnabled(False)
        layout.addWidget(self.clear_btn)

        return panel

    def _create_summary_panel(self):
        """Create right-side measurement summary panel."""
        panel = QtWidgets.QWidget()
        panel.setMinimumWidth(280)
        layout = QtWidgets.QVBoxLayout(panel)

        title = QtWidgets.QLabel("Measurement Summary")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        self.points_label = QtWidgets.QLabel("Points: 0")
        layout.addWidget(self.points_label)

        self.segment_list = QtWidgets.QListWidget()
        layout.addWidget(self.segment_list, stretch=1)

        self.total_label = QtWidgets.QLabel("Total: 0.00 km")
        self.total_label.setStyleSheet(
            "background-color: #e8f4f8; padding: 8px; "
            "font-weight: bold; font-size: 14px; border-radius: 4px;"
        )
        layout.addWidget(self.total_label)

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
        """Clear all measurement points and UI summary."""
        self.map_widget.clear_measurements()
        self._segments_m.clear()
        self.segment_list.clear()
        self.points_label.setText("Points: 0")
        self.total_label.setText("Total: 0.00 km")

    def _on_measurement_updated(self, update: MeasurementUpdate):
        """Handle a typed measurement update from the map."""
        point_count = update.point_index + 1
        self.points_label.setText(f"Points: {point_count}")

        if update.segment_distance_m is not None:
            segment_m = update.segment_distance_m
            self._segments_m.append(segment_m)
            row = (
                f"Segment {len(self._segments_m)}: "
                f"{segment_m:.1f} m  "
                f"({update.lat:.5f}, {update.lon:.5f})"
            )
            self.segment_list.addItem(row)
        elif point_count == 1:
            self.segment_list.addItem(
                f"Start: ({update.lat:.5f}, {update.lon:.5f})"
            )

        self.total_label.setText(f"Total: {update.cumulative_distance_m / 1000.0:.2f} km")


def main():
    """Run the measurement tool example."""
    app = QtWidgets.QApplication(sys.argv)
    window = MeasurementExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
