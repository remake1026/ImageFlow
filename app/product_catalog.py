"""Read product and color options from the bundled products.csv file."""
from __future__ import annotations

import csv
import os
import re
import sys
import tempfile
from pathlib import Path


def user_products_csv_path() -> Path:
    """产品数据写入用户目录，避免安装目录没有写权限。"""
    local_root = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
    return local_root / "ImageFlow" / "products.csv"


def products_csv_path() -> Path:
    """优先读取后台保存的用户数据，再回退到软件自带目录。"""
    user_catalog = user_products_csv_path()
    if user_catalog.exists():
        return user_catalog
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


def parse_colors(value: str) -> list[str]:
    """兼容英文/中文逗号、顿号和历史 CSV 中的替换分隔符。"""
    return [item.strip() for item in re.split(r"[,，、;；�]+", value) if item.strip()]


def load_product_catalog(path: Path | None = None) -> dict[str, list[str]]:
    """Return product-to-colors mappings in products.csv order."""
    csv_path = path or products_csv_path()
    if not csv_path.exists():
        return {}

    catalog: dict[str, list[str]] = {}
    reader = csv.DictReader(_read_csv_text(csv_path).splitlines())
    for row in reader:
        normalized = {str(key).strip().lower(): _clean(value) for key, value in row.items() if key is not None}
        product = normalized.get("product") or normalized.get("产品") or ""
        color_text = normalized.get("colors") or normalized.get("color") or normalized.get("颜色") or ""
        for color in parse_colors(color_text):
            if color not in catalog.setdefault(product, []):
                catalog[product].append(color)
        if product and product not in catalog:
            catalog[product] = []
    return {product: colors for product, colors in catalog.items() if product}


def save_product_catalog(catalog: dict[str, list[str]], path: Path | None = None) -> Path:
    """原子保存产品数据；默认写入当前用户的可写配置目录。"""
    destination = path or user_products_csv_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Product", "Colors"])
            for product, colors in catalog.items():
                clean_product = _clean(product)
                if clean_product:
                    writer.writerow([clean_product, ", ".join(_clean(color) for color in colors if _clean(color))])
        temporary.replace(destination)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return destination
