import socket
import unittest

from PySide6 import QtCore, QtWidgets
from pyopenlayersqt import OLMapWidget


class MapServerLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_parent_destruction_stops_the_embedded_server(self):
        parent = QtWidgets.QWidget()
        widget = OLMapWidget(parent, show_osm_layer=False)
        server = widget._server
        thread = server._thread
        port = server.port
        parent.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', port), timeout=1)

    def test_close_then_delete_is_idempotent(self):
        widget = OLMapWidget(show_osm_layer=False)
        server = widget._server
        widget.close()
        widget.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertIsNone(server._httpd)
