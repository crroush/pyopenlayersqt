#!/usr/bin/env python3
"""
Validate the coordinate display feature implementation.
This script checks that the feature is correctly integrated.
"""

import inspect
from pyopenlayersqt import OLMapWidget


def test_show_coordinates_parameter():
    """Test that the show_coordinates parameter exists and has the right default."""
    # Get the __init__ signature
    sig = inspect.signature(OLMapWidget.__init__)
    
    # Check that show_coordinates parameter exists
    assert 'show_coordinates' in sig.parameters, "show_coordinates parameter not found in __init__"
    
    # Check that the default is True
    param = sig.parameters['show_coordinates']
    assert param.default is True, f"show_coordinates default should be True, got {param.default}"
    
    print("✓ show_coordinates parameter exists with default=True")


def test_widget_initialization():
    """Test that the widget can be initialized with show_coordinates parameter."""
    try:
        # Test with default (True)
        widget1 = OLMapWidget()
        assert hasattr(widget1, '_show_coordinates'), "Widget missing _show_coordinates attribute"
        assert widget1._show_coordinates is True, "Default show_coordinates should be True"
        print("✓ Widget initializes with show_coordinates=True by default")
        
        # Test with explicit False
        widget2 = OLMapWidget(show_coordinates=False)
        assert widget2._show_coordinates is False, "show_coordinates=False not respected"
        print("✓ Widget initializes with show_coordinates=False when specified")
        
        # Test with explicit True
        widget3 = OLMapWidget(show_coordinates=True)
        assert widget3._show_coordinates is True, "show_coordinates=True not respected"
        print("✓ Widget initializes with show_coordinates=True when specified")
        
    except Exception as e:
        print(f"✗ Widget initialization failed: {e}")
        raise


def test_docstring():
    """Test that the docstring mentions show_coordinates."""
    docstring = OLMapWidget.__init__.__doc__
    assert docstring is not None, "No docstring found"
    assert 'show_coordinates' in docstring, "show_coordinates not documented in docstring"
    print("✓ show_coordinates is documented in the docstring")


def main():
    """Run all validation tests."""
    print("Validating coordinate display feature implementation...\n")
    
    try:
        test_show_coordinates_parameter()
        test_widget_initialization()
        test_docstring()
        
        print("\n✅ All validation tests passed!")
        return 0
    except AssertionError as e:
        print(f"\n❌ Validation failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
