"""Exercise viewport gestures through the real main-window event route."""
import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from app.qt.QtCore import QEvent, QPoint, QPointF, Qt
from app.qt.QtGui import QMouseEvent, QWheelEvent
from qt_test_support import QTest
from app.qt.QtWidgets import QApplication

from app.models import PhotoItem, SizeTemplate
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
        self.window._exit_requested = True
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
                # Qt5's QTest.mouseMove uses the OS cursor, which the offscreen
                # plugin does not deliver. Send a real Qt event on both bindings.
                moved = p + QPoint(40, 20)
                event = QMouseEvent(
                    QEvent.Type.MouseMove, QPointF(moved), QPointF(moved),
                    QPointF(self.canvas.mapToGlobal(moved)), Qt.MouseButton.NoButton,
                    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                )
                QApplication.sendEvent(self.canvas, event)
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

    def test_restore_initial_crop_for_each_size_in_both_modes(self):
        self.window.templates.append(SizeTemplate('custom', '自定义', 700, 300, builtin=False))
        for template in self.window.templates:
            template.selected = True
        for template in self.window.templates:
            for preview in (False, True):
                with self.subTest(template=template.id, preview=preview):
                    self.window.current_template_id = template.id
                    crop = self.window.current_photo().crop(template.id)
                    crop.zoom, crop.offset_x, crop.offset_y = 2.5, 0.4, -0.3
                    self.window._refresh_all()
                    self.canvas.set_result_preview(preview)
                    self.canvas._preview_zoom = 1.8
                    self.canvas._preview_offset = QPointF(20, 30)
                    self.window._sync_crop_controls()
                    self.assertTrue(self.window.restore_composition_preview_button.isEnabled())
                    self.window.restore_composition_preview_button.click()
                    self.window._size_estimate_timer.stop()
                    self.app.processEvents()
                    self.assertFalse(self.canvas.is_result_preview())
                    self.assertFalse(self.canvas.has_view_transform())
                    self.assertEqual((crop.zoom, crop.offset_x, crop.offset_y), (1, 0, 0))
                    frame, image = self.canvas._frame, self.canvas._image_rect
                    aspect = 800 / 600 if template.id == 'original' else template.aspect
                    expected_width = min(image.width(), image.height() * aspect)
                    self.assertAlmostEqual(frame.width(), expected_width)
                    self.assertAlmostEqual(frame.height(), expected_width / aspect)
                    self.assertAlmostEqual(frame.center().x(), image.center().x())
                    self.assertAlmostEqual(frame.center().y(), image.center().y())
                    self.assertEqual(self.window.current_template_id, template.id)

    def test_restore_is_scoped_and_undoable(self):
        photo = self.window.current_photo()
        photo.crop('4x5').zoom = 3
        photo.crop('1x1').offset_x = 0.4
        photo.crop('1x1').guide_enabled = True
        photo.watermark('1x1').enabled = True
        other = PhotoItem('other.png')
        other.crop('1x1').zoom = 4
        self.window.photos.append(other)
        self.window.thumbnail_cache[other.path] = self.window.thumbnail_cache[photo.path]
        self.window._refresh_photo_list()
        self.window._refresh_all()
        before = copy.deepcopy(self.window.photos)
        self.window.restore_composition_preview_button.click()
        self.assertEqual(photo.crop('4x5'), before[0].crop('4x5'))
        self.assertEqual(photo.watermark_by_template, before[0].watermark_by_template)
        self.assertTrue(photo.crop('1x1').guide_enabled)
        self.assertEqual(other, before[1])
        with patch('main.load_thumbnail', return_value=Image.new('RGBA', (800, 600), 'white')):
            self.window.undo_last_action()
        self.window._size_estimate_timer.stop()
        self.assertEqual(self.window.photos, before)

    def test_restore_without_photo_is_disabled(self):
        self.window.photos.clear()
        self.window.current_photo_index = -1
        self.window._refresh_all()
        self.assertFalse(self.window.restore_composition_preview_button.isEnabled())
        self.window._restore_default_composition_preview()
        self.assertEqual(self.window._undo_stack, [])

    def test_normal_wheel_edits_crop_only_in_edit_mode(self):
        self.wheel(Qt.KeyboardModifier.NoModifier)
        self.assertNotEqual(self.before, self.window.current_photo().to_dict())
        current = copy.deepcopy(self.window.current_photo().to_dict())
        self.canvas.set_result_preview(True)
        self.wheel(Qt.KeyboardModifier.NoModifier)
        self.assertEqual(current, self.window.current_photo().to_dict())


if __name__ == '__main__':
    unittest.main()
