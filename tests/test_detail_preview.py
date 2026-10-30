"""High-resolution decoding, memory bounds and asynchronous canvas integration."""
import copy
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from app.qt.QtCore import QPointF, Qt
from app.qt.QtGui import QImage
from qt_test_support import QTest
from app.qt.QtWidgets import QApplication, QWidget

from app.crop_canvas import CropCanvas
from app.detail_preview import DetailPreviewLoader, load_detail_image
from app.models import CropSettings, SizeTemplate, WatermarkSettings


class DetailPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.owner = QWidget()
        self.loader = DetailPreviewLoader(self.owner, max_pixels=200_000)

    def tearDown(self):
        self.loader.shutdown()
        self.owner.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def wait_for(self, predicate, timeout=3000):
        for _ in range(timeout // 10):
            self.app.processEvents()
            if predicate():
                return
            QTest.qWait(10)
        self.fail('Background preview did not complete')

    def make_image(self, name, color, size=(1000, 600)):
        path = self.root / name
        Image.new('RGB', size, color).save(path)
        return str(path)

    def test_decoder_caps_pixels_and_preserves_exif_orientation(self):
        path = self.root / 'oriented.jpg'
        source = Image.new('RGB', (600, 400), 'red')
        exif = source.getexif()
        exif[274] = 6
        source.save(path, exif=exif)
        image = load_detail_image(str(path))
        self.assertEqual((image.width(), image.height()), (400, 600))
        bounded = load_detail_image(str(path), 60_000)
        self.assertLessEqual(bounded.sizeInBytes(), 60_000 * 4)
        self.assertAlmostEqual(bounded.width() / bounded.height(), 2 / 3, places=2)

    def test_supported_photo_formats_and_alpha(self):
        for suffix in ('jpg', 'png', 'webp', 'tiff', 'bmp'):
            with self.subTest(suffix=suffix):
                path = self.make_image('source.' + suffix, 'red', (100, 80))
                image = load_detail_image(path)
                self.assertEqual((image.width(), image.height()), (100, 80))
                self.assertGreater(image.pixelColor(10, 10).red(), 240)
        path = self.root / 'transparent.png'
        Image.new('RGBA', (50, 50), (255, 0, 0, 64)).save(path)
        self.assertEqual(load_detail_image(str(path)).pixelColor(0, 0).alpha(), 64)

    def test_cache_reuse_and_source_replacement(self):
        path = self.make_image('source.png', 'red')
        self.loader.set_source(path)
        self.loader.request()
        self.wait_for(lambda: not self.loader.image.isNull())
        first = self.loader.image.cacheKey()
        self.loader.request()
        self.assertEqual(first, self.loader.image.cacheKey())
        self.assertIsNone(self.loader._worker)
        self.make_image('source.png', 'blue', (900, 500))
        self.loader.request()
        self.assertTrue(self.loader.image.isNull())
        self.wait_for(lambda: not self.loader.image.isNull())
        self.assertEqual(self.loader.image.pixelColor(0, 0).blue(), 255)
        self.assertLessEqual(self.loader.image.sizeInBytes(), 200_000 * 4)

    def test_rapid_switch_discards_old_result_and_decodes_serially(self):
        paths = [self.make_image(f'{i}.png', color) for i, color in enumerate(('red', 'green', 'blue'))]
        started, release = threading.Event(), threading.Event()
        calls = []
        def decode(path, max_pixels):
            calls.append(path)
            if len(calls) == 1:
                started.set()
                release.wait(2)
            return load_detail_image(path, max_pixels)
        with patch('app.detail_preview.load_detail_image', side_effect=decode):
            self.loader.set_source(paths[0]); self.loader.request()
            self.wait_for(started.is_set)
            self.loader.set_source(paths[1]); self.loader.request()
            self.loader.set_source(paths[2]); self.loader.request()
            self.assertTrue(self.loader.image.isNull())
            release.set()
            self.wait_for(lambda: not self.loader.image.isNull())
        self.assertEqual(calls, [paths[0], paths[2]])
        self.assertEqual(self.loader.image.pixelColor(0, 0).blue(), 255)

    def test_decode_failure_keeps_preview_available(self):
        path = self.root / 'broken.png'; path.write_bytes(b'not an image')
        errors = []
        self.loader.failed.connect(errors.append)
        self.loader.set_source(str(path)); self.loader.request()
        self.wait_for(lambda: bool(errors))
        self.assertTrue(self.loader.image.isNull())
        self.loader.request()
        self.assertIsNone(self.loader._worker)

    def test_zoom_restores_real_detail_without_changing_composition(self):
        source = Image.new('RGB', (6400, 400), 'white')
        draw = ImageDraw.Draw(source)
        for x in range(0, 6400, 2):
            draw.line((x, 0, x, 399), fill='black')
        path = self.root / 'fine-lines.png'; source.save(path)
        thumb = source.copy(); thumb.thumbnail((1600, 1600))
        canvas = CropCanvas(); canvas.resize(400, 240)
        crop = CropSettings(guide_enabled=False); before = copy.deepcopy(crop)
        canvas.set_content(thumb, SizeTemplate('original', 'Original', 0, 0), crop,
                           '', WatermarkSettings(), ('photo', 'original'), str(path))
        canvas.show(); self.app.processEvents()
        try:
            QTest.qWait(220)
            self.assertTrue(canvas._detail_loader.image.isNull(), 'Fit view should not decode a full image')
            canvas._preview_zoom = 16
            canvas._schedule_detail_refresh()
            low = canvas.grab().toImage()
            self.wait_for(lambda: not canvas._detail_loader.image.isNull())
            high = canvas.grab().toImage()
            def contrast(image):
                values = [image.pixelColor(x, image.height() // 2).red() for x in range(image.width() // 3, image.width() * 2 // 3)]
                return max(values) - min(values)
            self.assertGreater(contrast(high), contrast(low) + 100)
            self.assertEqual(crop, before)
            self.assertEqual(canvas._preview_zoom, 16)
            self.assertEqual(canvas._preview_offset, QPointF())
            # A crop result can need source detail even at view zoom=1.
            canvas.set_content(thumb, SizeTemplate('square', '1:1', 1, 1), crop,
                               '', WatermarkSettings(), ('photo', 'square'), str(path))
            canvas.set_result_preview(True)
            self.assertFalse(canvas._detail_loader.image.isNull(), 'Reuse current source when only the crop template changes')
            canvas._detail_loader.set_source('')
            canvas._detail_loader.set_source(str(path))
            self.wait_for(lambda: not canvas._detail_loader.image.isNull())
            self.assertEqual(canvas._preview_zoom, 1, 'Crop result should request detail at fit-to-window scale')
        finally:
            canvas.shutdown(); canvas.close(); canvas.deleteLater()


if __name__ == '__main__':
    unittest.main()
