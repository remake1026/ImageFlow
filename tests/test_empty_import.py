"""Empty-workspace double clicks and their interaction with photo preview."""
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from app.importer import ImportResult
from app.qt.QtCore import Qt
from app.qt.QtWidgets import QApplication
from qt_test_support import QTest
from main import MainWindow


class EmptyImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch('main.load_presets', return_value={}), patch.object(MainWindow, '_setup_system_tray'):
            self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._exit_requested = True
        with patch.object(self.window, '_save_last_session'):
            self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def targets(self):
        return (self.window.photo_list.viewport(), self.window.canvas)

    def double_click(self, widget, button=Qt.MouseButton.LeftButton):
        QTest.mouseDClick(widget, button, pos=widget.rect().center())

    def import_one(self):
        self.window.import_progress = Mock()
        self.window._finish_import(ImportResult([('test.png', Image.new('RGBA', (800, 600), 'white'))], []))
        self.window._size_estimate_timer.stop()
        self.app.processEvents()

    def test_empty_regions_open_dialog_and_allow_retry_after_cancel(self):
        with patch('main.QFileDialog.getOpenFileNames', return_value=([], '')) as dialog:
            for widget in self.targets():
                for _ in range(2):
                    dialog.reset_mock()
                    self.double_click(widget)
                    dialog.assert_called_once()
                    self.assertEqual(self.window.photos, [])

    def test_single_click_and_right_double_click_do_not_import(self):
        with patch('main.QFileDialog.getOpenFileNames') as dialog:
            for widget in self.targets():
                QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=widget.rect().center())
                self.double_click(widget, Qt.MouseButton.RightButton)
            dialog.assert_not_called()

    def test_existing_photos_disable_import_but_keep_preview_toggle(self):
        self.import_one()
        with patch('main.QFileDialog.getOpenFileNames') as dialog:
            self.double_click(self.window.photo_list.viewport())
            self.assertFalse(self.window.canvas._result_preview)
            self.double_click(self.window.canvas)
            self.assertTrue(self.window.canvas._result_preview)
            self.double_click(self.window.canvas)
            self.assertFalse(self.window.canvas._result_preview)
            dialog.assert_not_called()

    def test_deleting_all_photos_reenables_both_regions(self):
        self.import_one()
        self.window._delete_photos({photo.id for photo in self.window.photos})
        with patch('main.QFileDialog.getOpenFileNames', return_value=([], '')) as dialog:
            for widget in self.targets():
                dialog.reset_mock()
                self.double_click(widget)
                dialog.assert_called_once()

    def test_loading_does_not_start_another_import(self):
        for attribute in ('import_worker', 'startup_worker'):
            with self.subTest(worker=attribute), patch.object(self.window, attribute, Mock(isRunning=Mock(return_value=True))):
                with patch('main.QFileDialog.getOpenFileNames') as dialog:
                    for widget in self.targets():
                        self.double_click(widget)
                    dialog.assert_not_called()
