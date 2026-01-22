#!/usr/bin/env python3
"""Measurement Mode Example

This example demonstrates the distance measurement feature:
- Toggle measurement mode with a button
- Click on the map to create measurement points
- See segment and cumulative distances in a tooltip
- Lines follow great-circle (geodesic) paths for accurate visualization
- Measurement events are logged to the console
- Press Escape to exit measurement mode
- Clear measurements with a button
"""

from PySide6 import QtWidgets
from pyopenlayersqt import OLMapWidget
import sys
import json


class MeasurementWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pyopenlayersqt - Measurement Mode Example")
        
        # Create map widget centered on San Francisco Bay Area
        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=10)
        
        # Connect to measurement events
        self.map_widget.jsEvent.connect(self.on_js_event)
        
        # Create controls
        self.measure_button = QtWidgets.QPushButton("Start Measurement")
        self.measure_button.setCheckable(True)
        self.measure_button.toggled.connect(self.on_measure_toggled)
        
        self.clear_button = QtWidgets.QPushButton("Clear Measurements")
        self.clear_button.clicked.connect(self.on_clear_clicked)
        
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        
        # Layout
        controls_layout = QtWidgets.QHBoxLayout()
        controls_layout.addWidget(self.measure_button)
        controls_layout.addWidget(self.clear_button)
        controls_layout.addStretch()
        
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(controls_layout)
        main_layout.addWidget(self.map_widget, 1)
        main_layout.addWidget(QtWidgets.QLabel("Measurement Log:"))
        main_layout.addWidget(self.log_text)
        
        container = QtWidgets.QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
        
        self.log("Application started. Click 'Start Measurement' to begin.")
    
    def on_measure_toggled(self, checked):
        """Toggle measurement mode."""
        self.map_widget.set_measure_mode(checked)
        if checked:
            self.measure_button.setText("Stop Measurement (or press Esc)")
            self.log("Measurement mode enabled. Click on the map to add points.")
        else:
            self.measure_button.setText("Start Measurement")
            self.log("Measurement mode disabled.")
    
    def on_clear_clicked(self):
        """Clear all measurements."""
        self.map_widget.clear_measurements()
        self.log("Measurements cleared.")
    
    def on_js_event(self, event_type, payload_json):
        """Handle events from JavaScript."""
        if event_type == "measurement":
            try:
                data = json.loads(payload_json)
                segment_m = data.get('segment_distance_m')
                cumulative_m = data.get('cumulative_distance_m')
                lon = data.get('lon')
                lat = data.get('lat')
                index = data.get('point_index')
                
                # Format distances
                if segment_m is None:
                    msg = f"Point {index}: ({lat:.5f}, {lon:.5f})"
                else:
                    segment_str = self.format_distance(segment_m)
                    cumulative_str = self.format_distance(cumulative_m)
                    msg = f"Point {index}: ({lat:.5f}, {lon:.5f}) - Segment: {segment_str}, Total: {cumulative_str}"
                
                self.log(msg)
            except Exception as e:
                self.log(f"Error processing measurement event: {e}")
    
    def format_distance(self, meters):
        """Format distance for display."""
        if meters < 1000:
            return f"{meters:.1f} m"
        elif meters < 100000:
            return f"{meters / 1000:.2f} km"
        else:
            return f"{meters / 1000:.0f} km"
    
    def log(self, message):
        """Add a message to the log."""
        self.log_text.append(message)


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = MeasurementWindow()
    window.resize(1000, 700)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
