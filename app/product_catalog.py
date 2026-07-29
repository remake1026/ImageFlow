"""Read SKU and color options from the bundled products.csv file."""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path


def products_csv_path() -> Path:
    """Prefer an editable CSV beside the app, then use the bundled copy."""
    app_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    external = app_dir / "products.csv"
    if external.exists():
        return external
    resource_dir = Path(getattr(sys, "_MEIPASS", app_dir))
    return resource_dir / "products.csv"


def _read_csv_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _clean(value: object) -> str:
    return str(value or "").strip().strip('"“”')


def _colors(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,，]", value) if item.strip()]


def load_product_catalog(path: Path | None = None) -> dict[str, list[str]]:
    """Return SKU -> colors, retaining the order from products.csv."""
    csv_path = path or products_csv_path()
    if not csv_path.exists():
        return {}

    catalog: dict[str, list[str]] = {}
    reader = csv.DictReader(_read_csv_text(csv_path).splitlines())
    for row in reader:
        normalized = {str(key).strip().lower(): _clean(value) for key, value in row.items() if key is not None}
        sku = normalized.get("sku") or normalized.get("product") or normalized.get("产品") or ""
        color_text = normalized.get("colors") or normalized.get("color") or normalized.get("颜色") or ""
        for color in _colors(color_text):
            if color not in catalog.setdefault(sku, []):
                catalog[sku].append(color)
        if sku and sku not in catalog:
            catalog[sku] = []
    return {sku: colors for sku, colors in catalog.items() if sku}
