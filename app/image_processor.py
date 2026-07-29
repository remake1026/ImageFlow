"""Pillow 图片读取、无损裁剪与水印合成。预览和导出共用同一套几何计算。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageOps
from PySide6.QtGui import QImage, QPixmap

from .models import CropSettings, SizeTemplate, WatermarkSettings


def open_oriented(path: str) -> Image.Image:
    """读取图片并应用 EXIF 方向；调用方负责关闭图片。"""
    source = Image.open(path)
    return ImageOps.exif_transpose(source)


def output_size(source_size: tuple[int, int], template: SizeTemplate) -> tuple[int, int]:
    if template.id == "original" or template.width <= 0 or template.height <= 0:
        return source_size
    return template.width, template.height


def crop_box(source_size: tuple[int, int], aspect: float, crop: CropSettings) -> tuple[int, int, int, int]:
    """按实际原图坐标生成裁剪框。缩放永远不会露出空白。"""
    width, height = source_size
    base_width = min(width, height * aspect)
    base_height = base_width / aspect
    zoom = max(1.0, min(crop.zoom, 12.0))
    crop_width = max(1.0, base_width / zoom)
    crop_height = max(1.0, base_height / zoom)
    free_x, free_y = width - crop_width, height - crop_height
    center_x = width / 2 + max(-1.0, min(1.0, crop.offset_x)) * free_x / 2
    center_y = height / 2 + max(-1.0, min(1.0, crop.offset_y)) * free_y / 2
    left = max(0.0, min(width - crop_width, center_x - crop_width / 2))
    top = max(0.0, min(height - crop_height, center_y - crop_height / 2))
    return (round(left), round(top), round(left + crop_width), round(top + crop_height))


def watermark_rect(canvas_size: tuple[int, int], mark_size: tuple[int, int], settings: WatermarkSettings) -> tuple[float, float]:
    """计算未旋转水印左上角。偏移和边距均以输出尺寸百分比表示。"""
    width, height = canvas_size
    mark_w, mark_h = mark_size
    margin_x, margin_y = width * settings.margin_percent / 100, height * settings.margin_percent / 100
    dx, dy = width * settings.offset_x / 100, height * settings.offset_y / 100
    horizontal = "左" if "左" in settings.anchor else "右" if "右" in settings.anchor else "中"
    vertical = "上" if "上" in settings.anchor else "下" if "下" in settings.anchor else "中"
    x = margin_x if horizontal == "左" else width - margin_x - mark_w if horizontal == "右" else (width - mark_w) / 2
    y = margin_y if vertical == "上" else height - margin_y - mark_h if vertical == "下" else (height - mark_h) / 2
    return x + dx, y + dy


def paste_watermark(canvas: Image.Image, watermark_path: str, settings: WatermarkSettings) -> Image.Image:
    if not settings.enabled or not watermark_path or not Path(watermark_path).is_file():
        return canvas
    with Image.open(watermark_path) as original_mark:
        mark = original_mark.convert("RGBA")
    target_width = max(1, round(canvas.width * settings.size_percent / 100))
    target_height = max(1, round(mark.height * target_width / mark.width))
    mark.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
    # thumbnail 保持比例，若图片比目标窄时仍需达到目标宽度。
    if mark.width != target_width:
        mark = mark.resize((target_width, target_height), Image.Resampling.LANCZOS)
    if settings.opacity < 100:
        alpha = mark.getchannel("A").point(lambda v: v * settings.opacity // 100)
        mark.putalpha(alpha)
    x, y = watermark_rect(canvas.size, mark.size, settings)
    if settings.rotation:
        rotated = mark.rotate(-settings.rotation, expand=True, resample=Image.Resampling.BICUBIC)
        x -= (rotated.width - mark.width) / 2
        y -= (rotated.height - mark.height) / 2
        mark = rotated
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.alpha_composite(mark, (round(x), round(y)))
    return Image.alpha_composite(canvas.convert("RGBA"), layer)


def render_image(
    source_path: str,
    template: SizeTemplate,
    crop: CropSettings,
    watermark_path: str,
    watermark: WatermarkSettings,
) -> tuple[Image.Image, Optional[bytes], Optional[bytes]]:
    """返回最终图像和可选 ICC / EXIF 数据，始终由原图分辨率生成。"""
    with Image.open(source_path) as raw:
        icc = raw.info.get("icc_profile")
        exif = raw.getexif()
        if exif:
            exif[0x0112] = 1  # 保存时不再产生错误旋转
            exif_bytes: Optional[bytes] = exif.tobytes()
        else:
            exif_bytes = None
        source = ImageOps.exif_transpose(raw).convert("RGBA")
    target_size = output_size(source.size, template)
    aspect = target_size[0] / target_size[1]
    result = source.crop(crop_box(source.size, aspect, crop)).resize(target_size, Image.Resampling.LANCZOS)
    result = paste_watermark(result, watermark_path, watermark)
    return result, icc, exif_bytes


def pil_to_pixmap(image: Image.Image) -> QPixmap:
    rgba = image.convert("RGBA")
    qimage = QImage(rgba.tobytes("raw", "RGBA"), rgba.width, rgba.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimage.copy())


def load_thumbnail(path: str, max_edge: int = 2048) -> Image.Image:
    with open_oriented(path) as image:
        preview = image.convert("RGBA")
        preview.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        return preview.copy()
