import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.data_paths import configured_data_directory
from app.presets import load_presets, save_presets
from app.product_catalog import load_product_catalog, save_product_catalog
from app.single_instance import SingleInstance
from app.qt.QtWidgets import QApplication


class DataPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_profile_keeps_presets_catalog_and_instance_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            roots = [Path(temp) / name for name in ("profile-one", "profile-two")]
            guards = []
            try:
                for index, root in enumerate(roots):
                    with patch.dict(os.environ, IMAGEFLOW_DATA_DIR=str(root)):
                        self.assertEqual(load_presets()["watermarks"], {})
                        save_presets({"profile": index})
                        save_product_catalog({f"Sample-{index}": ["Blue"]})
                        guard = SingleInstance()
                        guards.append(guard)
                        self.assertTrue(guard.start_or_activate())
                self.assertNotEqual(guards[0].name, guards[1].name)
                for index, root in enumerate(roots):
                    with patch.dict(os.environ, IMAGEFLOW_DATA_DIR=str(root)):
                        self.assertEqual(load_presets(), {"profile": index})
                        self.assertEqual(load_product_catalog(), {f"Sample-{index}": ["Blue"]})
            finally:
                for guard in guards:
                    guard.close()

    def test_relative_profile_path_is_rejected(self):
        with patch.dict(os.environ, IMAGEFLOW_DATA_DIR="relative-profile"):
            with self.assertRaises(RuntimeError):
                configured_data_directory()
