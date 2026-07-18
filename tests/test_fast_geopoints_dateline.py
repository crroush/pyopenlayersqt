import base64
import importlib.util
import sys
import types
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def _load_layers_module():
    package = types.ModuleType("pyopenlayersqt")
    package.__path__ = [str(ROOT / "pyopenlayersqt")]
    sys.modules.setdefault("pyopenlayersqt", package)
    for name in ("utils", "models", "layers"):
        module_name = f"pyopenlayersqt.{name}"
        if module_name in sys.modules:
            continue
        spec = importlib.util.spec_from_file_location(
            module_name, ROOT / "pyopenlayersqt" / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return sys.modules["pyopenlayersqt.layers"]


class RecordingMap:
    def __init__(self):
        self.messages = []

    def _send(self, message):
        self.messages.append(message)


def _decode_float64_array(encoded, shape):
    data = base64.b64decode(encoded)
    return np.frombuffer(data, dtype=np.float64).reshape(shape)


def test_fast_points_accepts_dateline_centers_without_normalizing():
    FastPointsLayer = _load_layers_module().FastPointsLayer
    layer = FastPointsLayer(RecordingMap(), "dateline", "Dateline")

    coords = [(0.0, 179.99), (0.0, -179.99), (1.0, 180.0), (-1.0, -180.0)]
    layer.add_points(coords, ids=["east", "west", "east_wrap", "west_wrap"])

    assert len(layer._map_widget.messages) == 1
    message = layer._map_widget.messages[0]
    assert message["type"] == "fast_points.add_points"
    assert message["point_count"] == len(coords)
    lonlat = _decode_float64_array(message["coords_b64"], (len(coords), 2))
    np.testing.assert_allclose(
        lonlat,
        np.array([[179.99, 0.0], [-179.99, 0.0], [180.0, 1.0], [-180.0, -1.0]], dtype=np.float64),
    )


def test_fast_geopoints_accepts_dateline_ellipse_centers_without_normalizing():
    FastGeoPointsLayer = _load_layers_module().FastGeoPointsLayer
    layer = FastGeoPointsLayer(RecordingMap(), "dateline", "Dateline")

    coords = [(0.0, 179.99), (0.0, -179.99), (1.0, 180.0), (-1.0, -180.0)]
    layer.add_points_with_ellipses(
        coords,
        sma_m=[5_000.0, 5_000.0, 10_000.0, 10_000.0],
        smi_m=[1_000.0, 1_000.0, 2_000.0, 2_000.0],
        tilt_deg=[0.0, 45.0, 90.0, 135.0],
        ids=["east", "west", "east_wrap", "west_wrap"],
    )

    assert len(layer._map_widget.messages) == 1
    message = layer._map_widget.messages[0]
    assert message["type"] == "fast_geopoints.add_points"
    assert message["point_count"] == len(coords)
    lonlat = _decode_float64_array(message["coords_b64"], (len(coords), 2))
    np.testing.assert_allclose(
        lonlat,
        np.array([[179.99, 0.0], [-179.99, 0.0], [180.0, 1.0], [-180.0, -1.0]], dtype=np.float64),
    )


def test_fast_layer_renderer_wraps_dateline_objects_to_view_extent():
    bridge_js = (ROOT / "pyopenlayersqt/resources/ol_bridge.js").read_text()

    assert "function pyolqt_wrap_x_for_extent" in bridge_js
    assert "pyolqt_query_extent_for_render(extent)" in bridge_js
    assert "const wrappedX = pyolqt_wrap_x_for_extent(entry.x[i], extent);" in bridge_js
    assert "const wrappedX = pyolqt_wrap_x_for_extent(mercX, extent);" in bridge_js
    assert "extent[0] - ellipseRadius" in bridge_js
