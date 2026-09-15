import unittest

import numpy as np

from pyopenlayersqt.apps.csv_plotter import _selection_mask


class SelectionMaskTests(unittest.TestCase):
    def test_indices_take_precedence_and_out_of_range_values_are_ignored(self):
        result = _selection_mask(4, [-1, 0, 2, 9], ["pt_1"], [])

        np.testing.assert_array_equal(result, [True, False, True, False])

    def test_feature_ids_are_resolved_when_indices_are_unavailable(self):
        result = _selection_mask(
            4,
            [],
            ["pt_1", "pt_3"],
            ["pt_0", "pt_1", "pt_2", "pt_3"],
        )

        np.testing.assert_array_equal(result, [False, True, False, True])

    def test_selection_is_restricted_to_rows_admitted_by_filters(self):
        result = _selection_mask(
            4,
            [0, 1, 2, 3],
            [],
            [],
            [False, True, False, True],
        )

        np.testing.assert_array_equal(result, [False, True, False, True])


if __name__ == "__main__":
    unittest.main()
