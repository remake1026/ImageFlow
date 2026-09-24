"""后台导出线程，UI 保持可响应且可取消。"""
from __future__ import annotations

from io import BytesIO
import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .image_processor import render_image
from .models import CropSettings, ExportSettings, PhotoItem, SizeTemplate, WatermarkSettings


@dataclass
class ExportJob:
    photo: PhotoItem
    template: SizeTemplate
    sequence: int


def safe_filename(value: str) -> str:
    value = re.sub(r'[\\/:*?"<>|]+', "_", value).strip(" ._")
    return value or "未命名"


def build_filename(settings: ExportSettings, template: SizeTemplate, sequence: int, original_filename: str) -> str:
    """根据命名开关组合导出名，绝不修改原始照片文件。"""
    del template
    if settings.replace_original_name:
        # 覆盖原名称时始终输出三位流水号，确保批量导出不会同名。
        sequence_part = f"{sequence:03d}"
        parts = [settings.brand.strip(), settings.product.strip(), settings.color.strip(), settings.date.strip(), sequence_part]
    else:
        original_name = Path(original_filename).stem
        sequence_part = str(sequence) if settings.start_sequence is not None else ""
        parts = [settings.brand.strip(), settings.product.strip(), settings.color.strip(), settings.date.strip(), sequence_part, original_name]
    return safe_filename(" ".join(part for part in parts if part))


def save_encoded_image(
    image,
    destination,
    settings: ExportSettings,
    icc: bytes | None,
    exif: bytes | None,
) -> None:
    """按当前导出设置写入文件或内存流。"""
    save_args: dict = {}
    if settings.keep_icc and icc:
        save_args["icc_profile"] = icc
    if settings.keep_exif and exif and settings.image_format in ("JPG", "WEBP"):
        save_args["exif"] = exif
    if settings.image_format == "JPG":
        image.convert("RGB").save(destination, "JPEG", quality=settings.jpg_quality, optimize=True, **save_args)
    elif settings.image_format == "PNG":
        image.save(destination, "PNG", **save_args)
    else:
        image.save(destination, "WEBP", quality=settings.jpg_quality, **save_args)


def encoded_image_size(
    image,
    settings: ExportSettings,
    icc: bytes | None,
    exif: bytes | None,
) -> int:
    """按实际导出相同编码规则写入内存，返回输出字节数。"""
    stream = BytesIO()
    save_encoded_image(image, stream, settings, icc, exif)
    return stream.tell()


class OutputSizeEstimateWorker(QThread):
    """后台编码当前照片，避免质量滑杆拖动阻塞界面。"""

    estimated = Signal(int, int)
    failed = Signal(int)

    def __init__(
        self,
        request_id: int,
        photo_path: str,
        template: SizeTemplate,
        crop: CropSettings,
        watermark_path: str,
        watermark: WatermarkSettings,
        settings: ExportSettings,
    ) -> None:
        super().__init__()
        self.request_id = request_id
        self.photo_path = photo_path
        self.template = template
        self.crop = crop
        self.watermark_path = watermark_path
        self.watermark = watermark
        self.settings = settings

    def run(self) -> None:
        try:
            image, icc, exif = render_image(
                self.photo_path,
                self.template,
                self.crop,
                self.watermark_path,
                self.watermark,
                self.settings.preserve_source_resolution,
            )
            self.estimated.emit(self.request_id, encoded_image_size(image, self.settings, icc, exif))
        except Exception:
            self.failed.emit(self.request_id)


class ExportWorker(QThread):
    progress = Signal(int, int, str)
    failed = Signal(str)
    completed = Signal(str)
    cancelled = Signal()

    def __init__(self, jobs: list[ExportJob], watermark_path: str, settings: ExportSettings) -> None:
        super().__init__()
        self.jobs, self.watermark_path, self.settings = jobs, watermark_path, settings
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        output_root = Path(self.settings.output_folder)
        try:
            output_root.mkdir(parents=True, exist_ok=True)
            total = len(self.jobs)
            for index, job in enumerate(self.jobs, start=1):
                if self._cancelled:
                    self.cancelled.emit()
                    return
                folder = output_root / job.template.folder_name if self.settings.subfolders else output_root
                folder.mkdir(parents=True, exist_ok=True)
                extension = {"JPG": "jpg", "PNG": "png", "WEBP": "webp"}[self.settings.image_format]
                destination = folder / f"{build_filename(self.settings, job.template, job.sequence, job.photo.filename)}.{extension}"
                if destination.exists() and not self.settings.overwrite:
                    stem, suffix, counter = destination.stem, destination.suffix, 2
                    while destination.exists():
                        destination = folder / f"{stem}_{counter}{suffix}"
                        counter += 1
                image, icc, exif = render_image(
                    job.photo.path,
                    job.template,
                    job.photo.crop(job.template.id),
                    self.watermark_path,
                    job.photo.watermark(job.template.id),
                    self.settings.preserve_source_resolution,
                )
                save_encoded_image(image, destination, self.settings, icc, exif)
                self.progress.emit(index, total, destination.name)
            self.completed.emit(str(output_root))
        except Exception as error:  # 导出错误交给界面以友好方式展示
            self.failed.emit(str(error))
