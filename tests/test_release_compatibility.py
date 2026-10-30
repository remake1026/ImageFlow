"""Run the same desktop/export smoke tests with the x86 and x64 toolchains."""
import hashlib
import tempfile
from pathlib import Path
import unittest

from PIL import Image
from app.qt.QtCore import QTimer
from app.qt.QtWidgets import QApplication, QDialog
from app.exporter import save_encoded_image
from app.image_processor import pil_to_pixmap, render_image
from app.management_dialog import ManagementDialog
from app.models import CropSettings, ExportSettings, SizeTemplate, WatermarkSettings
from app.watermark_editor_dialog import WatermarkEditorDialog


class ReleaseCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_management_dialog_modal_event_loop(self):
        dialog = ManagementDialog({"Sample": ["Red", "Blue"]})
        QTimer.singleShot(0, dialog.accept)
        self.assertEqual(dialog.exec(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.sku_tree.topLevelItemCount(), 1)
        dialog.deleteLater()

    def test_watermark_editor_preview_and_modal_event_loop(self):
        dialog = WatermarkEditorDialog(
            Image.new("RGBA", (240, 160), "blue"),
            SizeTemplate("test", "1:1", 100, 100),
            CropSettings(), "", WatermarkSettings(),
        )
        dialog.show()
        self.app.processEvents()
        self.assertFalse(dialog.preview_label.pixmap().isNull())
        QTimer.singleShot(0, dialog.accept)
        self.assertEqual(dialog.exec(), QDialog.DialogCode.Accepted)
        dialog.deleteLater()

    def test_crop_watermark_export_and_preview_preserve_source(self):
        with tempfile.TemporaryDirectory() as folder:
            source, mark = Path(folder) / "原始照片.png", Path(folder) / "水印.png"
            Image.new("RGB", (240, 160), "blue").save(source)
            Image.new("RGBA", (30, 30), "red").save(mark)
            original = hashlib.sha256(source.read_bytes()).digest()
            result, icc, exif = render_image(
                str(source), SizeTemplate("test", "1:1", 100, 100), CropSettings(),
                str(mark), WatermarkSettings(enabled=True, anchor="中心", size_percent=30),
            )
            self.assertEqual(result.size, (100, 100))
            self.assertEqual(result.getpixel((50, 50))[:3], (255, 0, 0))
            self.assertFalse(pil_to_pixmap(result).isNull())
            for format in ("JPG", "PNG", "WEBP"):
                output = Path(folder) / f"导出.{format.lower()}"
                save_encoded_image(result, output, ExportSettings(image_format=format), icc, exif)
                with Image.open(output) as saved:
                    self.assertEqual(saved.size, (100, 100))
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), original)


if __name__ == "__main__":
    unittest.main()
