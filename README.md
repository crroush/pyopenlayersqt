# pyopenlayersqt

OpenLayers + Qt (QWebEngine) mapping widget for Python.

A high-performance, feature-rich mapping widget that embeds OpenLayers in a Qt application using QWebEngine. Designed for displaying and interacting with large volumes of geospatial data.
<img width="803" height="467" alt="image" src="https://github.com/user-attachments/assets/0d607680-b16a-46ed-9562-eeb00525cf02" />

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
  - [Deleting Features](#deleting-features)
  - [Distance Measurement Mode](#distance-measurement-mode)
  - [FeatureTableWidget](#featuretablewidget)
  - [RangeSliderWidget](#rangesliderwidget)
- [Complete Example](#complete-example)
- [View Extent Tracking](#view-extent-tracking)
- [Advanced: Direct JavaScript Communication](#advanced-direct-javascript-communication)
- [Performance Tips](#performance-tips)
- [Architecture](#architecture)
- [License](#license)
- [Contributing](#contributing)
- [Credits](#credits)


## Features

- **🗺️ Interactive Map Widget**: Fully-featured OpenLayers map embedded in PySide6/Qt
- **⚡ High-Performance Rendering**: Fast points layers with spatial indexing for millions of points
- **🎨 Rich Styling**: Customizable styles for points, polygons, circles, and ellipses
- **🎨 QColor Support**: Use `QColor` objects or color names directly in styles - no `.name()` needed
- **📍 Geolocation Support**: Fast geo-points layer with uncertainty ellipses
- **🌐 WMS Integration**: Built-in Web Map Service layer support
- **🖼️ Raster Overlays**: PNG/ overlay support with custom bounds
- **✅ Feature Selection**: Interactive feature selection with Python ↔ JavaScript sync
- **🎯 Smart Z-Ordering**: Selected points and ellipses automatically appear on top
- **📊 Feature Table Widget**: High-performance table widget for displaying and managing features
- **🔄 Bidirectional Sync**: Seamless selection synchronization between map and table
- **📏 Distance Measurement**: Interactive measurement mode with geodesic distance calculations and great-circle path visualization
- **🎚️ Range Slider Widget**: Dual-handle range slider for filtering features by numeric or timestamp ranges

## Installation

```bash
pip install pyopenlayersqt
```

### Requirements

- Python >= 3.8
- PySide6 >= 6.5
- numpy >= 1.23
- pillow >= 10.0
- matplotlib >= 3.7
- pyqtgraph >= 0.13 *(optional, needed for example 16 only)*

## Quick Start

```python
from PySide6 import QtWidgets
from PySide6.QtGui import QColor
from pyopenlayersqt import OLMapWidget, PointStyle
import sys

app = QtWidgets.QApplication(sys.argv)

# Create the map widget with custom initial view
map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)

# Add a vector layer
vector_layer = map_widget.add_vector_layer("my_layer", selectable=True)

# Add some points with QColor styling
coords = [(37.7749, -122.4194), (34.0522, -118.2437)]  # SF, LA
vector_layer.add_points(
    coords,
    ids=["sf", "la"],
    style=PointStyle(radius=8.0, fill_color=QColor("red"))
)

# Show the map
map_widget.show()
sys.exit(app.exec())
```

See the [examples directory](examples/) for more working examples:
- `01_basic_map_with_markers.py` - Basic map with QColor markers (start here!)
- `02_layer_types_and_styling.py` - All geometry types with QColor
- `03_fast_points_performance.py` - High-performance rendering (10,000+ points)
- `04_wms_and_base_layers.py` - WMS integration and opacity control
- `05_raster_overlay.py` - Raster/heatmap visualization with in-memory PNG bytes
- `06_geo_uncertainty_ellipses.py` - Geolocation uncertainty with ellipses
- `07_feature_selection.py` - Interactive selection across layers
- `08_table_integration.py` - Bidirectional map-table sync (CORE)
- `09_selection_and_recoloring.py` - Interactive recoloring (CORE)
- `10_range_slider_filtering.py` - Range slider filtering
- `11_measurement_tool.py` - Distance measurement tool
- `12_coordinate_display.py` - Coordinate display toggle
- `13_dual_table_linking.py` - Two-table parent/child map-table selection workflow
- `14_delayed_render_interrupt.py` - Debounced, interruptible process-based heatmap rendering
- `15_load_data_and_zoom.py` - Load features, then click a button to auto-zoom to loaded data
- `16_time_series_map_table_plot.py` - 100k time-series tri-directional selection sync (map ↔ table ↔ pyqtgraph plot)

## Core Components

### OLMapWidget

The main widget class that embeds an OpenLayers map.

```python
from pyopenlayersqt import OLMapWidget

# Create with default world view (center at 0,0, zoom level 2)
map_widget = OLMapWidget()

# Or create with custom initial view
map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)

# Programmatically adjust view later (no mouse interaction needed)
map_widget.set_center((34.0522, -118.2437))
map_widget.set_zoom(10)
# or set both at once
map_widget.set_view(center=(40.7128, -74.0060), zoom=12)

# Auto-zoom to all currently relevant points/features
feature_points = [
    (37.7749, -122.4194),
    (34.0522, -118.2437),
    (36.1699, -115.1398),
]
map_widget.auto_zoom_to_points(feature_points, padding_px=32, max_zoom=12)

# Or simply fit to all data already loaded in map layers
map_widget.fit_to_data()
```

### Programmatic Zoom & Resolution Reference

OpenLayers uses the standard Web Mercator zoom model. This means zoom levels map
predictably to resolution (meters per pixel at the equator):

`resolution_m_per_px = 156543.03392804097 / (2 ** zoom)`

You can query this directly in Python with:

```python
resolution = OLMapWidget.zoom_resolution_m_per_px(zoom)
```

Approximate full-world horizontal extent represented by each zoom level:

| Zoom | Resolution (m/px) | Approx. horizontal extent on a 256 px tile (km) |
|------|-------------------:|-------------------------------------------------:|
| 0    | 156543.0339        | 40075.02 |
| 1    | 78271.5170         | 20037.51 |
| 2    | 39135.7585         | 10018.75 |
| 3    | 19567.8792         | 5009.38  |
| 4    | 9783.9396          | 2504.69  |
| 5    | 4891.9698          | 1252.34  |
| 6    | 2445.9849          | 626.17   |
| 7    | 1222.9925          | 313.09   |
| 8    | 611.4962           | 156.54   |
| 9    | 305.7481           | 78.27    |
| 10   | 152.8741           | 39.14    |
| 11   | 76.4370            | 19.57    |
| 12   | 38.2185            | 9.78     |
| 13   | 19.1093            | 4.89     |
| 14   | 9.5546             | 2.45     |
| 15   | 4.7773             | 1.22     |
| 16   | 2.3887             | 0.61     |

Notes:
- "Extent" above is an equatorial approximation and varies with viewport size.
- For the actual current extent of your map widget, use `get_view_extent(callback)`.
- For feature-driven workflows (e.g., after adding a batch of points), use `fit_to_data()` for a one-call auto-fit across loaded layers, or `auto_zoom_to_points(...)` / `fit_bounds(...)` when you want explicit control.
<img width="515" height="401" alt="image" src="https://github.com/user-attachments/assets/6dbe1d15-cb28-4b68-a182-ec677a01e651" />

**Constructor Parameters:**

- `parent` - Optional parent widget
- `center` - Initial map center as `(lat, lon)` tuple. Defaults to `(0, 0)`.
- `zoom` - Initial zoom level (integer). Defaults to `2` (world view).
- `show_coordinates` - If True, displays mouse lat/lon coordinates in the lower right corner. Defaults to `True`.

**Key Methods:**

- `add_vector_layer(name, selectable=True)` - Create a vector layer for points, polygons, circles, ellipses
- `add_fast_points_layer(name, selectable, style, cell_size_m)` - Create a high-performance points layer
- `add_fast_geopoints_layer(name, selectable, style, cell_size_m)` - Create a geo-points layer with uncertainty ellipses
- `add_wms(options, name)` - Add a WMS (Web Map Service) layer
- `add_raster_image(image, bounds, style, name)` - Add a raster image overlay
- `set_base_opacity(opacity)` - Set OSM base layer opacity (0.0-1.0)
- `set_measure_mode(enabled)` - Enable/disable interactive distance measurement mode
- `on_measurement_updated(callback)` - Register a typed callback for measurement click updates
- `clear_measurements()` - Clear all measurement points and lines
- `set_view(center=None, zoom=None)` - Programmatically set map center and/or zoom
- `set_center((lat, lon))` - Programmatically set map center
- `set_zoom(zoom)` - Programmatically set map zoom level
- `fit_bounds(bounds, padding_px, max_zoom, duration_ms)` - Auto-fit map view to SW/NE bounds
- `auto_zoom_to_points(points, padding_px, max_zoom, duration_ms)` - Auto-fit map view to a list of feature points
- `fit_to_data(padding_px, max_zoom, duration_ms, ...)` - Auto-fit map view to data already in map layers
- `zoom_resolution_m_per_px(zoom)` - Return Web Mercator resolution (m/px) for a zoom level
- `get_view_extent(callback)` - Get current map extent asynchronously
- `watch_view_extent(callback, debounce_ms)` - Subscribe to extent changes

**Signals:**

- `ready` - Emitted when the map is ready
- `selectionChanged` - Emitted when feature selection changes
- `viewExtentChanged` - Emitted when map extent changes
- `measurementUpdated` - Emitted when a measurement point is added. Signal(object) carrying a `MeasurementUpdate` instance.
- `jsEvent` - Emitted for low-level JavaScript events. Signal(str, str) with event type and JSON payload.

### Layer Types

All layer types in pyopenlayersqt inherit from a common `BaseLayer` class, providing consistent functionality across different layer implementations.

#### Common Layer Methods

All layers (VectorLayer, FastPointsLayer, FastGeoPointsLayer, WMSLayer, RasterLayer) support these core methods:

```python
# Set layer opacity (0.0 = transparent, 1.0 = opaque)
layer.set_opacity(0.7)

# Remove the layer from the map
layer.remove()
```

**Feature-based layers** (VectorLayer, FastPointsLayer, FastGeoPointsLayer) also support:

```python
# Show/hide the layer
layer.set_visible(True)

# Enable/disable feature selection
layer.set_selectable(True)

# Clear all features from the layer
layer.clear()
```

Each layer type also has specialized methods for its specific use case, as detailed below.

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
        fill_color=QColor("red"),
        fill_opacity=0.85,
        stroke_color=QColor("black"),
        stroke_width=1.0
    )
)

# Add polygons
vector.add_polygon(
    ring=[(lat1, lon1), (lat2, lon2), ...],
    feature_id="poly1",
    style=PolygonStyle(
        stroke_color=QColor("dodgerblue"),
        stroke_width=2.0,
        fill_color=QColor("dodgerblue"),
        fill_opacity=0.15
    )
)

# Add lines (polylines)
vector.add_line(
    coords=[(lat1, lon1), (lat2, lon2), (lat3, lon3)],
    feature_id="ln1",
    style=PolygonStyle(
        stroke_color=QColor("dodgerblue"),
        stroke_width=2.0
    )
)

# Add circles (radius in meters)
vector.add_circle(
    center=(lat, lon),
    radius_m=1000.0,
    feature_id="circle1",
    style=CircleStyle(stroke_color=QColor("dodgerblue"), fill_opacity=0.15)
)

# Add ellipses (semi-major/minor axes in meters, tilt in degrees from north)
vector.add_ellipse(
    center=(lat, lon),
    sma_m=2000.0,  # Semi-major axis
    smi_m=1200.0,  # Semi-minor axis
    tilt_deg=45.0,  # Tilt from true north
    feature_id="ell1",
    style=EllipseStyle(stroke_color=QColor("gold"), fill_opacity=0.12)
)

# Update styles of specific features (e.g., selected features)
feature_ids = ["id1", "id2"]
new_styles = [
    PointStyle(radius=8.0, fill_color=QColor("red"), fill_opacity=1.0),
    PointStyle(radius=8.0, fill_color=QColor("green"), fill_opacity=1.0),
]
vector.update_feature_styles(feature_ids, new_styles)

# Remove features
vector.remove_features(["id1", "poly1"])

# Clear all features
vector.clear()
```
<img width="603" height="416" alt="image" src="https://github.com/user-attachments/assets/a9ec05ba-717b-494a-abab-eac30adb55fb" />

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
        default_color="green",  # Color name or QColor
        selected_radius=6.0,
        selected_color="yellow"
    ),
    cell_size_m=750.0  # Spatial index cell size
)

# Add points (efficient for large datasets)
coords = [(lat, lon), ...]  # millions of points
ids = [f"pt{i}" for i in range(len(coords))]

# Option 1: Single color for all points
fast.add_points(coords, ids=ids)

# Option 2: Per-point colors using QColor objects
from PySide6.QtGui import QColor
colors = [QColor(255, 0, 0, 180), QColor(0, 255, 0, 180), ...]
fast.add_points(coords, ids=ids, colors_rgba=colors)

# Option 3: Per-point colors using color names
colors = ["red", "green", "blue", ...]
fast.add_points(coords, ids=ids, colors_rgba=colors)

# Remove specific points
fast.remove_points(["pt1", "pt2"])

# Update colors of specific points (e.g., selected points)
feature_ids = ["pt10", "pt25", "pt50"]
# Use QColor objects (recommended)
from PySide6.QtGui import QColor
new_colors = [QColor("red"), QColor("green"), QColor("blue")]
fast.set_colors(feature_ids, new_colors)
# Or color names
new_colors = ["red", "green", "blue"]
fast.set_colors(feature_ids, new_colors)

# Temporarily hide/show features (without removing them)
fast.hide_features(["pt100", "pt200"])
fast.show_features(["pt100"])
fast.show_all_features()  # Show all hidden features

# Clear all points
fast.clear()
```
<img width="603" height="416" alt="image" src="https://github.com/user-attachments/assets/dbff66f1-b649-4232-8afd-5a3b1f619b43" />

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
        default_color="steelblue",  # Color name or QColor
        selected_point_radius=6.0,
        selected_color="white",
        # Ellipse styling
        ellipse_stroke_color="steelblue",
        ellipse_stroke_width=1.2,
        fill_ellipses=False,
        ellipse_fill_color=QColor(40, 80, 255, 40),
        # Behavior
        ellipses_visible=True,
        selected_ellipses_visible=True,  # Independent toggle for selected ellipses
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

# Toggle selected-ellipse visibility independently
fast_geo.set_selected_ellipses_visible(False)

# Update colors of specific points (e.g., selected points)
feature_ids = ["geo5", "geo12", "geo20"]
# Use QColor objects (recommended)
from PySide6.QtGui import QColor
new_colors = [QColor("red"), QColor("green"), QColor("blue")]
fast_geo.set_colors(feature_ids, new_colors)
# Or color names
new_colors = ["red", "green", "blue"]
fast_geo.set_colors(feature_ids, new_colors)

# Temporarily hide/show features (without removing them)
fast_geo.hide_features(["geo100", "geo200"])
fast_geo.show_features(["geo100"])
fast_geo.show_all_features()  # Show all hidden features

# Remove points
fast_geo.remove_ids(["geo1", "geo2"])

# Clear all
fast_geo.clear()
```
<img width="603" height="416" alt="image" src="https://github.com/user-attachments/assets/00098627-e9ec-4e75-9a86-03aeeb3da1e5" />

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
<img width="603" height="416" alt="image" src="https://github.com/user-attachments/assets/413956f3-6df8-4141-813d-08419c5da10e" />

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
<img width="603" height="416" alt="image" src="https://github.com/user-attachments/assets/2ff33448-afcd-42fc-9b0a-91066ee84202" />

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
from PySide6.QtGui import QColor

# Vector styles use QColor objects or color names (recommended)
point_style = PointStyle(
    radius=5.0,
    fill_color=QColor("red"),        # QColor object (recommended)
    fill_opacity=0.85,
    stroke_color=QColor("black"),    # QColor object
    stroke_width=1.0,
    stroke_opacity=0.9
)

# You can also use color names directly
polygon_style = PolygonStyle(
    stroke_color="red",    # Color name string
    fill_color="green"     # Color name string
)

# Fast layer styles support QColor/color names (recommended)
# Recommended: Using QColor objects or color names
fast_style_qcolor = FastPointsStyle(
    radius=3.0,
    default_color=QColor("steelblue"),  # QColor object
    selected_radius=6.0,
    selected_color="orange"              # Color name string
)

# Legacy (deprecated): Using RGBA tuples
fast_style = FastPointsStyle(
    radius=3.0,
    default_rgba=(255, 51, 51, 204),
    selected_radius=6.0,
    selected_rgba=(0, 255, 255, 255)
)

# Mixed: Both styles (color options take precedence)
fast_style_mixed = FastPointsStyle(
    radius=3.0,
    default_rgba=(255, 51, 51, 204),     # Fallback
    default_color="purple",               # This takes precedence
    selected_radius=6.0,
    selected_color=QColor("yellow")       # This takes precedence
)

# FastGeoPointsStyle supports QColor for all colors (points and ellipses)
geo_style = FastGeoPointsStyle(
    point_radius=4.0,
    default_color="darkgreen",                    # Point color (QColor or color name)
    selected_color=QColor("red"),                 # Selected point color
    ellipse_stroke_color="darkgreen",             # Ellipse stroke color
    ellipse_fill_color=QColor(0, 100, 0, 40),    # Ellipse fill color (with alpha)
    selected_ellipse_stroke_color="red",          # Selected ellipse stroke color
    fill_ellipses=True,
    ellipses_visible=True,
    selected_ellipses_visible=True            # Hide/show selected ellipses independently
)
```

**Key Features:**
- **QColor Support in ALL Styles**: Pass `QColor` objects directly to any color parameter in PointStyle, CircleStyle, PolygonStyle, EllipseStyle, FastPointsStyle, and FastGeoPointsStyle - no need for `.name()`
- **Color Names Everywhere**: Use color names like `"red"`, `"Green"`, `"steelblue"` directly in all Style classes
- **Multiple Formats**: All styles accept QColor objects, color names, hex strings, and CSS strings (RGBA tuples are deprecated)
- **Backward Compatible**: Existing code using RGBA tuples or hex colors continues to work
- **Z-Ordering**: Selected points and ellipses are automatically drawn on top in dense areas

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

For updating styles of selected features, see the layer-specific methods documented above:
- `VectorLayer.update_feature_styles()` - Update styles for vector features
- `FastPointsLayer.set_colors()` - Update colors for fast points
- `FastGeoPointsLayer.set_colors()` - Update colors for fast geo-points
- `FastGeoPointsLayer.set_selected_ellipses_visible()` - Toggle selected ellipse outlines independently from unselected ellipses

**Multi-layer selection workflow example:**
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
    from PySide6.QtGui import QColor
    for layer_id, feature_ids in selections.items():
        if layer_id == vector_layer.id:
            styles = [PointStyle(fill_color="red") for _ in feature_ids]
            vector_layer.update_feature_styles(feature_ids, styles)
        elif layer_id == fast_layer.id:
            colors = [QColor("red") for _ in feature_ids]
            fast_layer.set_colors(feature_ids, colors)
        elif layer_id == fast_geo_layer.id:
            colors = [QColor("red") for _ in feature_ids]
            fast_geo_layer.set_colors(feature_ids, colors)
```

See [examples/09_selection_and_recoloring.py](examples/09_selection_and_recoloring.py) for a complete interactive example.

### Deleting Features

Each layer type provides methods to remove features, either individually, in batches, or all at once.

#### VectorLayer Deletion

```python
# Remove specific features by ID
vector_layer.remove_features(["point1", "polygon2", "circle3"])

# Clear all features from the layer
vector_layer.clear()
```

#### FastPointsLayer Deletion

```python
# Remove specific points by ID
fast_layer.remove_points(["pt1", "pt2", "pt100"])

# Clear all points from the layer
fast_layer.clear()
```

#### FastGeoPointsLayer Deletion

```python
# Remove specific geo-points by ID
geo_layer.remove_ids(["geo1", "geo2", "geo50"])

# Clear all geo-points from the layer
geo_layer.clear()
```

#### Deleting Selected Features

A common pattern is to delete features that the user has selected interactively:

```python
from PySide6.QtGui import QShortcut, QKeySequence

# Track selections across all layers
selections = {}

def on_selection_changed(selection):
    """Update the selections dictionary when selection changes."""
    if len(selection.feature_ids) > 0:
        selections[selection.layer_id] = selection.feature_ids
    elif selection.layer_id in selections:
        del selections[selection.layer_id]

map_widget.selectionChanged.connect(on_selection_changed)

def delete_selected():
    """Delete all currently selected features across all layers."""
    for layer_id, feature_ids in list(selections.items()):
        if layer_id == vector_layer.id:
            vector_layer.remove_features(feature_ids)
        elif layer_id == fast_layer.id:
            fast_layer.remove_points(feature_ids)
        elif layer_id == geo_layer.id:
            geo_layer.remove_ids(feature_ids)
    
    # Clear selections after deletion
    selections.clear()
    print(f"Deleted features")

# Connect to a button
delete_button.clicked.connect(delete_selected)

# Or add keyboard shortcut (Delete key)
delete_shortcut = QShortcut(QKeySequence.Delete, map_widget)
delete_shortcut.activated.connect(delete_selected)
```

#### Removing Entire Layers

To remove an entire layer from the map:

```python
# Remove the layer (also removes all its features)
vector_layer.remove()
fast_layer.remove()
geo_layer.remove()
```

**Complete CRUD Example:** See [examples/08_table_integration.py](examples/08_table_integration.py) for a full working example demonstrating Create, Read, Update, and Delete operations with interactive add/delete buttons and keyboard shortcuts across all layer types.

### Distance Measurement Mode

Interactive distance measurement with geodesic calculations and a clean callback API:

```python
from pyopenlayersqt import MeasurementUpdate

# Enable measurement mode
map_widget.set_measure_mode(True)

# Listen for typed measurement updates
def on_measurement(update: MeasurementUpdate):
    if update.segment_distance_m is not None:
        print(f"Segment: {update.segment_distance_m:.1f} m")
    print(f"Total: {update.cumulative_distance_m:.1f} m")
    print(f"Point at ({update.lat:.5f}, {update.lon:.5f})")

handle = map_widget.on_measurement_updated(on_measurement)
# (Optional) also available as a Qt signal:
# map_widget.measurementUpdated.connect(on_measurement)

# Clear all measurements
map_widget.clear_measurements()

# Stop callback if needed
handle.cancel()

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
- Measurement updates emitted to Python as `MeasurementUpdate` objects with distances and coordinates

See [examples/11_measurement_tool.py](examples/11_measurement_tool.py) for a complete working example.
<img width="653" height="416" alt="image" src="https://github.com/user-attachments/assets/90479971-749a-43e2-8534-58b3cb0ecd6c" />

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

# Optional: built-in right-click menu actions
from pyopenlayersqt.features_table import ContextMenuActionSpec


def view_metadata(event):
    # event.keys -> [(layer_id, feature_id), ...]
    # event.rows -> underlying row objects for selected rows
    print("Metadata:", event.rows)


def delete_selected(event):
    if event.keys:
        table.remove_keys(event.keys)


table.set_context_menu_actions([
    ContextMenuActionSpec("View Metadata", view_metadata),
    ContextMenuActionSpec("Delete Selected", delete_selected),
])

# Optional hook for custom menus owned by your GUI code
# table.contextMenuRequested.connect(on_context_menu_requested)
```

#### Row removal APIs: `remove_keys` vs `remove_where`

`FeatureTableWidget` provides two row-removal methods for different use cases:

- `table.remove_keys(keys)`
  - Use when you already know the exact `(layer_id, feature_id)` keys to remove.
  - Best for map-driven actions like deleting selected features from one or more
    layers, because keys are already available from selection events.
  - Example:

    ```python
    selected_keys = table.selected_keys()  # [(layer_id, feature_id), ...]
    if selected_keys:
        table.remove_keys(selected_keys)
    ```

- `table.remove_where(predicate)`
  - Use when removal logic depends on arbitrary row attributes/conditions rather
    than known keys.
  - Example:

    ```python
    # Remove all rows from a specific layer kind
    table.remove_where(lambda row: row.get("layer_kind") == "geo_points")
    ```

In short: prefer `remove_keys` for explicit feature-ID removals (typical CRUD
flows), and `remove_where` for ad-hoc, attribute-based filtering/removal.

### RangeSliderWidget

Dual-handle range slider for filtering features by numeric or timestamp ranges:

```python
from pyopenlayersqt.range_slider import RangeSliderWidget
from pyopenlayersqt import FastPointsStyle

# Create a fast points layer (required for hide/show features)
fast_layer = map_widget.add_fast_points_layer(
    "filterable_points",
    selectable=True,
    style=FastPointsStyle(radius=3.0, default_color="green")
)

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
    
    # Hide/show features on map (FastPointsLayer and FastGeoPointsLayer only)
    if hidden_ids:
        fast_layer.hide_features(hidden_ids)
    if visible_ids:
        fast_layer.show_features(visible_ids)
    
    # Hide/show rows in table
    layer_id = fast_layer.id
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

# Reset filters - show all features again
fast_layer.show_all_features()  # Show all on map
table.show_all_rows()  # Show all in table
```

See [examples/10_range_slider_filtering.py](examples/10_range_slider_filtering.py) for a complete working example with map and table filtering.
<img width="703" height="467" alt="image" src="https://github.com/user-attachments/assets/e3462ace-cc19-44fc-8200-42a6bcd7ad26" />

## Complete Example

For a comprehensive demonstration of all features, see the complete working example at [examples/08_table_integration.py](examples/08_table_integration.py). This example includes:
- Vector and fast points layers
- Feature table with bidirectional selection sync
- Sample data generation
- Layer management

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

For maintainers, see [CONTRIBUTING.md](CONTRIBUTING.md) for information on creating releases and publishing to PyPI.

## Credits

Built with:
- [OpenLayers](https://openlayers.org/) - High-performance web mapping library
- [PySide6](https://doc.qt.io/qtforpython/) - Qt for Python
- [NumPy](https://numpy.org/) - Numerical computing
- [Matplotlib](https://matplotlib.org/) - Plotting and colormaps
