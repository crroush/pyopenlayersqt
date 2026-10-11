import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pyopenlayersqt.apps import csv_plotter


class ChromiumFlagsTests(unittest.TestCase):
    def test_gpu_option_preserves_existing_flags_before_qt_starts(self):
        for flags in ('', '--no-sandbox --disable-dev-shm-usage --proxy-server="http://localhost:1234"'):
            with self.subTest(flags=flags), patch.dict(os.environ, {'QTWEBENGINE_CHROMIUM_FLAGS': flags}):
                app = Mock()
                app.exec.return_value = 0

                def create_app(_args):
                    self.assertEqual(os.environ['QTWEBENGINE_CHROMIUM_FLAGS'], (flags + ' --disable-gpu').strip())
                    return app

                with patch.object(csv_plotter, 'parse_args', return_value=SimpleNamespace(disable_gpu=True)), \
                     patch.object(csv_plotter.QtWidgets, 'QApplication', side_effect=create_app), \
                     patch.object(csv_plotter, 'PyOpenLayersCsvApp'):
                    self.assertEqual(csv_plotter.main(), 0)
