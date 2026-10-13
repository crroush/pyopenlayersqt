import http.client
import tempfile
import unittest
from pathlib import Path

from PySide6 import QtCore
from pyopenlayersqt.widget import PKG_DIR, _StaticServer


class WebChannelHttpTests(unittest.TestCase):
    def test_map_loads_qt_script_from_its_http_origin(self):
        with tempfile.TemporaryDirectory() as overlays:
            server = _StaticServer(PKG_DIR, Path(overlays))
            host, port = server.start()
            try:
                connection = http.client.HTTPConnection(host, port, timeout=5)
                connection.request('GET', '/resources/map.html')
                html = connection.getresponse().read().decode()
                self.assertIn('src="/qtwebchannel/qwebchannel.js"', html)
                self.assertNotIn('qrc:', html)
                connection.request('GET', '/qtwebchannel/qwebchannel.js?v=1')
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertIn('javascript', response.getheader('Content-Type'))
                resource = QtCore.QFile(':/qtwebchannel/qwebchannel.js')
                self.assertTrue(resource.open(QtCore.QIODevice.ReadOnly))
                try:
                    expected = bytes(resource.readAll())
                finally:
                    resource.close()
                self.assertEqual(response.read(), expected)
                connection.request('HEAD', '/qtwebchannel/qwebchannel.js')
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(int(response.getheader('Content-Length')), len(expected))
                self.assertEqual(response.read(), b'')
                connection.close()
            finally:
                server.stop()
