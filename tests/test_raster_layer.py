"""Tests for creating and populating raster layers."""

import unittest

from pyopenlayersqt.models import RasterStyle
from pyopenlayersqt.widget import OLMapWidget


class _MapWidgetStub:
    def __init__(self):
        self.commands = []

    def _next_id(self, prefix):
        return f"{prefix}1"

    def _ensure_overlay_url(self, image):
        return f"overlay://{image}"

    def _send(self, command):
        self.commands.append(command)


class RasterLayerTests(unittest.TestCase):
    def test_add_raster_layer_then_set_and_remove_image(self):
        widget = _MapWidgetStub()

        layer = OLMapWidget.add_raster_layer(
            widget, style=RasterStyle(opacity=0.4), name="pending"
        )

        self.assertIsNone(layer.url)
        self.assertIsNone(layer.bounds)
        self.assertEqual(widget.commands[0]["type"], "layer.add_raster")

        layer.set_image("image.png", bounds=[(1.0, 2.0), (3.0, 4.0)])

        self.assertEqual(layer.url, "overlay://image.png")
        self.assertEqual(layer.bounds, [(1.0, 2.0), (3.0, 4.0)])
        self.assertEqual(
            widget.commands[1],
            {
                "type": "raster.set_image",
                "layer_id": "r1",
                "url": "overlay://image.png",
                "bounds": [[2.0, 1.0], [4.0, 3.0]],
            },
        )

        layer.remove_image()

        self.assertIsNone(layer.url)
        self.assertIsNone(layer.bounds)
        self.assertEqual(
            widget.commands[2],
            {"type": "raster.remove_image", "layer_id": "r1"},
        )


if __name__ == "__main__":
    unittest.main()
