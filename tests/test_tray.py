import unittest
from unittest.mock import Mock, patch

from app.qt.QtWidgets import QApplication
from main import MainWindow


class TrayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch("main.load_presets", return_value={}), patch.object(MainWindow, "_setup_system_tray"):
            self.window = MainWindow()
        self.tray = Mock()
        self.tray.isVisible.return_value = True
        self.window._tray_icon = self.tray
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._exit_requested = True
        with patch.object(self.window, "_save_last_session"):
            self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_close_hides_open_restores_and_quit_saves(self):
        with patch.object(self.window, "_save_last_session") as save:
            self.window.close()
            self.assertFalse(self.window.isVisible())
            save.assert_not_called()
            self.window._show_from_tray()
            self.assertTrue(self.window.isVisible())
            with patch.object(QApplication, "quit") as quit_app:
                self.window._quit_from_tray()
            save.assert_called_once()
            quit_app.assert_called_once()
            self.tray.hide.assert_called_once()

    def test_unavailable_tray_closes_normally(self):
        self.tray.isVisible.return_value = False
        with patch.object(self.window, "_save_last_session") as save:
            self.window.close()
        save.assert_called_once()
