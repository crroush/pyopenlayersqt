import unittest

from PySide6 import QtWidgets
from PySide6.QtGui import QColor, QImage, QPalette

from pyopenlayersqt.time_histogram_slider import GraphicalTimeSlider


class HistogramRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.slider = GraphicalTimeSlider()
        self.slider.resize(640, 240)
        self.slider.show()
        self.app.processEvents()

    def tearDown(self):
        self.slider.close()
        self.slider.deleteLater()

    def rendered_heights(self, values, sample_positions):
        def render():
            image = QImage(self.slider.size(), QImage.Format_ARGB32)
            self.slider.render(image)
            return image

        self.slider.setDistributionValues([])
        empty = render()
        self.slider.setDistributionValues(values)
        filled = render()
        plot = self.slider._plot_rect()
        heights = []
        for position in sample_positions:
            start, end, _ = next(
                item for item in self.slider._bins if item[0] <= position < item[1]
            )
            left = self.slider._extent_value_to_pos(start)
            right = self.slider._extent_value_to_pos(end)
            x = (left + right - 1) // 2
            heights.append(sum(
                empty.pixel(x, y) != filled.pixel(x, y)
                for y in range(plot.top() + 1, plot.bottom())
            ))
        return heights

    def test_sparse_bins_are_visible_and_empty_bins_stay_blank(self):
        values = [10] * 20000 + [30] * 10000 + [60] + [70] * 2 + [80] * 3
        for background in ('#ffffff', '#202020'):
            with self.subTest(background=background):
                palette = self.slider.palette()
                palette.setColor(QPalette.Window, QColor(background))
                self.slider.setPalette(palette)
                peak, half, empty, *sparse = self.rendered_heights(values, [10, 30, 50, 60, 70, 80])
                self.assertTrue(all(height >= 3 for height in sparse), sparse)
                self.assertEqual(empty, 0)
                self.assertAlmostEqual(half, peak / 2, delta=2)
                self.assertEqual(sum(count for _, _, count in self.slider._bins), len(values))

    def test_zoom_reaggregates_sparse_counts_and_rescales_the_bars(self):
        values = [10] * 20000 + [60] + [70] * 2 + [80] * 3
        full_heights = self.rendered_heights(values, [60, 70, 80])
        self.slider.setExtentRange(50, 90)
        zoomed_heights = self.rendered_heights(values, [60, 70, 80])
        self.assertEqual(sum(count for _, _, count in self.slider._bins), 6)
        self.assertLess(zoomed_heights[0], zoomed_heights[1])
        self.assertLess(zoomed_heights[1], zoomed_heights[2])
        self.assertTrue(all(zoomed > full for zoomed, full in zip(zoomed_heights, full_heights)))
