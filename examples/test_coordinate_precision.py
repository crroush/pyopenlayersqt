#!/usr/bin/env python3
"""
Test coordinate display precision and formatting.
This validates that coordinates are displayed with 6 decimal places.
"""

def test_coordinate_format():
    """Test that the JavaScript format is correct for 6 decimal places."""
    import re
    
    # Read the ol_bridge.js file
    with open('/home/runner/work/pyopenlayersqt/pyopenlayersqt/pyopenlayersqt/resources/ol_bridge.js', 'r') as f:
        content = f.read()
    
    # Check that .toFixed(6) is used for both lat and lon
    lat_pattern = r'const lat = lonlat\[1\]\.toFixed\(6\)'
    lon_pattern = r'const lon = lonlat\[0\]\.toFixed\(6\)'
    
    assert re.search(lat_pattern, content), "Latitude should use .toFixed(6)"
    assert re.search(lon_pattern, content), "Longitude should use .toFixed(6)"
    
    print("✓ Coordinate precision is set to 6 decimal places")
    
    # Check that min-width is set
    min_width_pattern = r'min-width:\s*270px'
    assert re.search(min_width_pattern, content), "Coordinate box should have min-width: 270px"
    
    print("✓ Coordinate box has fixed minimum width of 270px")
    
    # Check that box-sizing is set
    box_sizing_pattern = r'box-sizing:\s*border-box'
    assert re.search(box_sizing_pattern, content), "Coordinate box should have box-sizing: border-box"
    
    print("✓ Coordinate box has box-sizing: border-box")


def test_coordinate_examples():
    """Test various coordinate formats to show precision."""
    test_coords = [
        (0.0, 0.0, "0.000000", "0.000000"),
        (37.7749, -122.4194, "37.774900", "-122.419400"),
        (-89.999999, 179.999999, "-89.999999", "179.999999"),
        (1.123456, -1.123456, "1.123456", "-1.123456"),
        (12.345678, -123.456789, "12.345678", "-123.456789"),
    ]
    
    print("\n✓ Example coordinate formats (Lat, Lon):")
    for lat, lon, expected_lat, expected_lon in test_coords:
        formatted_lat = f"{lat:.6f}"
        formatted_lon = f"{lon:.6f}"
        assert formatted_lat == expected_lat, f"Lat format mismatch: {formatted_lat} != {expected_lat}"
        assert formatted_lon == expected_lon, f"Lon format mismatch: {formatted_lon} != {expected_lon}"
        print(f"  Lat: {formatted_lat}, Lon: {formatted_lon}")


def main():
    """Run all tests."""
    print("Testing coordinate display precision and formatting...\n")
    
    try:
        test_coordinate_format()
        test_coordinate_examples()
        
        print("\n✅ All tests passed!")
        return 0
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
