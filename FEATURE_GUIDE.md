# Mouse Coordinate Display Feature - Visual Guide

## Feature Overview

This document describes the visual appearance and behavior of the mouse coordinate display feature.

## Visual Appearance

```
┌─────────────────────────────────────────────────────────────┐
│                                                               │
│                      MAP AREA                                 │
│                                                               │
│                                                               │
│                                                               │
│                                                               │
│                                                               │
│                                   ┌─────────────────────────┐ │
│                                   │ Lat: 37.774900          │ │
│                                   │ Lon: -122.419400        │ │
│                                   └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
     ↑
     Coordinate bubble appears here in lower-right corner
     (Fixed width: 270px minimum)
```

## Styling Details

**Coordinate Bubble:**
- **Position**: Fixed in lower-right corner (8px from bottom, 8px from right)
- **Background**: Semi-transparent white (rgba(255, 255, 255, 0.9))
- **Text Color**: Dark gray (#333)
- **Font**: Monospace, 12px
- **Padding**: 6px vertical, 10px horizontal
- **Border Radius**: 4px (rounded corners)
- **Shadow**: Subtle box shadow (0 1px 4px rgba(0,0,0,0.3))
- **Z-index**: 1000 (appears on top of map)
- **Pointer Events**: None (doesn't interfere with map interactions)
- **Min Width**: 270px (fixed size to prevent resizing with different coordinate lengths)
- **Box Sizing**: border-box (includes padding in width calculation)

## Behavior

### When Enabled (default)
1. User moves mouse over map
2. Coordinate bubble appears in lower-right corner
3. Coordinates update in real-time (throttled to 50ms for performance)
4. Format: "Lat: XX.XXXXXX, Lon: YY.YYYYYY" (6 decimal places)
5. Bubble disappears when mouse leaves map area

### When Disabled
- No coordinate bubble appears
- Mouse movement has no effect on coordinate display

## Usage Examples

### Example 1: Default (Coordinates Enabled)
```python
from pyopenlayersqt import OLMapWidget

# Coordinates will be displayed (default behavior)
map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)
```

### Example 2: Coordinates Disabled
```python
from pyopenlayersqt import OLMapWidget

# Coordinates will NOT be displayed
map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6, show_coordinates=False)
```

## Technical Implementation

### JavaScript Side (ol_bridge.js)
- **State Management**: Uses `coordinateOverlay` and `coordinatePointerMoveKey` in state
- **Event Handling**: Listens to OpenLayers' `pointermove` event
- **Coordinate Transformation**: Converts from Web Mercator (EPSG:3857) to WGS84 (EPSG:4326)
- **Performance**: Throttled to update at most every 50ms (20 updates per second)
- **Security**: Uses `textContent` instead of `innerHTML` to prevent XSS

### Python Side (widget.py)
- **Parameter**: `show_coordinates: bool = True` in `__init__`
- **Command**: Sends `coordinates.set_visible` message to JavaScript on map ready
- **Default**: Enabled by default for immediate user feedback

## Coordinate Precision

- **Decimal Places**: 6 (e.g., 37.774900, -122.419400)
- **Precision**: Approximately 0.11 meters at the equator
- **Format**: Always shows 6 decimal places (e.g., 0.000000 for coordinates near origin)
- **Fixed Width**: Box has a minimum width of 270px to prevent resizing when coordinates change

## Edge Cases Handled

1. **Mouse outside map**: Bubble is hidden
2. **Invalid coordinates**: Bubble is hidden
3. **Map not initialized**: No error, silently fails
4. **Rapid mouse movement**: Throttled to prevent performance issues
5. **Toggle visibility**: Can be changed dynamically via command

## Performance Characteristics

- **Update Frequency**: Maximum 20 times per second (50ms throttle)
- **DOM Updates**: Minimal - only updates text content and display style
- **Event Listeners**: Single `pointermove` listener when enabled
- **Memory**: Single DOM element, minimal state

## Accessibility

- **Non-Intrusive**: Uses `pointer-events: none` so it doesn't block map interactions
- **Visual Contrast**: White background with dark text for readability
- **Position**: Fixed position ensures it's always visible when enabled
