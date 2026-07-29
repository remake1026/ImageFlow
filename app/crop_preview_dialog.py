"""当前尺寸的裁剪预览弹窗：双击可在编辑框和最终成图间切换。"""
from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

from .image_processor import crop_box, paste_watermark, pil_to_pixmap
from .models import CropSettings, SizeTemplate, WatermarkSettings


class PreviewImageLabel(QLabel):
    double_clicked = Signal()

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


def create_crop_icon() -> QIcon:
    """绘制不依赖外部图标文件的裁剪框图标。"""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setPen(QPen(QColor("#F59A23"), 2))
    # 两条裁剪角标，表现“裁剪”而不是简单的图片图标。
    painter.drawLine(4, 10, 4, 4)
    painter.drawLine(4, 4, 10, 4)
    painter.drawLine(20, 14, 20, 20)
    painter.drawLine(20, 20, 14, 20)
    painter.setPen(QPen(QColor("#F59A23"), 1))
    painter.drawLine(7, 7, 17, 17)
    painter.end()
    return QIcon(pixmap)


class CropPreviewDialog(QDialog):
    """预览仅使用缩略图；最终导出仍由原图执行同样的裁剪计算。"""

    def __init__(
        self,
        source: Image.Image,
        template: SizeTemplate,
        crop: CropSettings,
        watermark_path: str,
        watermark: WatermarkSettings,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("当前裁剪预览")
        self.resize(820, 700)
        self._source = source.convert("RGBA")
        self._template = template
        self._crop = crop
        self._watermark_path = watermark_path
        self._watermark = watermark
        self._show_final = False
        self._rendered = Image.new("RGBA", (1, 1))

        layout = QVBoxLayout(self)
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label = PreviewImageLabel()
        self.image_label.setObjectName("cropPreviewImage")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(360, 300)
        self.image_label.setToolTip("双击切换“裁剪框编辑预览”和“裁剪后图片预览”")
        self.image_label.double_clicked.connect(self.toggle_preview)
        layout.addWidget(self.info_label)
        layout.addWidget(self.image_label, 1)
        self._redraw()

    def _crop_image(self) -> Image.Image:
        aspect = self._source.width / self._source.height if self._template.id == "original" else self._template.aspect
        box = crop_box(self._source.size, aspect, self._crop)
        cropped = self._source.crop(box).copy()
        # 水印直接在裁剪后的画布上合成，锚点、边距与偏移均以成图为参考。
        return paste_watermark(cropped, self._watermark_path, self._watermark)

    def _build_editor_preview(self) -> Image.Image:
        aspect = self._source.width / self._source.height if self._template.id == "original" else self._template.aspect
        box = crop_box(self._source.size, aspect, self._crop)
        image = self._source.copy()
        dim_layer = Image.new("RGBA", image.size, (0, 0, 0, 125))
        image = Image.alpha_composite(image, dim_layer)
        cropped = self._crop_image()
        image.alpha_composite(cropped, (box[0], box[1]))
        drawing = ImageDraw.Draw(image)
        drawing.rectangle(box, outline=(245, 245, 245, 255), width=max(1, image.width // 800))
        # 三分法线只用于编辑状态，最终预览不会显示。
        for ratio in (1 / 3, 2 / 3):
            x = box[0] + (box[2] - box[0]) * ratio
            y = box[1] + (box[3] - box[1]) * ratio
            drawing.line((x, box[1], x, box[3]), fill=(255, 255, 255, 150), width=1)
            drawing.line((box[0], y, box[2], y), fill=(255, 255, 255, 150), width=1)
        return image

    def toggle_preview(self) -> None:
        self._show_final = not self._show_final
        self._redraw()

    def _redraw(self) -> None:
        self._rendered = self._crop_image() if self._show_final else self._build_editor_preview()
        self.info_label.setText(
            "裁剪后图片预览（双击返回编辑预览）" if self._show_final
            else "当前裁剪框预览（双击查看裁剪后的图片）"
        )
        self._update_pixmap()

    def _update_pixmap(self) -> None:
        pixmap = pil_to_pixmap(self._rendered)
        target = self.image_label.size()
        scaled = pixmap.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if self._rendered.size != (1, 1):
            self._update_pixmap()
