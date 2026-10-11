import json

from webengine_helpers import WebEngineTestCase


class WebChannelStartupTests(WebEngineTestCase):
    def test_real_map_becomes_ready_and_drains_startup_features(self):
        widget = self.make_map()
        layer = widget.add_vector_layer('startup')
        layer.add_points([(40, -105)], ids=['marker'])
        self.wait_for(lambda: self.ready_events)
        self.assertEqual(self.js('window._pyolqt_state.layers.get(' + json.dumps(layer.id) + ').source.getFeatures().map(f => f.getId())'), ['marker'])
        self.assertTrue(self.js('window.pyolqt_is_ready()'))
