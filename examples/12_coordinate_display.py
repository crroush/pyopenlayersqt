#!/usr/bin/env python3
"""Coordinate Display Toggle

This example demonstrates the coordinate display feature:
- Show/hide mouse coordinates in the lower-right corner
- Toggle coordinate display with a button
- Coordinates update as mouse moves over the map
- Displays latitude and longitude in real-time

The coordinate display is controlled by the show_coordinates parameter
in the OLMapWidget constructor or can be toggled programmatically.
"""

import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, PointStyle


class CoordinateDisplayExample(QtWidgets.QMainWindow):
    """Coordinate display example window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Coordinate Display Toggle")
        self.resize(1200, 800)

        # Create map with coordinate display enabled by default
        self.map_widget = OLMapWidget(
            center=(37.7749, -122.4194),
            zoom=10,
            show_coordinates=True  # Show coordinates by default
        )

        # Add some reference points
        self._add_reference_points()

        # Create controls
        controls = self._create_controls()

        # Layout
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(controls)
        layout.addWidget(self.map_widget, stretch=1)
        self.setCentralWidget(container)

    def _add_reference_points(self):
        """Add reference points to show locations."""
        layer = self.map_widget.add_vector_layer("cities", selectable=False)

        cities = [
            (37.7749, -122.4194, "San Francisco", "red"),
            (37.8044, -122.2712, "Oakland", "blue"),
            (37.3382, -121.8863, "San Jose", "green"),
        ]

        for lat, lon, name, color in cities:
            layer.add_points(
                [(lat, lon)],
                ids=[name],
                style=PointStyle(
                    radius=10.0,
                    fill_color=QColor(color),
                    stroke_color=QColor("black"),
                    stroke_width=2.0
                )
            )

    def _create_controls(self):
        """Create control panel."""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(panel)

        # Instructions
        instructions = QtWidgets.QLabel(
            "Move your mouse over the map to see coordinates in the lower-right corner. "
            "Use the button to toggle coordinate display on/off."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("padding: 8px;")
        layout.addWidget(instructions, stretch=1)

        # Toggle button
        self.toggle_btn = QtWidgets.QPushButton("Hide Coordinates")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setFixedWidth(150)
        self.toggle_btn.clicked.connect(self._toggle_coordinates)
        layout.addWidget(self.toggle_btn)

        # Info label
        info = QtWidgets.QLabel(
            "Coordinates shown: Enabled"
        )
        info.setStyleSheet(
            "background-color: #d4edda; color: #155724; "
            "padding: 8px; border-radius: 4px; font-weight: bold;"
        )
        self.info_label = info
        layout.addWidget(info)

        return panel

    def _toggle_coordinates(self, checked):
        """Toggle coordinate display."""
        # Note: Currently, the coordinate display toggle requires JavaScript
        # communication. For this example, we'll use JavaScript evaluation.
        if checked:
            # Hide coordinates
            self.toggle_btn.setText("Show Coordinates")
            self.info_label.setText("Coordinates shown: Disabled")
            self.info_label.setStyleSheet(
                "background-color: #f8d7da; color: #721c24; "
                "padding: 8px; border-radius: 4px; font-weight: bold;"
            )
            # Send message to hide coordinates
            self.map_widget.send({
                "type": "set_coordinate_display",
                "visible": False
            })
        else:
            # Show coordinates
            self.toggle_btn.setText("Hide Coordinates")
            self.info_label.setText("Coordinates shown: Enabled")
            self.info_label.setStyleSheet(
                "background-color: #d4edda; color: #155724; "
                "padding: 8px; border-radius: 4px; font-weight: bold;"
            )
            # Send message to show coordinates
            self.map_widget.send({
                "type": "set_coordinate_display",
                "visible": True
            })


def main():
    """Run the coordinate display example."""
    app = QtWidgets.QApplication(sys.argv)
    window = CoordinateDisplayExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
