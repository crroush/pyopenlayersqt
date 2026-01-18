# pyopenlayersqt Examples

This directory contains working example scripts demonstrating various features of pyopenlayersqt.

## Running the Examples

Each example is a standalone Python script that can be run directly:

```bash
python examples/01_quick_start.py
python examples/02_complete_example.py
python examples/03_performance_settings.py
```

## Example Descriptions

### 01_quick_start.py

The most basic example showing:
- Creating a map widget with custom initial center and zoom
- Adding a vector layer
- Adding points with custom styling
- Displaying the map

**Key features:**
- Map centered on US West Coast (-120.0, 37.0) at zoom level 6
- Two points: San Francisco and Los Angeles
- Custom red circle markers

### 02_complete_example.py

A comprehensive example demonstrating:
- Map widget with custom initial view
- Multiple layer types (vector and fast points)
- Feature table widget integration
- Bidirectional selection synchronization
- Handling 10,000+ points efficiently

**Key features:**
- Map centered on US West Coast for optimal viewing
- 1 vector point (red marker at San Francisco)
- 10,000 fast points (green, scattered across western US)
- Feature table showing all features
- Click on map to select features (updates table)
- Click on table rows to select features (updates map)
- Efficient rendering with canvas-based fast points layer

### 03_performance_settings.py

Performance optimization example demonstrating:
- Configuring FastPointsLayer for optimal performance with large datasets
- Performance settings: `skip_rendering_while_interacting` and `max_points_while_interacting`
- Comparing different performance configurations
- Handling 10,000+ points with smooth pan/zoom interactions

**Key features:**
- 10,000 random points across US West Coast
- Default performance settings (recommended for most use cases)
- Demonstrates smooth 60fps panning/zooming even with many points
- Shows how points reappear after interaction ends
- Examples of different performance configurations

## Requirements

All examples require:
- Python >= 3.10
- PySide6 >= 6.5
- numpy >= 1.23 (for examples using random data)
- pyopenlayersqt (installed from this repository)

Install dependencies:
```bash
pip install PySide6 numpy
```

## Tips

- **Initial View**: Use the `center` and `zoom` parameters in `OLMapWidget()` to set the initial map view appropriate for your data
- **Performance**: For > 1000 points, use `FastPointsLayer` instead of `VectorLayer`
- **Performance Tuning**: Configure `skip_rendering_while_interacting` and `max_points_while_interacting` in `FastPointsStyle` for optimal performance
- **Selection**: Features are selectable by clicking or Ctrl+drag (box selection)
- **Table Sync**: The complete example shows how to keep map and table selections synchronized
