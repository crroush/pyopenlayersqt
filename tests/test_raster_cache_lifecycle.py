import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

from PySide6 import QtCore, QtWidgets
from pyopenlayersqt.layers import RasterLayer
from pyopenlayersqt.widget import OLMapWidget


class RasterCacheTests(unittest.TestCase):
    def test_replacement_is_bounded_and_clear_releases_only_its_layer(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = SimpleNamespace(_overlays_dir=Path(directory), _overlay_files={}, _send=lambda message: None)
            for name in ('_release_overlay_cache', '_write_overlay_file', '_ensure_overlay_url'):
                setattr(fake, name, getattr(OLMapWidget, name).__get__(fake))
            first, second = RasterLayer(fake, 'a'), RasterLayer(fake, 'b')
            bounds = [(0, 0), (1, 1)]
            urls = []
            for index in range(25):
                first.set_image(str(index).encode(), bounds, name='heatmap')
                urls.append(first.images['heatmap']['url'])
            self.assertEqual(len(set(urlsplit(url).path for url in urls)), 1)
            self.assertEqual(len(set(urls)), 25)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
            self.assertEqual(next(Path(directory).iterdir()).read_bytes(), b'24')
            first.set_image(urls[-1], bounds, name='heatmap')
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
            with patch('pyopenlayersqt.widget.os.replace', side_effect=OSError('write failed')):
                with self.assertRaises(OSError):
                    first.set_image(b'failed update', bounds, name='heatmap')
            self.assertEqual(next(Path(directory).iterdir()).read_bytes(), b'24')
            second.set_image(b'other layer', bounds, name='heatmap')
            first.clear()
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
            second.remove_image('heatmap')
            self.assertEqual(list(Path(directory).iterdir()), [])
            second.set_image(b'removed layer', bounds)
            second.remove()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_switch_to_remote_url_releases_owned_file(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = SimpleNamespace(_overlays_dir=Path(directory), _overlay_files={})
            for name in ('_release_overlay_cache', '_write_overlay_file', '_ensure_overlay_url'):
                setattr(fake, name, getattr(OLMapWidget, name).__get__(fake))
            fake._ensure_overlay_url(b'local', cache_key=('a', 'image'))
            self.assertEqual(fake._ensure_overlay_url('https://example.com/image.png', cache_key=('a', 'image')), 'https://example.com/image.png')
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_widget_caches_are_isolated_and_removed_on_destruction(self):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        parent = QtWidgets.QWidget()
        first, second = OLMapWidget(parent), OLMapWidget(parent)
        paths = [first._overlays_dir, second._overlays_dir]
        servers = [first._server, second._server]
        self.assertNotEqual(*paths)
        parent.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertTrue(all(not path.exists() for path in paths))
        # Server destruction is covered by a separate fix.
        for server in servers:
            server.stop()
