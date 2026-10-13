import json

from webengine_helpers import WebEngineTestCase


class VectorSelectionTests(WebEngineTestCase):
    def setUp(self):
        widget = self.make_map(inject_webchannel=True)
        self.first = widget.add_vector_layer('parent')
        self.second = widget.add_vector_layer('child')
        self.first.add_points([(40, -105)], ids=['parent'])
        self.second.add_points([(40.1, -105)], ids=['child'])
        self.events = []
        widget.selectionChanged.connect(self.events.append)
        self.wait_for(lambda: self.ready_events)

    def selected(self):
        return self.js('window._pyolqt_state.selectInteraction.getFeatures().getArray().map(f => f.getId()).sort()')

    def select_both(self):
        self.widget.set_vector_selection(self.first.id, ['parent'], emit=False)
        self.widget.set_vector_selection(self.second.id, ['child'], emit=False)
        self.assertEqual(self.selected(), ['child', 'parent'])

    def test_selection_and_clear_are_scoped_to_the_target_layer(self):
        self.select_both()
        self.second.clear()
        self.assertEqual(self.selected(), ['parent'])
        self.wait_for(lambda: self.events)
        self.assertEqual(self.events[-1].layer_id, self.second.id)
        self.assertEqual(self.events[-1].feature_ids, [])

    def test_deleted_features_and_removed_layers_leave_selection(self):
        self.select_both()
        self.second.remove_features(['child'])
        self.assertEqual(self.selected(), ['parent'])
        self.first.remove()
        self.assertEqual(self.selected(), [])
        self.wait_for(lambda: len(self.events) == 2)
        self.assertEqual({event.layer_id for event in self.events}, {self.first.id, self.second.id})
        self.assertTrue(all(event.feature_ids == [] for event in self.events))

    def test_click_deselection_emits_an_empty_selection(self):
        self.widget.set_vector_selection(self.first.id, ['parent'], emit=False)
        layer_id = json.dumps(self.first.id)
        self.js('(() => { const interaction = window._pyolqt_state.selectInteraction; '
                'const feature = window._pyolqt_state.layers.get(' + layer_id + ').source.getFeatureById("parent"); '
                'interaction.getFeatures().clear(); interaction.dispatchEvent({type: "select", selected: [], deselected: [feature]}); return true; })()')
        self.wait_for(lambda: self.events)
        self.assertEqual(self.events[-1].layer_id, self.first.id)
        self.assertEqual(self.events[-1].feature_ids, [])
