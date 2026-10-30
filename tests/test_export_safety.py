import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.exporter import ExportJob, ExportWorker
from app.models import ExportSettings, PhotoItem, SizeTemplate


class ExportSafetyTests(unittest.TestCase):
    def test_overwrite_does_not_replace_source_or_another_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "photo.jpg"
            Image.new("RGB", (20, 20), "red").save(source)
            original = source.read_bytes()
            photo = PhotoItem(str(source))
            templates = [SizeTemplate("a", "1:1", 10, 10), SizeTemplate("b", "2:1", 20, 10)]
            settings = ExportSettings(output_folder=directory, image_format="JPG", brand="",
                                      start_sequence=None, subfolders=False, overwrite=True)
            worker = ExportWorker([ExportJob(photo, template, 1) for template in templates], "", settings)
            errors = []
            worker.failed.connect(errors.append)
            worker.run()
            self.assertEqual(errors, [])
            self.assertEqual(source.read_bytes(), original)
            self.assertTrue((Path(directory) / "photo_2.jpg").is_file())
            self.assertTrue((Path(directory) / "photo_3.jpg").is_file())


if __name__ == "__main__":
    unittest.main()
