import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app.qt.QtWidgets import QApplication
from app.single_instance import SingleInstance


class SingleInstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_second_process_activates_primary_and_exit_releases_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            primary = SingleInstance(Path(folder))
            activations = []
            primary.activation_requested.connect(lambda: activations.append(True))
            try:
                self.assertTrue(primary.start_or_activate())
                child = subprocess.run([sys.executable, "-c",
                    "import sys; from pathlib import Path; from app.qt.QtCore import QCoreApplication; "
                    "from app.single_instance import SingleInstance; app=QCoreApplication([]); "
                    "guard=SingleInstance(Path(sys.argv[1])); print(guard.start_or_activate())",
                    folder], capture_output=True, text=True, timeout=10,
                    cwd=Path(__file__).resolve().parents[1])
                self.assertEqual(child.returncode, 0, child.stderr)
                self.assertEqual(child.stdout.strip(), "False")
                for _ in range(10):
                    self.app.processEvents()
                self.assertTrue(activations)
            finally:
                primary.close()
            replacement = SingleInstance(Path(folder))
            try:
                self.assertTrue(replacement.start_or_activate())
            finally:
                replacement.close()

    def test_recovers_after_previous_process_crashes(self):
        with tempfile.TemporaryDirectory() as folder:
            child = subprocess.run([sys.executable, "-c",
                "import os, sys; from pathlib import Path; from app.qt.QtCore import QCoreApplication; "
                "from app.single_instance import SingleInstance; app=QCoreApplication([]); "
                "guard=SingleInstance(Path(sys.argv[1])); assert guard.start_or_activate(); os._exit(0)",
                folder], capture_output=True, text=True, timeout=10,
                cwd=Path(__file__).resolve().parents[1])
            self.assertEqual(child.returncode, 0, child.stderr)
            replacement = SingleInstance(Path(folder))
            try:
                self.assertTrue(replacement.start_or_activate())
            finally:
                replacement.close()
