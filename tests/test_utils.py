"""Tests for utility functions in widget.py.

Tests _to_jsonable behavior with nested dataclasses, primitive types, lists,
dicts, and fallbacks to str for unknown types.

Tests _is_http_url with valid and invalid URLs.
"""

from dataclasses import dataclass

import pytest

from pyopenlayersqt.widget import _to_jsonable, _is_http_url


class TestToJsonable:
    """Tests for _to_jsonable function."""
    
    def test_primitives(self):
        """Test that primitive types are returned as-is."""
        assert _to_jsonable("hello") == "hello"
        assert _to_jsonable(42) == 42
        assert _to_jsonable(3.14) == 3.14
        assert _to_jsonable(True) is True
        assert _to_jsonable(False) is False
        assert _to_jsonable(None) is None
    
    def test_list(self):
        """Test that lists are converted recursively."""
        assert _to_jsonable([1, 2, 3]) == [1, 2, 3]
        assert _to_jsonable(["a", "b", "c"]) == ["a", "b", "c"]
        assert _to_jsonable([1, "two", 3.0]) == [1, "two", 3.0]
    
    def test_tuple(self):
        """Test that tuples are converted to lists."""
        assert _to_jsonable((1, 2, 3)) == [1, 2, 3]
        assert _to_jsonable(("a", "b")) == ["a", "b"]
    
    def test_dict(self):
        """Test that dicts are converted recursively with string keys."""
        assert _to_jsonable({"a": 1, "b": 2}) == {"a": 1, "b": 2}
        assert _to_jsonable({1: "one", 2: "two"}) == {"1": "one", "2": "two"}
    
    def test_nested_structures(self):
        """Test nested lists and dicts."""
        data = {"items": [1, 2, 3], "nested": {"key": "value"}}
        expected = {"items": [1, 2, 3], "nested": {"key": "value"}}
        assert _to_jsonable(data) == expected
        
        data = [{"a": 1}, {"b": 2}]
        expected = [{"a": 1}, {"b": 2}]
        assert _to_jsonable(data) == expected
    
    def test_dataclass(self):
        """Test that dataclasses are converted to dicts via asdict."""
        @dataclass
        class Point:
            x: int
            y: int
        
        p = Point(x=10, y=20)
        result = _to_jsonable(p)
        assert result == {"x": 10, "y": 20}
    
    def test_nested_dataclass(self):
        """Test nested dataclasses."""
        @dataclass
        class Point:
            x: int
            y: int
        
        @dataclass
        class Line:
            start: Point
            end: Point
        
        line = Line(start=Point(0, 0), end=Point(10, 10))
        result = _to_jsonable(line)
        expected = {
            "start": {"x": 0, "y": 0},
            "end": {"x": 10, "y": 10}
        }
        assert result == expected
    
    def test_unknown_type_fallback(self):
        """Test that unknown types fall back to str()."""
        class CustomClass:
            def __str__(self):
                return "custom"
        
        obj = CustomClass()
        assert _to_jsonable(obj) == "custom"
    
    def test_mixed_types(self):
        """Test mixing various types together."""
        @dataclass
        class Config:
            name: str
            value: int
        
        data = {
            "config": Config("test", 42),
            "items": [1, 2, (3, 4)],
            "flag": True,
        }
        
        result = _to_jsonable(data)
        expected = {
            "config": {"name": "test", "value": 42},
            "items": [1, 2, [3, 4]],
            "flag": True,
        }
        assert result == expected


class TestIsHttpUrl:
    """Tests for _is_http_url function."""
    
    def test_http_urls(self):
        """Test that http:// URLs are recognized."""
        assert _is_http_url("http://example.com") is True
        assert _is_http_url("http://localhost:8080") is True
        assert _is_http_url("http://127.0.0.1") is True
    
    def test_https_urls(self):
        """Test that https:// URLs are recognized."""
        assert _is_http_url("https://example.com") is True
        assert _is_http_url("https://www.google.com") is True
        assert _is_http_url("https://api.github.com/repos") is True
    
    def test_with_whitespace(self):
        """Test that URLs with leading/trailing whitespace work."""
        assert _is_http_url("  http://example.com  ") is True
        assert _is_http_url("\thttps://example.com\n") is True
    
    def test_non_http_urls(self):
        """Test that non-http(s) URLs are rejected."""
        assert _is_http_url("ftp://example.com") is False
        assert _is_http_url("file:///path/to/file") is False
        assert _is_http_url("ws://example.com") is False
        assert _is_http_url("wss://example.com") is False
    
    def test_relative_paths(self):
        """Test that relative paths are rejected."""
        assert _is_http_url("path/to/file") is False
        assert _is_http_url("./relative/path") is False
        assert _is_http_url("../parent/path") is False
    
    def test_absolute_paths(self):
        """Test that absolute file paths are rejected."""
        assert _is_http_url("/absolute/path") is False
        assert _is_http_url("/home/user/file.txt") is False
    
    def test_empty_string(self):
        """Test that empty string is rejected."""
        assert _is_http_url("") is False
        assert _is_http_url("   ") is False
    
    def test_plain_text(self):
        """Test that plain text without protocol is rejected."""
        assert _is_http_url("example.com") is False
        assert _is_http_url("www.example.com") is False
