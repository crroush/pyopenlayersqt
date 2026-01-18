#!/usr/bin/env python3
"""Performance Settings Example

This example demonstrates how to configure performance settings for FastPointsLayer
to optimize rendering during pan/zoom operations with large datasets.

The example shows:
- Creating a FastPointsLayer with performance-optimized settings
- Adding many points (10,000+) to test performance
- Configuring skip_rendering_while_interacting and max_points_while_interacting
- Comparing different performance configurations
"""

from PySide6 import QtWidgets
from pyopenlayersqt import OLMapWidget, FastPointsStyle
import numpy as np
import sys


def main():
    app = QtWidgets.QApplication(sys.argv)

    # Create the map widget centered on the US West Coast
    map_widget = OLMapWidget(center=(-120.0, 37.0), zoom=6)

    # Example 1: Default performance settings (recommended for most use cases)
    # - skip_rendering_while_interacting=True: Skip rendering when >100 points during pan/zoom
    # - skip_threshold=100: Threshold for skipping rendering
    # - max_points_while_interacting=5000: Render up to 5000 points during interaction
    # - min_points_while_interacting=500: Minimum points when throttling
    default_style = FastPointsStyle(
        radius=2.5,
        default_rgba=(0, 180, 0, 180),
        selected_radius=6.0,
        selected_rgba=(255, 255, 0, 255),
        # Performance settings (these are the defaults):
        skip_rendering_while_interacting=True,
        skip_threshold=100,
        max_points_while_interacting=5000,
        min_points_while_interacting=500,
    )

    fast_layer_default = map_widget.add_fast_points_layer(
        "fast_points_default",
        selectable=True,
        style=default_style,
        cell_size_m=750.0
    )

    # Example 2: Always render all points (may impact performance with large datasets)
    # Use this if you need to see all points during pan/zoom regardless of performance
    # Setting skip_threshold very high effectively disables skipping
    always_render_style = FastPointsStyle(
        radius=2.5,
        default_rgba=(0, 120, 255, 180),
        skip_rendering_while_interacting=False,  # Disable skip optimization
        skip_threshold=1000000,  # Very high threshold - won't skip unless you have millions of points
        max_points_while_interacting=100000,  # High limit for detail reduction
    )

    # Example 3: More aggressive optimization for very large datasets (100k+ points)
    # Reduce points rendered during interaction for smoother experience
    aggressive_style = FastPointsStyle(
        radius=2.0,
        default_rgba=(255, 100, 0, 180),
        skip_rendering_while_interacting=True,
        skip_threshold=50,  # Skip earlier - at 50 points instead of 100
        max_points_while_interacting=1000,  # Show only 1000 points during interaction
        min_points_while_interacting=250,  # Allow lower minimum for very large datasets
    )

    # Generate random points for demonstration
    # Using 10,000 points to show performance impact
    rng = np.random.default_rng(seed=42)
    n = 10000
    
    # Generate points scattered across the US West Coast
    lons = -125 + rng.random(n) * 10  # -125 to -115 longitude
    lats = 32 + rng.random(n) * 10    # 32 to 42 latitude
    coords = list(zip(lons.tolist(), lats.tolist()))
    ids = [f"point_{i}" for i in range(n)]

    # Add points to the layer
    fast_layer_default.add_points(coords, ids=ids)

    print(f"Added {n} points to the map")
    print("\nPerformance Settings (Default Configuration):")
    print("- skip_rendering_while_interacting=True")
    print("- skip_threshold=100 (skip rendering during pan/zoom when >100 points visible)")
    print("- max_points_while_interacting=5000 (max detail during interaction)")
    print("- min_points_while_interacting=500 (minimum detail when throttling)")
    print("\nHow it works:")
    print("1. When you pan/zoom and >100 points are visible, rendering is skipped")
    print("2. This maintains smooth 60fps interaction")
    print("3. Points reappear at full detail when you stop moving the map")
    print("\nTry panning and zooming the map to see the performance optimization in action!")
    print("Notice how the map remains responsive even with 10,000 points.")

    # Show the map
    map_widget.resize(1200, 800)
    map_widget.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
