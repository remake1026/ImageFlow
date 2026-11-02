import shutil
import tempfile
import unittest
from pathlib import Path

from installer.public_assets import RESOURCE_FILES, check_catalog, check_payload, release_datas


class PublicAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "products.csv").write_text("Product,Colors\n", encoding="utf-8")
        for name in RESOURCE_FILES:
            path = self.root / "resources" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"reviewed-resource")

    def test_catalog_with_customer_data_blocks_release(self):
        (self.root / "products.csv").write_text("Product,Colors\nPrivate SKU,Blue\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            release_datas(self.root)

    def test_extra_watermark_is_never_collected(self):
        private = self.root / "resources" / "customer-watermark.png"
        private.write_bytes(b"private-watermark")
        self.assertNotIn(str(private), [source for source, _ in release_datas(self.root)])

    def test_packaging_rejects_unreviewed_and_outdated_payload(self):
        payload = self.root / "dist"
        internal = payload / "_internal"
        shutil.copytree(self.root / "resources", internal / "resources")
        shutil.copy2(self.root / "products.csv", internal / "products.csv")
        check_payload(self.root, payload)
        extra = internal / "resources" / "customer-watermark.png"
        extra.write_bytes(b"private")
        with self.assertRaises(ValueError):
            check_payload(self.root, payload)
        extra.unlink()
        (internal / "resources" / RESOURCE_FILES[0]).write_bytes(b"outdated")
        with self.assertRaises(ValueError):
            check_payload(self.root, payload)


if __name__ == "__main__":
    unittest.main()
