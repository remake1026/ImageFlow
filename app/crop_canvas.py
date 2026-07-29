"""中间区域的固定裁剪框交互控件。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QLineF, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import QWidget

from .image_processor import pil_to_pixmap, watermark_rect
from .models import CropSettings, SizeTemplate, WatermarkSettings


class CropCanvas(QWidget):
    crop_changed = Signal()
    watermark_changed = Signal()
    restore_requested = Signal()
    edit_started = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self._pixmap = QPixmap()
        self._watermark_pixmap = QPixmap()
        self._template: Optional[SizeTemplate] = None
        self._crop: Optional[CropSettings] = None
        self._watermark: Optional[WatermarkSettings] = None
        self._drag_mode = ""
        self._last_pos = QPoint()
        self._frame = QRectF()
        self._image_rect = QRectF()
        self._watermark_rect = QRectF()
        self._resize_corner = ""
        self._result_preview = False

    def set_content(
        self,
        image,
        template: SizeTemplate,
        crop: CropSettings,
        watermark_path: str,
        watermark: WatermarkSettings,
    ) -> None:
        self._pixmap = pil_to_pixmap(image)
        self._template, self._crop, self._watermark = template, crop, watermark
        self._watermark_pixmap = QPixmap(watermark_path) if watermark_path and Path(watermark_path).is_file() else QPixmap()
        self.update()

    def set_result_preview(self, enabled: bool) -> None:
        """切换裁剪结果的纯显示模式，不改动任何裁剪参数。"""
        self._result_preview = enabled
        self._drag_mode = ""
        self._resize_corner = ""
        self.setCursor(Qt.CursorShape.ArrowCursor if enabled else Qt.CursorShape.OpenHandCursor)
        self.update()

    def is_result_preview(self) -> bool:
        return self._result_preview

    def _aspect(self) -> float:
        if not self._template or not self._pixmap.height():
            return 1.0
        return self._pixmap.width() / self._pixmap.height() if self._template.id == "original" else self._template.aspect

    def _layout(self) -> None:
        if self._pixmap.isNull() or not self._crop:
            self._frame = QRectF()
            return
        # 黑色画布是固定视口。原图始终按 contain 比例居中、固定显示；
        # 用户操作的是叠在原图上的裁剪框，而不是移动原图本身。
        # 编辑预览直接贴合画布，不保留额外安全间隔。
        available = QRectF(self.rect())
        aspect = self._aspect()
        if available.width() <= 0 or available.height() <= 0:
            self._frame = QRectF()
            return
        image_w, image_h = self._pixmap.width(), self._pixmap.height()
        fit_scale = min(available.width() / image_w, available.height() / image_h)
        self._image_rect = QRectF(
            available.center().x() - image_w * fit_scale / 2,
            available.center().y() - image_h * fit_scale / 2,
            image_w * fit_scale,
            image_h * fit_scale,
        )
        # zoom=1 时裁剪框是当前比例在原图内可取得的最大区域；缩放后缩小
        # 裁剪框本身。由于框始终由原图坐标计算，内部不会露出黑色背景。
        base_w = min(image_w, image_h * aspect)
        base_h = base_w / aspect
        crop_w, crop_h = base_w / self._crop.zoom, base_h / self._crop.zoom
        free_x, free_y = image_w - crop_w, image_h - crop_h
        center_x = image_w / 2 + self._crop.offset_x * free_x / 2
        center_y = image_h / 2 + self._crop.offset_y * free_y / 2
        self._frame = QRectF(
            self._image_rect.left() + (center_x - crop_w / 2) * fit_scale,
            self._image_rect.top() + (center_y - crop_h / 2) * fit_scale,
            crop_w * fit_scale,
            crop_h * fit_scale,
        )
        self._watermark_rect = QRectF()
        if self._watermark and self._watermark.enabled and not self._watermark_pixmap.isNull():
            size_w = self._frame.width() * self._watermark.size_percent / 100
            size_h = size_w * self._watermark_pixmap.height() / self._watermark_pixmap.width()
            x, y = watermark_rect((self._frame.width(), self._frame.height()), (size_w, size_h), self._watermark)
            self._watermark_rect = QRectF(self._frame.x() + x, self._frame.y() + y, size_w, size_h)

    def _draw_watermark(self, painter: QPainter, rect: QRectF, clip_rect: QRectF) -> None:
        if rect.isNull() or not self._watermark:
            return
        painter.save()
        painter.setClipRect(clip_rect)
        center = rect.center()
        painter.translate(center)
        painter.rotate(-self._watermark.rotation)
        painter.translate(-center)
        painter.setOpacity(self._watermark.opacity / 100)
        painter.drawPixmap(rect, self._watermark_pixmap, QRectF(self._watermark_pixmap.rect()))
        painter.restore()

    def _paint_result_preview(self, painter: QPainter) -> None:
        """使用当前预览缓存的裁剪区域等比绘制最终画面。"""
        if self._frame.isNull() or self._image_rect.width() <= 0:
            return
        source_scale = self._image_rect.width() / self._pixmap.width()
        source_rect = QRectF(
            (self._frame.left() - self._image_rect.left()) / source_scale,
            (self._frame.top() - self._image_rect.top()) / source_scale,
            self._frame.width() / source_scale,
            self._frame.height() / source_scale,
        ).intersected(QRectF(self._pixmap.rect()))
        if source_rect.isEmpty():
            return
        # 裁剪结果预览同样直接贴合画布，不保留额外安全间隔。
        available = QRectF(self.rect())
        preview_scale = min(available.width() / source_rect.width(), available.height() / source_rect.height())
        target_rect = QRectF(
            available.center().x() - source_rect.width() * preview_scale / 2,
            available.center().y() - source_rect.height() * preview_scale / 2,
            source_rect.width() * preview_scale,
            source_rect.height() * preview_scale,
        )
        painter.drawPixmap(target_rect, self._pixmap, source_rect)
        if not self._watermark_rect.isNull():
            watermark_rect = QRectF(
                target_rect.left() + (self._watermark_rect.left() - self._frame.left()) * target_rect.width() / self._frame.width(),
                target_rect.top() + (self._watermark_rect.top() - self._frame.top()) * target_rect.height() / self._frame.height(),
                self._watermark_rect.width() * target_rect.width() / self._frame.width(),
                self._watermark_rect.height() * target_rect.height() / self._frame.height(),
            )
            self._draw_watermark(painter, watermark_rect, target_rect)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """窗口变化时重算 contain 比例，但不修改已保存的构图参数。"""
        super().resizeEvent(event)
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(74, 74, 74))
        self._layout()
        if self._pixmap.isNull():
            painter.setPen(QColor("#c6cbd4"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "导入照片后在此调整裁剪构图")
            return
        if self._result_preview:
            self._paint_result_preview(painter)
            return
        # 先完整显示图片；裁剪框之外会在下方叠加半透明遮罩。
        # 这样既能明确看到最终交付范围，也能看到被裁掉的画面。
        painter.drawPixmap(self._image_rect, self._pixmap, QRectF(self._pixmap.rect()))
        if not self._watermark_rect.isNull():
            self._draw_watermark(painter, self._watermark_rect, self._frame)
        if self._crop and self._crop.guide_enabled:
            painter.setPen(QPen(QColor(255, 255, 255, 110), 1, Qt.PenStyle.DashLine))
            for ratio in (1 / 3, 2 / 3):
                painter.drawLine(QLineF(self._frame.left() + self._frame.width() * ratio, self._frame.top(), self._frame.left() + self._frame.width() * ratio, self._frame.bottom()))
                painter.drawLine(QLineF(self._frame.left(), self._frame.top() + self._frame.height() * ratio, self._frame.right(), self._frame.top() + self._frame.height() * ratio))
        if self._watermark and self._watermark.safe_area:
            margin = self._frame.width() * self._watermark.margin_percent / 100
            painter.setPen(QPen(QColor("#F59A23"), 1, Qt.PenStyle.DashLine))
            painter.drawRect(self._frame.adjusted(margin, margin, -margin, -margin))
        # 裁剪外遮罩
        shade = QColor(0, 0, 0, 128)
        painter.fillRect(QRectF(0, 0, self.width(), self._frame.top()), shade)
        painter.fillRect(QRectF(0, self._frame.bottom(), self.width(), self.height() - self._frame.bottom()), shade)
        painter.fillRect(QRectF(0, self._frame.top(), self._frame.left(), self._frame.height()), shade)
        painter.fillRect(QRectF(self._frame.right(), self._frame.top(), self.width() - self._frame.right(), self._frame.height()), shade)
        painter.setPen(QPen(QColor(235, 235, 235, 220), 1))
        painter.drawRect(self._frame)
        # 四角的小延长线让裁剪边界更接近专业修图软件的视觉表现。
        painter.setPen(QPen(QColor(255, 255, 255, 230), 2))
        handle = 11
        for x, y, sx, sy in (
            (self._frame.left(), self._frame.top(), 1, 1),
            (self._frame.right(), self._frame.top(), -1, 1),
            (self._frame.left(), self._frame.bottom(), 1, -1),
            (self._frame.right(), self._frame.bottom(), -1, -1),
        ):
            painter.drawLine(QLineF(x, y, x + sx * handle, y))
            painter.drawLine(QLineF(x, y, x, y + sy * handle))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._result_preview or event.button() != Qt.MouseButton.LeftButton or not self._crop:
            return
        self.setFocus()
        self._layout()
        self._last_pos = event.position().toPoint()
        corner = self._corner_at(event.position())
        if corner:
            self.edit_started.emit()
            self._drag_mode = "resize"
            self._resize_corner = corner
            self.setCursor(self._cursor_for_corner(corner))
        # 主预览中的水印只用于显示最终效果；水印位置只能在编辑器中调整。
        elif self._frame.contains(event.position()):
            self.edit_started.emit()
            self._drag_mode = "crop"
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._result_preview or not self._crop:
            return
        if not self._drag_mode:
            self._layout()
            corner = self._corner_at(event.position())
            if corner:
                self.setCursor(self._cursor_for_corner(corner))
            else:
                self.setCursor(Qt.CursorShape.OpenHandCursor if self._frame.contains(event.position()) else Qt.CursorShape.ArrowCursor)
            return
        delta = event.position().toPoint() - self._last_pos
        self._last_pos = event.position().toPoint()
        if self._drag_mode == "resize":
            from_center = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self._resize_frame_from_corner(event.position(), from_center)
            self.crop_changed.emit()
        else:
            self._move_frame_by_screen_pixels(delta.x(), delta.y())
            self.crop_changed.emit()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._result_preview:
            self._drag_mode = ""
            self._resize_corner = ""
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        self._drag_mode = ""
        self._resize_corner = ""
        self._layout()
        self.setCursor(Qt.CursorShape.OpenHandCursor if self._frame.contains(event.position()) else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not self._drag_mode:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if not self._result_preview and self._frame.contains(event.position()):
            self.restore_requested.emit()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._result_preview or not self._crop or not self._frame.contains(event.position()):
            return
        # 鼠标所在位置是缩放锚点：缩放的是裁剪框，原图不移动。
        self._layout()
        old_zoom = self._crop.zoom
        factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        new_zoom = max(1.0, min(12.0, old_zoom * factor))
        if new_zoom == old_zoom:
            return
        self.edit_started.emit()
        iw, ih = self._pixmap.width(), self._pixmap.height()
        aspect = self._aspect()
        base_w = min(iw, ih * aspect)
        base_h = base_w / aspect
        old_crop_w, old_crop_h = base_w / old_zoom, base_h / old_zoom
        new_crop_w, new_crop_h = base_w / new_zoom, base_h / new_zoom
        scale = self._image_rect.width() / iw
        mouse_x = (event.position().x() - self._image_rect.left()) / scale
        mouse_y = (event.position().y() - self._image_rect.top()) / scale
        old_center_x = iw / 2 + self._crop.offset_x * (iw - old_crop_w) / 2
        old_center_y = ih / 2 + self._crop.offset_y * (ih - old_crop_h) / 2
        relative_x = (mouse_x - old_center_x) / old_crop_w
        relative_y = (mouse_y - old_center_y) / old_crop_h
        self._crop.zoom = new_zoom
        self._set_frame_center(mouse_x - relative_x * new_crop_w, mouse_y - relative_y * new_crop_h, new_crop_w, new_crop_h)
        self.crop_changed.emit()
        self.update()

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._result_preview or not self._crop:
            return
        steps = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        key = event.key()
        # 以输出像素为语义换算成归一化偏移，保证方向键细调稳定。
        if key not in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            return super().keyPressEvent(event)
        dx = (-steps if key == Qt.Key.Key_Left else steps if key == Qt.Key.Key_Right else 0)
        dy = (-steps if key == Qt.Key.Key_Up else steps if key == Qt.Key.Key_Down else 0)
        self.nudge_frame(dx, dy)

    def _set_frame_center(self, center_x: float, center_y: float, crop_w: float, crop_h: float) -> None:
        """将原图坐标中的裁剪框中心转换为受边界限制的归一化偏移。"""
        if not self._crop:
            return
        iw, ih = self._pixmap.width(), self._pixmap.height()
        center_x = max(crop_w / 2, min(iw - crop_w / 2, center_x))
        center_y = max(crop_h / 2, min(ih - crop_h / 2, center_y))
        free_x, free_y = iw - crop_w, ih - crop_h
        self._crop.offset_x = 0.0 if free_x <= 0 else max(-1.0, min(1.0, 2 * (center_x - iw / 2) / free_x))
        self._crop.offset_y = 0.0 if free_y <= 0 else max(-1.0, min(1.0, 2 * (center_y - ih / 2) / free_y))

    def _move_frame_by_screen_pixels(self, dx: int, dy: int) -> None:
        """拖拽只平移裁剪框，底图和黑色画布的位置完全不变。"""
        if not self._crop or self._pixmap.isNull() or self._image_rect.width() <= 0:
            return
        iw, ih = self._pixmap.width(), self._pixmap.height()
        aspect = self._aspect()
        base_w = min(iw, ih * aspect)
        base_h = base_w / aspect
        crop_w, crop_h = base_w / self._crop.zoom, base_h / self._crop.zoom
        old_center_x = iw / 2 + self._crop.offset_x * (iw - crop_w) / 2
        old_center_y = ih / 2 + self._crop.offset_y * (ih - crop_h) / 2
        scale = self._image_rect.width() / iw
        self._set_frame_center(old_center_x + dx / scale, old_center_y + dy / scale, crop_w, crop_h)

    def set_zoom_from_center(self, zoom: float) -> None:
        """调整缩放比例时保持当前裁剪框中心不动。"""
        if self._result_preview or not self._crop or self._pixmap.isNull() or self._image_rect.width() <= 0:
            return
        self._layout()
        iw, ih = self._pixmap.width(), self._pixmap.height()
        aspect = self._aspect()
        base_w = min(iw, ih * aspect)
        base_h = base_w / aspect
        old_crop_w, old_crop_h = base_w / self._crop.zoom, base_h / self._crop.zoom
        center_x = iw / 2 + self._crop.offset_x * (iw - old_crop_w) / 2
        center_y = ih / 2 + self._crop.offset_y * (ih - old_crop_h) / 2
        new_zoom = max(1.0, min(12.0, zoom))
        new_crop_w, new_crop_h = base_w / new_zoom, base_h / new_zoom
        self._crop.zoom = new_zoom
        self._set_frame_center(center_x, center_y, new_crop_w, new_crop_h)
        self.crop_changed.emit()
        self.update()

    def nudge_frame(self, dx: int, dy: int) -> None:
        """提供给方向键和界面按钮的裁剪框像素级微调。"""
        if self._result_preview or not self._crop:
            return
        self._layout()
        self._move_frame_by_screen_pixels(dx, dy)
        self.crop_changed.emit()
        self.update()

    def _corner_at(self, position) -> str:  # type: ignore[no-untyped-def]
        """返回鼠标命中的裁剪框角点；角点用于等比例缩放。"""
        if self._frame.isNull():
            return ""
        points = {
            "top_left": self._frame.topLeft(),
            "top_right": self._frame.topRight(),
            "bottom_left": self._frame.bottomLeft(),
            "bottom_right": self._frame.bottomRight(),
        }
        for name, point in points.items():
            if abs(position.x() - point.x()) <= 12 and abs(position.y() - point.y()) <= 12:
                return name
        return ""

    @staticmethod
    def _cursor_for_corner(corner: str) -> Qt.CursorShape:
        return Qt.CursorShape.SizeFDiagCursor if corner in ("top_left", "bottom_right") else Qt.CursorShape.SizeBDiagCursor

    def _resize_frame_from_corner(self, position, from_center: bool = False) -> None:  # type: ignore[no-untyped-def]
        """拖动任意角等比例缩放裁剪框，裁剪比例始终与输出尺寸一致。"""
        if not self._crop or not self._resize_corner or self._image_rect.width() <= 0:
            return
        iw, ih = self._pixmap.width(), self._pixmap.height()
        aspect = self._aspect()
        base_w = min(iw, ih * aspect)
        base_h = base_w / aspect
        scale = self._image_rect.width() / iw
        mouse_x = (position.x() - self._image_rect.left()) / scale
        mouse_y = (position.y() - self._image_rect.top()) / scale
        if from_center:
            old_crop_w, old_crop_h = base_w / self._crop.zoom, base_h / self._crop.zoom
            center_x = iw / 2 + self._crop.offset_x * (iw - old_crop_w) / 2
            center_y = ih / 2 + self._crop.offset_y * (ih - old_crop_h) / 2
            requested_w = 2 * max(abs(mouse_x - center_x), abs(mouse_y - center_y) * aspect)
            min_w = base_w / 12.0
            crop_w = max(min_w, min(base_w, requested_w))
            crop_h = crop_w / aspect
            self._crop.zoom = base_w / crop_w
            self._set_frame_center(center_x, center_y, crop_w, crop_h)
            return
        anchors = {
            "top_left": (self._frame.bottomRight(), -1, -1),
            "top_right": (self._frame.bottomLeft(), 1, -1),
            "bottom_left": (self._frame.topRight(), -1, 1),
            "bottom_right": (self._frame.topLeft(), 1, 1),
        }
        anchor, direction_x, direction_y = anchors[self._resize_corner]
        anchor_x = (anchor.x() - self._image_rect.left()) / scale
        anchor_y = (anchor.y() - self._image_rect.top()) / scale
        # 从横向或纵向拖动距离推导同一个宽度，保证框永远不变形。
        requested_w = max(abs(mouse_x - anchor_x), abs(mouse_y - anchor_y) * aspect)
        min_w = base_w / 12.0
        crop_w = max(min_w, min(base_w, requested_w))
        crop_h = crop_w / aspect
        self._crop.zoom = base_w / crop_w
        self._set_frame_center(
            anchor_x + direction_x * crop_w / 2,
            anchor_y + direction_y * crop_h / 2,
            crop_w,
            crop_h,
        )
