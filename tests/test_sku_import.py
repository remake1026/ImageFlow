import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.management_dialog import ManagementDialog
from app.product_catalog import import_product_catalog
from app.qt.QtWidgets import QApplication


class SkuImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_import_merges_existing_skus_and_emits_updated_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "products.csv"
            path.write_text('Product,Colors\nproduct-a,"White, Blue"\nNew,Black\n', encoding="utf-8-sig")
            dialog = ManagementDialog({"Product-A": ["White", "Red"]})
            changes = []
            dialog.catalog_changed.connect(changes.append)
            with patch("app.management_dialog.QFileDialog.getOpenFileName", return_value=(str(path), "")), \
                 patch("app.management_dialog.save_product_catalog") as save, \
                 patch("app.management_dialog.QMessageBox.information"):
                dialog._import_skus()
            expected = {"Product-A": ["White", "Red", "Blue"], "New": ["Black"]}
            self.assertEqual(dialog.catalog, expected)
            self.assertEqual(changes, [expected])
            self.assertEqual(dialog.sku_tree.topLevelItemCount(), 2)
            save.assert_called_once()
            dialog.deleteLater()

    def test_rejects_csv_without_product_column(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("name,color\nexample,red\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                import_product_catalog(path)


if __name__ == "__main__":
    unittest.main()
