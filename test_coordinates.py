#!/usr/bin/env python3
"""Test Coordinate Display Feature

This script tests the mouse coordinate display feature.
It creates two map widgets:
1. With coordinates enabled (default)
2. With coordinates disabled
"""

import sys
from PySide6 import QtWidgets
from pyopenlayersqt import OLMapWidget, PointStyle


def main():
    """Run the coordinate display test."""
    app = QtWidgets.QApplication(sys.argv)
    
    # Create main window with two maps side by side
    main_window = QtWidgets.QWidget()
    main_window.setWindowTitle("Coordinate Display Test")
    main_window.resize(1200, 600)
    
    layout = QtWidgets.QHBoxLayout(main_window)
    
    # Left side: Map with coordinates enabled (default)
    left_group = QtWidgets.QGroupBox("Coordinates Enabled (Default)")
    left_layout = QtWidgets.QVBoxLayout(left_group)
    map1 = OLMapWidget(center=(37.0, -120.0), zoom=6)
    left_layout.addWidget(map1)
    
    # Add a point to show it's working
    layer1 = map1.add_vector_layer("layer1", selectable=True)
    layer1.add_points(
        [(37.7749, -122.4194)],
        ids=["sf"],
        style=PointStyle(radius=8.0, fill_color="#ff3333")
    )
    
    # Right side: Map with coordinates disabled
    right_group = QtWidgets.QGroupBox("Coordinates Disabled")
    right_layout = QtWidgets.QVBoxLayout(right_group)
    map2 = OLMapWidget(center=(37.0, -120.0), zoom=6, show_coordinates=False)
    right_layout.addWidget(map2)
    
    # Add a point to show it's working
    layer2 = map2.add_vector_layer("layer2", selectable=True)
    layer2.add_points(
        [(37.7749, -122.4194)],
        ids=["sf"],
        style=PointStyle(radius=8.0, fill_color="#3333ff")
    )
    
    layout.addWidget(left_group)
    layout.addWidget(right_group)
    
    main_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
