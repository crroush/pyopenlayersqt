import json

from webengine_helpers import WebEngineTestCase


class ReloadTests(WebEngineTestCase):
    def test_reload_reinitializes_and_allows_ready_handler_to_rebuild(self):
        widget = self.make_map(inject_webchannel=True, center=(40, -105), zoom=5)
        resets, layers = [], []
        widget.mapReset.connect(lambda: resets.append(True))

        def build_layers():
            layer = widget.add_vector_layer('rebuilt')
            layer.add_points([(40, -105)], ids=['marker'])
            layers.append(layer)

        widget.ready.connect(build_layers)
        self.wait_for(lambda: len(layers) == 1)
        self.assertEqual(self.js('window._pyolqt_state.layers.size'), 1)
        previous_layer = layers[0]
        raster = widget.add_raster_layer('temporary')
        raster.set_image(b'cached image', [(0, 0), (1, 1)])
        self.assertEqual(len(widget._overlay_files), 1)
        previous_generation = widget._page_generation
        widget.reload()
        self.wait_for(lambda: len(layers) == 2)
        self.assertEqual(resets, [True])
        self.assertEqual(widget._overlay_files, {})
        self.assertEqual(len(self.ready_events), 2)
        self.assertEqual(self.js('window._pyolqt_state.layers.size'), 1)
        self.assertEqual(self.js('window._pyolqt_state.layers.get(' + json.dumps(layers[1].id) + ').source.getFeatures().map(f => f.getId())'), ['marker'])
        center = self.js('ol.proj.toLonLat(window._pyolqt_state.map.getView().getCenter())')
        self.assertAlmostEqual(center[0], -105)
        self.assertAlmostEqual(center[1], 40)
        with self.assertRaisesRegex(RuntimeError, 'recreate layers'):
            previous_layer.add_points([(0, 0)])
        with self.assertRaisesRegex(RuntimeError, 'recreate layers'):
            widget.set_vector_selection(previous_layer.id, ['marker'])
        widget._pending.append({'type': 'map.set_view', 'zoom': 9})
        widget._flush_next_pending(previous_generation)
        self.assertEqual(len(widget._pending), 1)
        widget._flush_pending()
        self.wait_for(lambda: not widget._pending_flush_active)
        self.assertEqual(self.js('window._pyolqt_state.map.getView().getZoom()'), 9)
