import http.client
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pyopenlayersqt.widget import OLMapWidget, _StaticServer


class AbsoluteRasterPathTests(unittest.TestCase):
    def test_absolute_paths_are_copied_and_served(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            overlays = root / 'overlays'
            overlays.mkdir()
            source = root / 'mounted image.png'
            source.write_bytes(b'\x89PNG\r\n\x1a\nexample')
            fake = SimpleNamespace(_overlays_dir=overlays)
            fake._write_overlay_file = OLMapWidget._write_overlay_file.__get__(fake)
            server = _StaticServer(root, overlays)
            host, port = server.start()
            try:
                for image in (str(source), source):
                    url = OLMapWidget._ensure_overlay_url(fake, image)
                    self.assertTrue(url.startswith('/_overlays/'))
                    connection = http.client.HTTPConnection(host, port, timeout=5)
                    connection.request('GET', url)
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), source.read_bytes())
                    connection.close()
            finally:
                server.stop()

    def test_server_paths_and_remote_urls_remain_usable(self):
        for url in ('/_overlays/test.png?ts=1', '/vendor/test.png', '/resources/test.png', 'https://example.com/test.png'):
            self.assertEqual(OLMapWidget._ensure_overlay_url(None, url), url)
