import time
import unittest
from types import SimpleNamespace

from PySide6 import QtCore, QtWidgets
from PySide6.QtWebEngineCore import QWebEnginePage

from pyopenlayersqt import OLMapWidget


class ReadinessPollingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def wait_for(self, predicate):
        deadline = time.monotonic() + 10
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail('Timed out waiting for readiness polling')
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(10, loop.quit)
            loop.exec()

    def test_polling_recovers_readiness_without_a_webchannel_event(self):
        page = QWebEnginePage()
        owner = SimpleNamespace(_js_ready=False, _page_generation=0, page=lambda: page)
        results = []

        def checked(value):
            results.append(value)
            owner._js_ready = value is True

        owner._on_pyolqt_ready_check = checked
        loaded = []
        page.loadFinished.connect(loaded.append)
        try:
            page.setHtml('<script>window.pyolqt_is_ready = () => true;</script>')
            self.wait_for(lambda: bool(loaded))
            self.assertTrue(loaded[-1])
            OLMapWidget._on_load_finished(owner, True)
            self.wait_for(lambda: bool(results))
            self.assertIs(results[-1], True)
        finally:
            owner._js_ready = True
            page.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
