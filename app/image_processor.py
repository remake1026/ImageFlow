"""Pillow 图片读取、无损裁剪与水印合成。预览和导出共用同一套几何计算。"""
from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageOps
from PySide6.QtGui import QImage, QPixmap

from .models import CropSettings, SizeTemplate, WatermarkSettings


def open_oriented(path: str) -> Image.Image:
    """读取图片并应用 EXIF 方向；调用方负责关闭图片。"""
    source = Image.open(path)
    return ImageOps.exif_transpose(source)


def output_size(
    source_size: tuple[int, int],
    template: SizeTemplate,
    preserve_source_resolution: bool = False,
) -> tuple[int, int]:
    if template.id == "original" or template.width <= 0 or template.height <= 0:
        return source_size
    if preserve_source_resolution:
        width, height = source_size
        aspect = template.width / template.height
        crop_width = min(width, height * aspect)
        crop_height = crop_width / aspect
        return max(1, round(crop_width)), max(1, round(crop_height))
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
    preserve_source_resolution: bool = False,
) -> tuple[Image.Image, Optional[bytes], Optional[bytes]]:
    """返回最终图像和可选 ICC / EXIF 数据，始终由原图分辨率生成。"""
    with Image.open(source_path) as raw:
        icc = raw.info.get("icc_profile")
        exif = raw.getexif()
        # 必须先依据原始 EXIF 校正像素；getexif() 返回的对象与 raw 关联，
        # 若提前删除 Orientation，exif_transpose 将无法得知应旋转的方向。
        source = ImageOps.exif_transpose(raw).convert("RGBA")
        if exif:
            # 像素已由 exif_transpose 校正；不能再附带原图方向标签，
            # 否则部分查看器会按旧方向再旋转一次。
            exif.pop(0x0112, None)
            exif_bytes: Optional[bytes] = exif.tobytes()
        else:
            exif_bytes = None
    target_size = output_size(source.size, template, preserve_source_resolution)
    aspect = target_size[0] / target_size[1]
    result = source.crop(crop_box(source.size, aspect, crop))
    if result.size != target_size:
        result = result.resize(target_size, Image.Resampling.LANCZOS)
    result = paste_watermark(result, watermark_path, watermark)
    return result, icc, exif_bytes


def pil_to_pixmap(image: Image.Image) -> QPixmap:
    rgba = image.convert("RGBA")
    qimage = QImage(rgba.tobytes("raw", "RGBA"), rgba.width, rgba.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimage.copy())


def thumbnail_cache_root() -> Path:
    """返回只用于 ImageFlow 图片预览的本地缓存目录。"""
    local_root = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
    return local_root / "ImageFlow" / "thumbnail-cache"


def thumbnail_cache_info() -> tuple[int, int]:
    """返回缓存文件数量与总字节数；损坏或临时文件也计入可清理范围。"""
    root = thumbnail_cache_root()
    if not root.is_dir():
        return 0, 0
    files = [item for item in root.iterdir() if item.is_file()]
    total_bytes = 0
    for item in files:
        try:
            total_bytes += item.stat().st_size
        except OSError:
            continue
    return len(files), total_bytes


def clear_thumbnail_cache() -> tuple[int, int]:
    """仅删除 ImageFlow 预览缓存，返回成功删除的数量和字节数。"""
    root = thumbnail_cache_root()
    if not root.is_dir():
        return 0, 0
    removed_count = 0
    removed_bytes = 0
    for item in root.iterdir():
        if not item.is_file():
            continue
        try:
            size = item.stat().st_size
            item.unlink()
            removed_count += 1
            removed_bytes += size
        except OSError:
            continue
    try:
        root.rmdir()
    except OSError:
        pass
    return removed_count, removed_bytes


def _thumbnail_cache_path(path: str, max_edge: int) -> Path:
    """按源文件版本生成持久化预览缓存路径。"""
    source = Path(path)
    stat = source.stat()
    signature = (
        f"v2|{source.resolve(strict=False)}|{stat.st_size}|{stat.st_mtime_ns}|{max_edge}"
    ).encode("utf-8", errors="surrogatepass")
    return thumbnail_cache_root() / f"{hashlib.sha256(signature).hexdigest()}.webp"


def load_thumbnail(path: str, max_edge: int = 1600) -> Image.Image:
    """读取界面预览；后续启动优先复用磁盘缓存，不再重复解码大图。"""
    cache_path = _thumbnail_cache_path(path, max_edge)
    try:
        with Image.open(cache_path) as cached:
            return cached.convert("RGBA").copy()
    except (OSError, ValueError):
        pass

    # JPEG 可在解码阶段直接降采样，比先完整解码数千万像素再缩小明显更快。
    with Image.open(path) as image:
        if (image.format or "").upper() in {"JPEG", "MPO"}:
            image.draft("RGB", (max_edge, max_edge))
        oriented = ImageOps.exif_transpose(image)
        preview = oriented.convert("RGBA")
        preview.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        result = preview.copy()

    # 缓存失败不能影响正常导入。临时文件使用进程和线程编号，避免并行导入冲突。
    temp_path = cache_path.with_name(
        f"{cache_path.stem}.{os.getpid()}.{threading.get_ident()}.tmp.webp"
    )
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(temp_path, format="WEBP", quality=88, method=0)
        temp_path.replace(cache_path)
    except OSError:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
    return result
