import unittest
from unittest.mock import Mock, patch

from PIL import Image
from app.importer import ImportResult
from app.qt.QtCore import Qt
from app.qt.QtWidgets import QApplication
from main import MainWindow


class DefaultSizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch("main.load_presets", return_value={}):
            self.window = MainWindow()
        self.window.import_progress = Mock()

    def tearDown(self):
        self.window._exit_requested = True
        with patch.object(self.window, "_save_last_session"):
            self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def import_one(self, name):
        self.window._finish_import(ImportResult([(name, Image.new("RGBA", (10, 10)))], []))

    def selected(self):
        return [template.id for template in self.window.templates if template.selected]

    def test_first_successful_import_selects_original_only(self):
        self.assertEqual(self.selected(), [])
        self.import_one("first.png")
        self.assertEqual(self.selected(), ["original"])
        self.window.template_list.item(0).setCheckState(Qt.CheckState.Unchecked)
        self.import_one("second.png")
        self.assertEqual(self.selected(), [])

    def test_manual_selection_before_import_is_preserved(self):
        self.window.template_list.item(2).setCheckState(Qt.CheckState.Checked)
        self.import_one("first.png")
        self.assertEqual(self.selected(), ["4x5"])

    def test_restored_all_unchecked_is_preserved(self):
        self.window.presets["last_session"] = {
            "templates": [template.to_dict() for template in self.window.templates],
        }
        self.window._restore_last_session()
        self.import_one("first.png")
        self.assertEqual(self.selected(), [])
