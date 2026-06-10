"""Tests for custom icon source normalization."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PySide6.QtCore import QByteArray

from pyopenlayersqt.layers import VectorLayer
from pyopenlayersqt.widget import OLMapWidget


SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'


class _IconSourceHarness:
    """Exercise OLMapWidget icon helpers without constructing QWebEngine."""

    _cache_icon_file = OLMapWidget._cache_icon_file
    _cache_icon_bytes = OLMapWidget._cache_icon_bytes
    _icon_to_src = OLMapWidget._icon_to_src

    def __init__(self, overlays_dir: Path):
        self._overlays_dir = overlays_dir
        self._base_url = "http://127.0.0.1:1234"
        self.sent = []

    def _send(self, message):
        self.sent.append(message)


class IconSourceTests(unittest.TestCase):
    """Verify every documented icon source type becomes browser-loadable."""

    def test_byte_containers_are_cached_as_images(self):
        with TemporaryDirectory() as temp_dir:
            harness = _IconSourceHarness(Path(temp_dir))

            for value in (
                SVG_BYTES,
                bytearray(SVG_BYTES),
                memoryview(SVG_BYTES),
                QByteArray(SVG_BYTES),
            ):
                with self.subTest(source_type=type(value).__name__):
                    src = harness._icon_to_src(value)
                    self.assertTrue(src.endswith(".svg"))
                    cached_path = Path(temp_dir) / "icons" / src.rsplit("/", 1)[-1]
                    self.assertEqual(cached_path.read_bytes(), SVG_BYTES)

    def test_path_object_and_path_string_are_cached(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            icon_path = temp_path / "pin.svg"
            icon_path.write_bytes(SVG_BYTES)
            harness = _IconSourceHarness(temp_path / "cache")

            path_src = harness._icon_to_src(icon_path)
            string_src = harness._icon_to_src(str(icon_path))

            self.assertEqual(path_src, string_src)
            self.assertTrue(path_src.endswith(".svg"))

    def test_browser_loadable_sources_pass_through(self):
        with TemporaryDirectory() as temp_dir:
            harness = _IconSourceHarness(Path(temp_dir))
            sources = (
                "https://example.com/pin.svg",
                "http://example.com/pin.svg",
                "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=",
                "file:///tmp/pin.svg",
                "qrc:/icons/pin.svg",
            )

            for source in sources:
                with self.subTest(source=source):
                    self.assertEqual(harness._icon_to_src(source), source)

    def test_add_icon_points_normalizes_qbytearray_icons(self):
        with TemporaryDirectory() as temp_dir:
            harness = _IconSourceHarness(Path(temp_dir))
            layer = VectorLayer(harness, "icons")

            layer.add_icon_points(
                [(37.7749, -122.4194)],
                icon=QByteArray(SVG_BYTES),
                selected_icon=QByteArray(SVG_BYTES + b" "),
                ids=["qbytearray"],
            )

            style = harness.sent[0]["style"]
            self.assertTrue(style["icon_src"].endswith(".svg"))
            self.assertTrue(style["selected_icon_src"].endswith(".svg"))
            self.assertNotEqual(style["icon_src"], style["selected_icon_src"])


if __name__ == "__main__":
    unittest.main()
