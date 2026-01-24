# pyopenlayersqt

OpenLayers + Qt (QWebEngine) mapping widget for Python.

A high-performance, feature-rich mapping widget that embeds OpenLayers in a Qt application using QWebEngine. Designed for displaying and interacting with large volumes of geospatial data.
<img width="821" height="503" alt="image" src="https://github.com/user-attachments/assets/ef34e565-12f5-48b3-92e5-bbe752a96992" />

## Table of Contents

- [Features](#features)
- [Installation](#installation)
  - [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Core Components](#core-components)
  - [OLMapWidget](#olmapwidget)
  - [Layer Types](#layer-types)
    - [VectorLayer](#vectorlayer)
    - [FastPointsLayer](#fastpointslayer)
    - [FastGeoPointsLayer](#fastgeopointslayer)
    - [WMSLayer](#wmslayer)
    - [RasterLayer](#rasterlayer)
  - [Style Classes](#style-classes)
  - [Feature Selection](#feature-selection)
  - [Selection and Recoloring](#selection-and-recoloring)
  - [Distance Measurement Mode](#distance-measurement-mode)
  - [FeatureTableWidget](#featuretablewidget)
  - [RangeSliderWidget](#rangesliderwidget)
- [Complete Example](#complete-example)
- [Running the Demo](#running-the-demo)
- [View Extent Tracking](#view-extent-tracking)
- [Advanced: Direct JavaScript Communication](#advanced-direct-javascript-communication)
- [Performance Tips](#performance-tips)
- [Architecture](#architecture)
- [License](#license)
- [Contributing](#contributing)
- [Versioning and Releases](#versioning-and-releases)
  - [For Maintainers: Creating a Release](#for-maintainers-creating-a-release)
  - [PyPI Setup Requirements](#pypi-setup-requirements)
- [Credits](#credits)

## Features

- **🗺️ Interactive Map Widget**: Fully-featured OpenLayers map embedded in PySide6/Qt
- **⚡ High-Performance Rendering**: Fast points layers with spatial indexing for millions of points
- **🎨 Rich Styling**: Customizable styles for points, polygons, circles, and ellipses
- **📍 Geolocation Support**: Fast geo-points layer with uncertainty ellipses
- **🌐 WMS Integration**: Built-in Web Map Service layer support
- **🖼️ Raster Overlays**: PNG/image overlay support with custom bounds
- **✅ Feature Selection**: Interactive feature selection with Python ↔ JavaScript sync
- **📊 Feature Table Widget**: High-performance table widget for displaying and managing features
- **🔄 Bidirectional Sync**: Seamless selection synchronization between map and table
- **📏 Distance Measurement**: Interactive measurement mode with geodesic distance calculations and great-circle path visualization
- **🎚️ Range Slider Widget**: Dual-handle range slider for filtering features by numeric or timestamp ranges

## Installation

```bash
pip install pyopenlayersqt
```

### Requirements

- Python >= 3.10
- PySide6 >= 6.5
- numpy >= 1.23
- pillow >= 10.0
- matplotlib >= 3.7

## Quick Start

```python
from PySide6 import QtWidgets
from pyopenlayersqt import OLMapWidget, PointStyle
import sys

app = QtWidgets.QApplication(sys.argv)

# Create the map widget with custom initial view
map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)

# Add a vector layer
vector_layer = map_widget.add_vector_layer("my_layer", selectable=True)

# Add some points
coords = [(37.7749, -122.4194), (34.0522, -118.2437)]  # SF, LA
vector_layer.add_points(
    coords,
    ids=["sf", "la"],
    style=PointStyle(radius=8.0, fill_color="#ff3333")
)

# Show the map
map_widget.show()
sys.exit(app.exec())
```

See the [examples directory](examples/) for more working examples.

## Core Components

### OLMapWidget

The main widget class that embeds an OpenLayers map.

```python
from pyopenlayersqt import OLMapWidget

# Create with default world view (center at 0,0, zoom level 2)
map_widget = OLMapWidget()

# Or create with custom initial view
map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)
```
<img width="323" height="257" alt="image" src="https://github.com/user-attachments/assets/1f726e15-0598-4bb6-9223-b2a0d60238ff" />

**Constructor Parameters:**

- `parent` - Optional parent widget
- `center` - Initial map center as `(lat, lon)` tuple. Defaults to `(0, 0)`.
- `zoom` - Initial zoom level (integer). Defaults to `2` (world view).

**Key Methods:**

- `add_vector_layer(name, selectable=True)` - Create a vector layer for points, polygons, circles, ellipses
- `add_fast_points_layer(name, selectable, style, cell_size_m)` - Create a high-performance points layer
- `add_fast_geopoints_layer(name, selectable, style, cell_size_m)` - Create a geo-points layer with uncertainty ellipses
- `add_wms(options, name)` - Add a WMS (Web Map Service) layer
- `add_raster_image(image, bounds, style, name)` - Add a raster image overlay
- `set_base_opacity(opacity)` - Set OSM base layer opacity (0.0-1.0)
- `set_measure_mode(enabled)` - Enable/disable interactive distance measurement mode
- `clear_measurements()` - Clear all measurement points and lines
- `get_view_extent(callback)` - Get current map extent asynchronously
- `watch_view_extent(callback, debounce_ms)` - Subscribe to extent changes

**Signals:**

- `ready` - Emitted when the map is ready
- `selectionChanged` - Emitted when feature selection changes
- `viewExtentChanged` - Emitted when map extent changes

### Layer Types

#### VectorLayer

For standard vector features with full styling control.

```python
from pyopenlayersqt import PointStyle, PolygonStyle, CircleStyle, EllipseStyle

# Add a vector layer
vector = map_widget.add_vector_layer("vector", selectable=True)

# Add points
vector.add_points(
    coords=[(lat, lon), ...],
    ids=["id1", "id2", ...],
    style=PointStyle(
        radius=6.0,
        fill_color="#ff3333",
        fill_opacity=0.85,
        stroke_color="#000000",
        stroke_width=1.0
    )
)

# Add polygons
vector.add_polygon(
    ring=[(lat1, lon1), (lat2, lon2), ...],
    feature_id="poly1",
    style=PolygonStyle(
        stroke_color="#00aaff",
        stroke_width=2.0,
        fill_color="#00aaff",
        fill_opacity=0.15
    )
)

# Add lines (polylines)
vector.add_line(
    coords=[(lat1, lon1), (lat2, lon2), (lat3, lon3)],
    feature_id="ln1",
    style=PolygonStyle(
        stroke_color="#00aaff",
        stroke_width=2.0
    )
)

# Add circles (radius in meters)
vector.add_circle(
    center=(lat, lon),
    radius_m=1000.0,
    feature_id="circle1",
    style=CircleStyle(stroke_color="#00aaff", fill_opacity=0.15)
)

# Add ellipses (semi-major/minor axes in meters, tilt in degrees from north)
vector.add_ellipse(
    center=(lat, lon),
    sma_m=2000.0,  # Semi-major axis
    smi_m=1200.0,  # Semi-minor axis
    tilt_deg=45.0,  # Tilt from true north
    feature_id="ell1",
    style=EllipseStyle(stroke_color="#ffcc00", fill_opacity=0.12)
)

# Update styles of specific features (e.g., selected features)
feature_ids = ["id1", "id2"]
new_styles = [
    PointStyle(radius=8.0, fill_color="#ff0000", fill_opacity=1.0),
    PointStyle(radius=8.0, fill_color="#00ff00", fill_opacity=1.0),
]
vector.update_feature_styles(feature_ids, new_styles)

# Remove features
vector.remove_features(["id1", "poly1"])

# Clear all features
vector.clear()
```

#### FastPointsLayer

High-performance layer for rendering millions of points using canvas and spatial indexing.

```python
from pyopenlayersqt import FastPointsStyle

# Create fast points layer
fast = map_widget.add_fast_points_layer(
    "fast_points",
    selectable=True,
    style=FastPointsStyle(
        radius=2.5,
        default_rgba=(0, 180, 0, 180),  # RGBA 0-255
        selected_radius=6.0,
        selected_rgba=(255, 255, 0, 255)
    ),
    cell_size_m=750.0  # Spatial index cell size
)

# Add points (efficient for large datasets)
coords = [(lat, lon), ...]  # millions of points
ids = [f"pt{i}" for i in range(len(coords))]

# Option 1: Single color for all points
fast.add_points(coords, ids=ids)

# Option 2: Per-point colors
colors = [(r, g, b, a), ...]  # RGBA tuples
fast.add_points(coords, ids=ids, colors_rgba=colors)

# Remove specific points
fast.remove_points(["pt1", "pt2"])

# Update colors of specific points (e.g., selected points)
feature_ids = ["pt10", "pt25", "pt50"]
new_colors = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)]
fast.set_colors(feature_ids, new_colors)

# Clear all points
fast.clear()
```

#### FastGeoPointsLayer

High-performance layer for geolocation data with uncertainty ellipses.

```python
from pyopenlayersqt import FastGeoPointsStyle

# Create fast geo points layer
fast_geo = map_widget.add_fast_geopoints_layer(
    "fast_geo",
    selectable=True,
    style=FastGeoPointsStyle(
        # Point styling
        point_radius=2.5,
        default_point_rgba=(40, 80, 255, 180),
        selected_point_radius=6.0,
        selected_point_rgba=(255, 255, 255, 255),
        # Ellipse styling
        ellipse_stroke_rgba=(40, 80, 255, 160),
        ellipse_stroke_width=1.2,
        fill_ellipses=False,
        ellipse_fill_rgba=(40, 80, 255, 40),
        # Behavior
        ellipses_visible=True,
        min_ellipse_px=0.0,  # Cull tiny ellipses
        max_ellipses_per_path=2000,
        skip_ellipses_while_interacting=True
    ),
    cell_size_m=750.0
)

# Add points with uncertainty ellipses
coords = [(lat, lon), ...]
sma_m = [200.0, 300.0, ...]  # Semi-major axes in meters
smi_m = [100.0, 150.0, ...]  # Semi-minor axes in meters
tilt_deg = [45.0, 90.0, ...]  # Tilt from north in degrees
ids = [f"geo{i}" for i in range(len(coords))]

fast_geo.add_points_with_ellipses(
    coords=coords,
    sma_m=sma_m,
    smi_m=smi_m,
    tilt_deg=tilt_deg,
    ids=ids
)

# Toggle ellipse visibility
fast_geo.set_ellipses_visible(False)

# Update colors of specific points (e.g., selected points)
feature_ids = ["geo5", "geo12", "geo20"]
new_colors = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)]
fast_geo.set_colors(feature_ids, new_colors)

# Remove points
fast_geo.remove_ids(["geo1", "geo2"])

# Clear all
fast_geo.clear()
```

#### WMSLayer

Web Map Service layer integration.

```python
from pyopenlayersqt import WMSOptions

# Add WMS layer
wms_options = WMSOptions(
    url="https://ahocevar.com/geoserver/wms",
    params={
        "LAYERS": "topp:states",
        "TILED": True,
        "FORMAT": "image/png",
        "TRANSPARENT": True
    },
    opacity=0.85
)

wms_layer = map_widget.add_wms(wms_options, name="wms")

# Update WMS parameters
wms_layer.set_params({"LAYERS": "new:layer"})

# Set opacity
wms_layer.set_opacity(0.5)

# Remove layer
wms_layer.remove()
```

#### RasterLayer

Image overlay layer for heatmaps, imagery, etc.

```python
from pyopenlayersqt import RasterStyle

# Create PNG bytes (example using PIL)
from PIL import Image
import io

img = Image.new('RGBA', (512, 512), color=(255, 0, 0, 128))
buf = io.BytesIO()
img.save(buf, format='PNG')
png_bytes = buf.getvalue()

# Add raster overlay
bounds = [
    (lat_min, lon_min),  # Southwest corner
    (lat_max, lon_max)   # Northeast corner
]

raster = map_widget.add_raster_image(
    png_bytes,  # Can be bytes, file path, or URL
    bounds=bounds,
    style=RasterStyle(opacity=0.6),
    name="heatmap"
)

# Update opacity
raster.set_opacity(0.8)

# Remove layer
raster.remove()
```
<img width="828" height="506" alt="image" src="https://github.com/user-attachments/assets/5e0038df-0e53-4abb-86db-2cdf5d5615d6" />

### Style Classes

All style classes are immutable dataclasses with sensible defaults:

```python
from pyopenlayersqt import (
    PointStyle,
    PolygonStyle,
    CircleStyle,
    EllipseStyle,
    RasterStyle,
    FastPointsStyle,
    FastGeoPointsStyle
)

# Vector styles use CSS colors
point_style = PointStyle(
    radius=5.0,
    fill_color="#ff3333",  # CSS color or (r,g,b) tuple
    fill_opacity=0.85,
    stroke_color="#000000",
    stroke_width=1.0,
    stroke_opacity=0.9
)

# Fast layer styles use RGBA tuples (0-255)
fast_style = FastPointsStyle(
    radius=3.0,
    default_rgba=(255, 51, 51, 204),
    selected_radius=6.0,
    selected_rgba=(0, 255, 255, 255)
)
```

### Feature Selection

Selection is synchronized between the map and Python:

```python
# Set selection programmatically
map_widget.set_vector_selection(layer_id, ["feature1", "feature2"])
map_widget.set_fast_points_selection(layer_id, ["pt1", "pt2"])
map_widget.set_fast_geopoints_selection(layer_id, ["geo1", "geo2"])

# Listen to selection changes from map
def on_selection_changed(selection):
    print(f"Layer: {selection.layer_id}")
    print(f"Selected IDs: {selection.feature_ids}")
    print(f"Count: {selection.count}")

map_widget.selectionChanged.connect(on_selection_changed)
```

### Selection and Recoloring

Update colors or styles of selected features across all layer types:

```python
# For VectorLayer: Update feature styles
selected_ids = ["pt1", "pt2", "pt3"]
new_styles = [
    PointStyle(radius=10.0, fill_color="#ff0000"),
    PointStyle(radius=10.0, fill_color="#00ff00"),
    PointStyle(radius=10.0, fill_color="#0000ff"),
]
vector_layer.update_feature_styles(selected_ids, new_styles)

# For FastPointsLayer: Update colors
selected_ids = ["fp1", "fp2", "fp3"]
new_colors = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)]
fast_layer.set_colors(selected_ids, new_colors)

# For FastGeoPointsLayer: Update colors
selected_ids = ["geo1", "geo2", "geo3"]
new_colors = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)]
fast_geo_layer.set_colors(selected_ids, new_colors)
```

**Complete workflow example with multi-layer selection support:**
```python
# Track selections for all layers (layer_id -> list of feature_ids)
selections = {}

def on_selection_changed(selection):
    global selections
    # Update selections for this layer
    if len(selection.feature_ids) > 0:
        selections[selection.layer_id] = selection.feature_ids
    elif selection.layer_id in selections:
        # Clear selection for this layer
        del selections[selection.layer_id]
    
    total = sum(len(ids) for ids in selections.values())
    print(f"Total selected: {total} features across {len(selections)} layer(s)")

map_widget.selectionChanged.connect(on_selection_changed)

# Recolor all selected items across all layers
def recolor_selected_red():
    for layer_id, feature_ids in selections.items():
        if layer_id == vector_layer.id:
            styles = [PointStyle(fill_color="#ff0000") for _ in feature_ids]
            vector_layer.update_feature_styles(feature_ids, styles)
        elif layer_id == fast_layer.id:
            colors = [(255, 0, 0, 255) for _ in feature_ids]
            fast_layer.set_colors(feature_ids, colors)
        elif layer_id == fast_geo_layer.id:
            colors = [(255, 0, 0, 255) for _ in feature_ids]
            fast_geo_layer.set_colors(feature_ids, colors)
```

See [examples/06_selection_recoloring.py](examples/06_selection_recoloring.py) for a complete interactive example.

### Distance Measurement Mode

Interactive distance measurement with geodesic calculations:

```python
import json

# Enable measurement mode
map_widget.set_measure_mode(True)

# Listen for measurement events
def on_js_event(event_type, payload_json):
    if event_type == 'measurement':
        data = json.loads(payload_json)
        segment_m = data['segment_distance_m']      # Distance from previous point
        cumulative_m = data['cumulative_distance_m']  # Total distance from start
        lon, lat = data['lon'], data['lat']
        print(f"Point at ({lat:.5f}, {lon:.5f})")
        print(f"Segment: {segment_m:.1f} m, Total: {cumulative_m:.1f} m")

map_widget.jsEvent.connect(on_js_event)

# Clear all measurements
map_widget.clear_measurements()

# Disable measurement mode
map_widget.set_measure_mode(False)
```

**Features:**
- Click on map to create measurement anchor points
- Live polyline drawn from last point to cursor
- Tooltip displays segment and cumulative distances
- Uses Haversine formula for accurate great-circle distances
- **Lines follow great-circle paths** - measurement lines curve to represent the true shortest path on Earth's surface
- Curved paths are especially visible for long distances (e.g., New York to London)
- Press `Escape` to exit measurement mode
- Measurement events emitted to Python with distances and coordinates

See [examples/03_measurement_mode.py](examples/03_measurement_mode.py) for a complete working example.

### FeatureTableWidget

High-performance table widget for displaying and managing features:

```python
from pyopenlayersqt.features_table import FeatureTableWidget, ColumnSpec

# Define columns
columns = [
    ColumnSpec("Layer", lambda r: r.get("layer_kind", "")),
    ColumnSpec("Type", lambda r: r.get("geom_type", "")),
    ColumnSpec("ID", lambda r: r.get("feature_id", "")),
    ColumnSpec(
        "Latitude",
        lambda r: r.get("center_lat", ""),
        fmt=lambda v: f"{float(v):.6f}" if v != "" else ""
    ),
    ColumnSpec(
        "Longitude",
        lambda r: r.get("center_lon", ""),
        fmt=lambda v: f"{float(v):.6f}" if v != "" else ""
    ),
]

# Create table
table = FeatureTableWidget(
    columns=columns,
    key_fn=lambda r: (str(r.get("layer_id", "")), str(r.get("feature_id", ""))),
    debounce_ms=90
)

# Add rows
rows = [
    {
        "layer_kind": "vector",
        "layer_id": "v1",
        "feature_id": "pt1",
        "geom_type": "point",
        "center_lat": 37.7749,
        "center_lon": -122.4194
    }
]
table.append_rows(rows)

# Sync selection: table -> map
def on_table_selection(keys):
    # keys is list of (layer_id, feature_id) tuples
    for layer_id, feature_id in keys:
        # Update map selection based on layer type
        pass

table.selectionKeysChanged.connect(on_table_selection)

# Sync selection: map -> table
def on_map_selection(selection):
    keys = [(selection.layer_id, fid) for fid in selection.feature_ids]
    table.select_keys(keys, clear_first=True)

map_widget.selectionChanged.connect(on_map_selection)
```

### RangeSliderWidget

Dual-handle range slider for filtering features by numeric or timestamp ranges:

```python
from pyopenlayersqt.range_slider import RangeSliderWidget

# Numeric range slider
value_slider = RangeSliderWidget(
    min_val=0.0,
    max_val=100.0,
    step=1.0,
    label="Filter by Value"
)

# Connect to filter function
def on_value_range_changed(min_val, max_val):
    # Filter features based on value range
    visible_ids = [f["id"] for f in features if min_val <= f["value"] <= max_val]
    hidden_ids = [f["id"] for f in features if not (min_val <= f["value"] <= max_val)]
    
    # Hide/show features on map
    layer.hide_features(hidden_ids)
    layer.show_features(visible_ids)
    
    # Hide/show rows in table
    table.hide_rows_by_keys([(layer_id, fid) for fid in hidden_ids])
    table.show_rows_by_keys([(layer_id, fid) for fid in visible_ids])

value_slider.rangeChanged.connect(on_value_range_changed)

# ISO8601 timestamp range slider
timestamps = ["2024-01-01T00:00:00Z", "2024-01-15T12:00:00Z", "2024-01-31T23:59:59Z"]
timestamp_slider = RangeSliderWidget(
    values=sorted(set(timestamps)),  # Unique sorted timestamps
    label="Filter by Timestamp"
)

timestamp_slider.rangeChanged.connect(on_timestamp_range_changed)

# Reset filters
layer.show_all_features()  # Show all on map
table.show_all_rows()      # Show all in table
```

See [examples/05_range_slider_filter.py](examples/05_range_slider_filter.py) for a complete working example with map and table filtering.

## Complete Example

Here's a complete example based on the demo application. **For a working version, see [examples/02_complete_example.py](examples/02_complete_example.py).**

```python
from PySide6 import QtWidgets
from pyopenlayersqt import (
    OLMapWidget,
    PointStyle,
    FastPointsStyle,
)
from pyopenlayersqt.features_table import FeatureTableWidget, ColumnSpec
import sys
import numpy as np

class MapWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pyopenlayersqt Example")
        
        # Create map widget centered on US West Coast at appropriate zoom
        self.map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)
        
        # Add layers
        self.vector = self.map_widget.add_vector_layer("vector", selectable=True)
        
        self.fast = self.map_widget.add_fast_points_layer(
            "fast_points",
            selectable=True,
            style=FastPointsStyle(
                radius=2.5,
                default_rgba=(0, 180, 0, 180)
            )
        )
        
        # Create feature table
        columns = [
            ColumnSpec("Layer", lambda r: r.get("layer_kind", "")),
            ColumnSpec("Type", lambda r: r.get("geom_type", "")),
            ColumnSpec("ID", lambda r: r.get("feature_id", "")),
        ]
        
        self.table = FeatureTableWidget(
            columns=columns,
            key_fn=lambda r: (str(r.get("layer_id")), str(r.get("feature_id")))
        )
        
        # Connect signals
        self.map_widget.selectionChanged.connect(self.on_map_selection)
        self.table.selectionKeysChanged.connect(self.on_table_selection)
        
        # Layout
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.map_widget, 2)
        self.setCentralWidget(container)
        
        # Add data after map is ready
        self.map_widget.ready.connect(self.add_sample_data)
    
    def add_sample_data(self):
        # Add a vector point
        self.vector.add_points(
            [(37.7749, -122.4194)],
            ids=["sf"],
            style=PointStyle(radius=8.0, fill_color="#ff3333")
        )
        
        # Add to table
        self.table.append_rows([{
            "layer_kind": "vector",
            "layer_id": self.vector.id,
            "feature_id": "sf",
            "geom_type": "point"
        }])
        
        # Add fast points
        rng = np.random.default_rng()
        n = 10000
        lats = 32 + rng.random(n) * 10
        lons = -125 + rng.random(n) * 10
        coords = list(zip(lats.tolist(), lons.tolist()))
        ids = [f"fp{i}" for i in range(n)]
        self.fast.add_points(coords, ids=ids)
        
        # Add fast points to table
        rows = (
            {
                "layer_kind": "fast_points",
                "layer_id": self.fast.id,
                "feature_id": ids[i],
                "geom_type": "point"
            }
            for i in range(n)
        )
        self.table.append_rows(rows)
    
    def on_map_selection(self, selection):
        keys = [(selection.layer_id, fid) for fid in selection.feature_ids]
        self.table.select_keys(keys, clear_first=True)
    
    def on_table_selection(self, keys):
        # Group by layer
        by_layer = {}
        for layer_id, fid in keys:
            by_layer.setdefault(layer_id, []).append(fid)
        
        # Update each layer's selection
        for layer_id, fids in by_layer.items():
            if layer_id == self.vector.id:
                self.map_widget.set_vector_selection(layer_id, fids)
            elif layer_id == self.fast.id:
                self.map_widget.set_fast_points_selection(layer_id, fids)

def main():
    app = QtWidgets.QApplication(sys.argv)
    window = MapWindow()
    window.resize(1200, 800)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```

## Running the Demo

The repository includes a comprehensive demo application:

```bash
python demo/demo.py
```

The demo showcases:
- Vector layers with points, polygons, circles, and ellipses
- Fast points rendering (up to millions of points)
- Fast geo-points with uncertainty ellipses
- WMS layer integration
- Raster/heatmap overlays with custom rendering
- Feature table with bidirectional selection sync
- Dynamic styling and opacity controls

## View Extent Tracking

Monitor map extent changes for dynamic data loading:

```python
# One-time extent request
def on_extent(extent):
    print(f"Extent: {extent['lon_min']}, {extent['lat_min']} to "
          f"{extent['lon_max']}, {extent['lat_max']}")
    print(f"Zoom: {extent['zoom']}, Resolution: {extent['resolution']}")

map_widget.get_view_extent(on_extent)

# Watch extent changes (debounced)
def on_extent_changed(extent):
    # Load data for current extent
    load_data_for_extent(extent)

handle = map_widget.watch_view_extent(on_extent_changed, debounce_ms=150)

# Stop watching
handle.cancel()
```

## Advanced: Direct JavaScript Communication

For advanced use cases, you can send custom messages to the JavaScript bridge:

```python
# Send custom message to JavaScript
map_widget.send({
    "type": "custom_command",
    "param1": "value1",
    "param2": 123
})

# Listen to JavaScript events
def on_js_event(event_type, payload_json):
    print(f"Event: {event_type}, Payload: {payload_json}")

map_widget.jsEvent.connect(on_js_event)
```

## Performance Tips

1. **Use Fast Layers for Large Datasets**: For > 1000 points, use `FastPointsLayer` or `FastGeoPointsLayer` instead of vector layers
2. **Tune Cell Size**: Adjust `cell_size_m` parameter based on your data density (larger = faster, but less precise selection)
3. **Chunk Large Additions**: `FastGeoPointsLayer.add_points_with_ellipses()` automatically chunks data (default 50k points per chunk)
4. **Debounce Extent Watching**: Use appropriate `debounce_ms` when watching extent changes to avoid excessive updates
5. **Cull Tiny Ellipses**: Set `min_ellipse_px` in `FastGeoPointsStyle` to skip rendering very small ellipses
6. **Skip Ellipses While Interacting**: Enable `skip_ellipses_while_interacting` for smoother panning/zooming

## Architecture

- **Python → JavaScript**: Commands sent via `window.pyolqt_send()` 
- **JavaScript → Python**: Events sent via Qt Web Channel (`qtBridge.emitEvent()`)
- **Static Assets**: Served by embedded HTTP server (wheel-safe)
- **Raster Overlays**: Written to user cache directory and served dynamically

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Versioning and Releases

This project uses [Semantic Versioning](https://semver.org/) for version numbers (MAJOR.MINOR.PATCH).

### For Maintainers: Creating a Release

#### 1. Update the Version

Update the version number in `pyproject.toml`:

```toml
[project]
version = "X.Y.Z"  # e.g., "0.2.0"
```

#### 2. Commit the Version Change

```bash
git add pyproject.toml
git commit -m "Bump version to X.Y.Z"
git push origin main
```

#### 3. Create and Push a Git Tag

Create a tag matching the version number (with a `v` prefix):

```bash
git tag vX.Y.Z  # e.g., v0.2.0
git push origin vX.Y.Z
```

For pre-release versions, use a suffix:

```bash
git tag vX.Y.Z-alpha.1  # e.g., v0.2.0-alpha.1
git tag vX.Y.Z-beta.1   # e.g., v0.2.0-beta.1
git tag vX.Y.Z-rc.1     # e.g., v0.2.0-rc.1
git push origin vX.Y.Z-alpha.1
```

#### 4. Automated Publishing

Once the tag is pushed, GitHub Actions will automatically:
- Build the package using PEP 517 (`python -m build`)
- Publish to PyPI using trusted publishing (OIDC)

You can monitor the workflow at: https://github.com/crroush/pyopenlayersqt/actions

#### 5. Manual Workflow Trigger

You can also trigger the publish workflow manually from the GitHub Actions tab:
1. Go to https://github.com/crroush/pyopenlayersqt/actions
2. Select the "Publish to PyPI" workflow
3. Click "Run workflow"
4. Select the branch/tag to build from

### PyPI Setup Requirements

This project uses **PyPI Trusted Publishing** (OIDC), which is more secure than using API tokens.

#### Initial Setup (One-Time)

1. **Create a PyPI Account** (if you don't have one):
   - Go to https://pypi.org/account/register/

2. **Configure Trusted Publisher** on PyPI:
   - Go to https://pypi.org/manage/account/publishing/
   - Add a new pending publisher with these details:
     - **PyPI Project Name**: `pyopenlayersqt`
     - **Owner**: `crroush`
     - **Repository name**: `pyopenlayersqt`
     - **Workflow name**: `publish.yml`
     - **Environment name**: `pypi`

3. **After First Successful Publish**:
   - The pending publisher will be automatically converted to an active publisher
   - Future releases will publish automatically when you push a tag

#### Alternative: Using API Tokens

If trusted publishing is not available, you can use API tokens instead:

1. Generate a PyPI API token at https://pypi.org/manage/account/token/
2. Add it as a GitHub repository secret named `PYPI_API_TOKEN`
3. Update the workflow to use token-based authentication (see commented section in `.github/workflows/publish.yml`)

### Verification

After a release is published, verify it at:
- PyPI: https://pypi.org/project/pyopenlayersqt/
- Test installation: `pip install --upgrade pyopenlayersqt`

## Credits

Built with:
- [OpenLayers](https://openlayers.org/) - High-performance web mapping library
- [PySide6](https://doc.qt.io/qtforpython/) - Qt for Python
- [NumPy](https://numpy.org/) - Numerical computing
- [Matplotlib](https://matplotlib.org/) - Plotting and colormaps
