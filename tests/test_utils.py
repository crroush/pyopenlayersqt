"""Tests for widget.py utility functions.

Tests _to_jsonable and _is_http_url helper functions without requiring
Qt or other heavy dependencies.
"""
from dataclasses import dataclass

from pyopenlayersqt.widget import _to_jsonable, _is_http_url


def test_to_jsonable_primitives():
    """Test _to_jsonable with primitive types."""
    assert _to_jsonable("hello") == "hello"
    assert _to_jsonable(42) == 42
    assert _to_jsonable(3.14) == 3.14
    assert _to_jsonable(True) is True
    assert _to_jsonable(False) is False
    assert _to_jsonable(None) is None


def test_to_jsonable_list():
    """Test _to_jsonable with lists."""
    assert _to_jsonable([1, 2, 3]) == [1, 2, 3]
    assert _to_jsonable(["a", "b", "c"]) == ["a", "b", "c"]
    assert _to_jsonable([1, "two", 3.0, True, None]) == [1, "two", 3.0, True, None]


def test_to_jsonable_tuple():
    """Test _to_jsonable with tuples (converted to lists)."""
    assert _to_jsonable((1, 2, 3)) == [1, 2, 3]
    assert _to_jsonable(("a", "b")) == ["a", "b"]


def test_to_jsonable_dict():
    """Test _to_jsonable with dicts."""
    assert _to_jsonable({"key": "value"}) == {"key": "value"}
    assert _to_jsonable({1: "one", 2: "two"}) == {"1": "one", "2": "two"}
    assert _to_jsonable({"nested": {"a": 1, "b": 2}}) == {"nested": {"a": 1, "b": 2}}


def test_to_jsonable_nested():
    """Test _to_jsonable with nested structures."""
    data = {
        "list": [1, 2, {"inner": "value"}],
        "tuple": (4, 5, 6),
        "dict": {"key": [7, 8, 9]},
    }
    expected = {
        "list": [1, 2, {"inner": "value"}],
        "tuple": [4, 5, 6],
        "dict": {"key": [7, 8, 9]},
    }
    assert _to_jsonable(data) == expected


def test_to_jsonable_dataclass():
    """Test _to_jsonable with dataclasses."""
    @dataclass
    class Point:
        x: int
        y: int
    
    @dataclass
    class Line:
        start: Point
        end: Point
        name: str
    
    point1 = Point(x=1, y=2)
    assert _to_jsonable(point1) == {"x": 1, "y": 2}
    
    line = Line(start=Point(0, 0), end=Point(10, 10), name="diagonal")
    expected = {
        "start": {"x": 0, "y": 0},
        "end": {"x": 10, "y": 10},
        "name": "diagonal"
    }
    assert _to_jsonable(line) == expected


def test_to_jsonable_fallback():
    """Test _to_jsonable fallback to str for unknown types."""
    class CustomClass:
        def __str__(self):
            return "custom_object"
    
    obj = CustomClass()
    assert _to_jsonable(obj) == "custom_object"
    
    # Complex object that can't be serialized - just check it's converted to string
    obj_result = _to_jsonable(object())
    assert isinstance(obj_result, str)
    assert obj_result.startswith("<object object at 0x")


def test_is_http_url_valid():
    """Test _is_http_url with valid HTTP/HTTPS URLs."""
    assert _is_http_url("http://example.com") is True
    assert _is_http_url("https://example.com") is True
    assert _is_http_url("http://localhost:8080/path") is True
    assert _is_http_url("https://sub.domain.com/path?query=1") is True
    assert _is_http_url("  http://example.com  ") is True  # With whitespace


def test_is_http_url_invalid():
    """Test _is_http_url with non-HTTP URLs and other strings."""
    assert _is_http_url("ftp://example.com") is False
    assert _is_http_url("file:///path/to/file") is False
    assert _is_http_url("/absolute/path") is False
    assert _is_http_url("relative/path") is False
    assert _is_http_url("example.com") is False
    assert _is_http_url("") is False
    assert _is_http_url("  ") is False
    assert _is_http_url("data:image/png;base64,iVBOR...") is False
