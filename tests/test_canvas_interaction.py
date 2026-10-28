"""Exercise viewport gestures through the real main-window event route."""
import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.models import PhotoItem
from main import MainWindow, _load_stylesheet


class CanvasInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        cls.app.setStyleSheet(_load_stylesheet())

    def setUp(self):
        with patch('main.load_presets', return_value={}):
            self.window = MainWindow()
        self.window.photos = [PhotoItem('test-image.png')]
        self.window.current_photo_index = 0
        image = Image.new('RGBA', (800, 600), 'white')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 399, 299), fill='red')
        draw.rectangle((400, 300, 799, 599), fill='blue')
        self.window.thumbnail_cache['test-image.png'] = image
        self.window.current_template_id = '1x1'
        self.window.current_photo().crop('1x1').zoom = 2.0
        self.window._refresh_all()
        self.window._size_estimate_timer.stop()
        self.window.show()
        self.window.activateWindow()
        self.canvas = self.window.canvas
        self.canvas.setFocus()
        self.app.processEvents()
        self.before = copy.deepcopy(self.window.current_photo().to_dict())

    def tearDown(self):
        # Test fixtures must not overwrite the user's saved session.
        with patch.object(self.window, '_save_last_session'):
            self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def wheel(self, modifiers, delta=120, horizontal=False, pixel_delta=None):
        point = self.canvas.rect().center()
        event = QWheelEvent(
            QPointF(self.canvas.mapTo(self.window, point)),
            QPointF(self.canvas.mapToGlobal(point)),
            pixel_delta or QPoint(), QPoint(delta, 0) if horizontal else QPoint(0, delta), Qt.MouseButton.NoButton,
            modifiers, Qt.ScrollPhase.NoScrollPhase, False,
        )
        # Unlike a direct canvas.wheelEvent call, this passes through Qt's
        # window-to-widget hit testing and application event filters.
        self.app.sendEvent(self.window.windowHandle(), event)
        self.app.processEvents()

    def test_alt_wheel_changes_rendering_in_both_modes(self):
        for preview in (False, True):
            with self.subTest(preview=preview):
                self.canvas.set_result_preview(preview)
                self.app.processEvents()
                before = self.canvas.grab().toImage()
                self.wheel(Qt.KeyboardModifier.AltModifier)
                self.assertNotEqual(before, self.canvas.grab().toImage())
                self.assertGreater(self.canvas._preview_zoom, 1)
                self.assertEqual(self.before, self.window.current_photo().to_dict())
                self.wheel(Qt.KeyboardModifier.AltModifier, -120)
                self.assertAlmostEqual(self.canvas._preview_zoom, 1)

    def test_alt_horizontal_wheel_from_windows_mouse(self):
        # Captured from the user's real Alt+wheel input: angleDelta=(120, 0).
        for preview in (False, True):
            with self.subTest(preview=preview):
                self.canvas.set_result_preview(preview)
                self.app.processEvents()
                before = self.canvas.grab().toImage()
                self.wheel(Qt.KeyboardModifier.AltModifier, horizontal=True)
                self.assertGreater(self.canvas._preview_zoom, 1)
                self.assertNotEqual(before, self.canvas.grab().toImage())
                self.wheel(Qt.KeyboardModifier.AltModifier, -120, horizontal=True)
                self.assertAlmostEqual(self.canvas._preview_zoom, 1)
                self.assertEqual(self.before, self.window.current_photo().to_dict())

    def test_alt_pixel_wheel(self):
        for delta in (QPoint(0, 40), QPoint(40, 0)):
            with self.subTest(delta=delta):
                self.canvas.reset_preview_view()
                self.wheel(Qt.KeyboardModifier.AltModifier, 0, pixel_delta=delta)
                self.assertGreater(self.canvas._preview_zoom, 1)
                self.assertEqual(self.before, self.window.current_photo().to_dict())

    def test_space_drag_does_not_edit_crop(self):
        for preview in (False, True):
            with self.subTest(preview=preview):
                self.canvas.set_result_preview(preview)
                p = self.canvas.rect().center()
                QTest.keyPress(self.canvas, Qt.Key.Key_Space)
                QTest.mousePress(self.canvas, Qt.MouseButton.LeftButton, pos=p)
                QTest.mouseMove(self.canvas, p + QPoint(40, 20))
                QTest.mouseRelease(self.canvas, Qt.MouseButton.LeftButton, pos=p + QPoint(40, 20))
                QTest.keyRelease(self.canvas, Qt.Key.Key_Space)
                self.assertEqual(self.canvas._preview_offset, QPointF(40, 20))
                self.assertEqual(self.before, self.window.current_photo().to_dict())

    def test_main_window_passes_source_for_detail_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'full.png')
            source = Image.new('RGB', (3200, 2000), 'blue')
            source.save(path)
            thumb = source.copy(); thumb.thumbnail((1600, 1600))
            self.window.current_photo().path = path
            self.window.thumbnail_cache[path] = thumb
            self.window._refresh_canvas()
            self.window._size_estimate_timer.stop()
            self.window._show_crop_result_preview()
            for _ in range(500):
                QTest.qWait(10)
                if not self.canvas._detail_loader.image.isNull():
                    break
            detail = self.canvas._detail_loader.image
            self.assertEqual((detail.width(), detail.height()), (3200, 2000))
            self.assertEqual(self.window.thumbnail_cache[path].size, (1600, 1000))
            self.assertEqual(self.window.current_photo().crop('1x1').zoom, 2)

    def test_fit_view_preserves_crop(self):
        self.wheel(Qt.KeyboardModifier.AltModifier)
        self.window.fit_button.click()
        self.assertFalse(self.canvas.has_view_transform())
        self.assertEqual(self.before, self.window.current_photo().to_dict())

    def test_normal_wheel_edits_crop_only_in_edit_mode(self):
        self.wheel(Qt.KeyboardModifier.NoModifier)
        self.assertNotEqual(self.before, self.window.current_photo().to_dict())
        current = copy.deepcopy(self.window.current_photo().to_dict())
        self.canvas.set_result_preview(True)
        self.wheel(Qt.KeyboardModifier.NoModifier)
        self.assertEqual(current, self.window.current_photo().to_dict())


if __name__ == '__main__':
    unittest.main()
