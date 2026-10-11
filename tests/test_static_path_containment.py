import http.client
import tempfile
import unittest
from pathlib import Path

from pyopenlayersqt.widget import _StaticServer


class StaticPathContainmentTests(unittest.TestCase):
    def test_traversal_and_symlink_escapes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, overlays = root / 'package', root / 'overlays'
            package.mkdir()
            overlays.mkdir()
            marker = root / 'marker.txt'
            marker.write_bytes(b'private marker')
            (package / 'escape').symlink_to(root, target_is_directory=True)
            (overlays / 'escape').symlink_to(root, target_is_directory=True)
            (package / 'valid name.txt').write_bytes(b'public asset')
            (overlays / 'valid name.txt').write_bytes(b'public overlay')
            server = _StaticServer(package, overlays)
            host, port = server.start()
            connection = http.client.HTTPConnection(host, port, timeout=5)
            try:
                for path in ('/../marker.txt', '/%2e%2e/marker.txt', '/_overlays/../marker.txt', '/_overlays/%2e%2e%2fmarker.txt', '/escape/marker.txt', '/_overlays/escape/marker.txt', '/_overlays/' + str(marker)):
                    for method in ('GET', 'HEAD'):
                        with self.subTest(path=path, method=method):
                            connection.request(method, path)
                            response = connection.getresponse()
                            self.assertEqual(response.status, 403)
                            self.assertNotIn(b'private marker', response.read())
                for path, expected in (('/valid%20name.txt?v=1', b'public asset'), ('/_overlays/valid%20name.txt', b'public overlay')):
                    connection.request('GET', path)
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), expected)
            finally:
                connection.close()
                server.stop()
