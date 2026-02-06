# Coordinate Display Box - Before and After Fix

## Problem
The coordinate display box was changing size when coordinates had different numbers of digits.

### Before Fix (4 decimal places, no fixed width):
```
Small coordinates (1 digit):
┌─────────────────┐
│ Lat: 1.2345     │  <- Narrow box
│ Lon: 2.3456     │
└─────────────────┘

Medium coordinates (2 digits):
┌──────────────────────┐
│ Lat: 37.7749         │  <- Medium box
│ Lon: -122.4194       │
└──────────────────────┘

Large negative (3 digits):
┌───────────────────────────┐
│ Lat: -123.4567            │  <- Wide box (PROBLEM!)
│ Lon: -145.6789            │
└───────────────────────────┘
```

The box kept resizing, creating a jarring visual effect.

## Solution
1. Increased precision to 6 decimal places (as requested)
2. Added `min-width: 270px` to fix the box size
3. Added `box-sizing: border-box` for consistent layout

### After Fix (6 decimal places, fixed width):
```
All coordinate ranges now use the SAME box size:

Small coordinates (1 digit):
┌─────────────────────────────────┐
│ Lat: 1.234567, Lon: 2.345678    │  <- Fixed 270px
└─────────────────────────────────┘

Medium coordinates (2 digits):
┌─────────────────────────────────┐
│ Lat: 37.774900, Lon: -122.419400│  <- Fixed 270px
└─────────────────────────────────┘

Large negative (3 digits):
┌─────────────────────────────────┐
│ Lat: -123.456789, Lon: -145.6789│  <- Fixed 270px
└─────────────────────────────────┘

Zero coordinates:
┌─────────────────────────────────┐
│ Lat: 0.000000, Lon: 0.000000    │  <- Fixed 270px
└─────────────────────────────────┘

Maximum range:
┌─────────────────────────────────┐
│ Lat: -89.999999, Lon: 179.999999│  <- Fixed 270px
└─────────────────────────────────┘
```

## Changes Made

### JavaScript (ol_bridge.js)
```javascript
// Before:
const lon = lonlat[0].toFixed(4);
const lat = lonlat[1].toFixed(4);

// After:
const lon = lonlat[0].toFixed(6);
const lat = lonlat[1].toFixed(6);
```

```javascript
// Before (no fixed width):
coordElement.style.cssText = 
  'position: absolute; ' +
  'bottom: 8px; ' +
  'right: 8px; ' +
  // ... other styles ...
  'display: none;';

// After (with fixed width):
coordElement.style.cssText = 
  'position: absolute; ' +
  'bottom: 8px; ' +
  'right: 8px; ' +
  // ... other styles ...
  'display: none; ' +
  'min-width: 270px; ' +           // NEW: Fixed minimum width
  'box-sizing: border-box;';       // NEW: Consistent box model
```

## Benefits

✅ **Fixed Box Size**: Box no longer resizes when moving mouse to different locations
✅ **Higher Precision**: 6 decimal places provides ~0.11m accuracy (vs ~11m with 4 decimals)
✅ **Better UX**: Stable, non-jumping UI element
✅ **Handles All Cases**: Works for positive, negative, 1-3 digit coordinates

## Testing

Run the test:
```bash
python test_coordinate_precision.py
```

All coordinate ranges now display consistently with the same box width!
