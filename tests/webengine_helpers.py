import json
import time
import unittest

from PySide6 import QtCore, QtWidgets
from PySide6.QtWebEngineCore import QWebEngineScript
from pyopenlayersqt import OLMapWidget


class WebEngineTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def make_map(self, inject_webchannel=False, **kwargs):
        self.widget = OLMapWidget(show_osm_layer=False, **kwargs)
        self.widget.resize(640, 480)
        self.ready_events = []
        self.widget.ready.connect(lambda: self.ready_events.append(True))
        if inject_webchannel:
            # Keep unrelated regression tests runnable before the HTTP
            # WebChannel fix is merged. Production startup tests do not inject.
            resource = QtCore.QFile(':/qtwebchannel/qwebchannel.js')
            assert resource.open(QtCore.QIODevice.ReadOnly)
            script = QWebEngineScript()
            script.setInjectionPoint(QWebEngineScript.DocumentCreation)
            script.setWorldId(QWebEngineScript.MainWorld)
            script.setSourceCode(bytes(resource.readAll()).decode())
            resource.close()
            self.widget.page().scripts().insert(script)
        self.widget.show()
        return self.widget

    def wait_for(self, predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail('Timed out waiting for WebEngine')
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(10, loop.quit)
            loop.exec()

    def js(self, expression):
        result = []
        self.widget.page().runJavaScript('JSON.stringify(' + expression + ')', result.append)
        self.wait_for(lambda: bool(result))
        return json.loads(result[0])

    def tearDown(self):
        if hasattr(self, 'widget'):
            self.widget.close()
            self.widget.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
