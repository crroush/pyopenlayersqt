#!/usr/bin/env python3
"""Test script to verify great-circle measurement lines.

This script creates a measurement example with distant locations
to verify that the lines are now curved great-circle paths.
"""

from PySide6 import QtWidgets
from pyopenlayersqt import OLMapWidget
import sys
import json


class TestMeasurementWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Great-Circle Measurement Test")
        
        # Create map widget - start with a view of the Atlantic
        self.map_widget = OLMapWidget(center=(40.0, -30.0), zoom=3)
        
        # Connect to measurement events
        self.map_widget.jsEvent.connect(self.on_js_event)
        
        # Create controls
        info_label = QtWidgets.QLabel(
            "Click 'Start Measurement' and then click on distant locations "
            "(e.g., New York and London) to see the great-circle path.\n"
            "The line should now be curved, representing the actual shortest path."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("padding: 10px; background-color: #e8f4f8;")
        
        self.measure_button = QtWidgets.QPushButton("Start Measurement")
        self.measure_button.setCheckable(True)
        self.measure_button.toggled.connect(self.on_measure_toggled)
        
        self.clear_button = QtWidgets.QPushButton("Clear Measurements")
        self.clear_button.clicked.connect(self.on_clear_clicked)
        
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        
        # Layout
        controls_layout = QtWidgets.QHBoxLayout()
        controls_layout.addWidget(self.measure_button)
        controls_layout.addWidget(self.clear_button)
        controls_layout.addStretch()
        
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addWidget(info_label)
        main_layout.addLayout(controls_layout)
        main_layout.addWidget(self.map_widget, 1)
        main_layout.addWidget(QtWidgets.QLabel("Measurement Log:"))
        main_layout.addWidget(self.log_text)
        
        container = QtWidgets.QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
        
        self.log("Test ready. Try measuring between:")
        self.log("  - New York (40.7128° N, 74.0060° W)")
        self.log("  - London (51.5074° N, 0.1278° W)")
        self.log("Expected: ~5,570 km with a curved northward arc")
    
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
                    msg = f"Point {index}: ({lat:.4f}°, {lon:.4f}°)"
                else:
                    segment_str = self.format_distance(segment_m)
                    cumulative_str = self.format_distance(cumulative_m)
                    msg = f"Point {index}: ({lat:.4f}°, {lon:.4f}°) - Segment: {segment_str}, Total: {cumulative_str}"
                
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
    window = TestMeasurementWindow()
    window.resize(1200, 800)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
