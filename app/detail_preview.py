"""按需解码当前照片的高清预览；不写入磁盘缓存或导出数据。"""
from __future__ import annotations

from math import sqrt
from pathlib import Path

from app.qt.QtCore import QObject, QSize, QThread, Qt, Signal
from app.qt.QtGui import QImage, QImageReader

# 只保留一张 32 位预览图，常驻像素缓存最多约 128 MiB。
# 解码器和格式转换仍可能临时使用额外内存。
MAX_DETAIL_PIXELS = 32 * 1024 * 1024


def source_key(path: str) -> tuple[str, int, int]:
    file = Path(path)
    stat = file.stat()
    return str(file.resolve()), stat.st_mtime_ns, stat.st_size


def load_detail_image(path: str, max_pixels: int = MAX_DETAIL_PIXELS) -> QImage:
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and size.width() * size.height() > max_pixels:
        scale = sqrt(max_pixels / (size.width() * size.height()))
        reader.setScaledSize(QSize(max(1, int(size.width() * scale)), max(1, int(size.height() * scale))))
    image = reader.read()
    if image.isNull():
        raise OSError(reader.errorString())
    # 兼容不提供尺寸或不支持解码时缩放的格式。
    if image.width() * image.height() > max_pixels:
        scale = sqrt(max_pixels / (image.width() * image.height()))
        image = image.scaled(max(1, int(image.width() * scale)), max(1, int(image.height() * scale)),
                             Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


class DetailPreviewWorker(QThread):
    def __init__(self, key: tuple[str, int, int], max_pixels: int, parent: QObject) -> None:
        super().__init__(parent)
        self.key = key
        self.max_pixels = max_pixels
        self.image = QImage()
        self.error = ""

    def run(self) -> None:
        try:
            if not self.isInterruptionRequested():
                image = load_detail_image(self.key[0], self.max_pixels)
                if not self.isInterruptionRequested():
                    self.image = image
        except Exception as error:
            self.error = str(error)


class DetailPreviewLoader(QObject):
    ready = Signal()
    failed = Signal(str)

    def __init__(self, parent: QObject, max_pixels: int = MAX_DETAIL_PIXELS) -> None:
        super().__init__(parent)
        self.max_pixels = max_pixels
        self.image = QImage()
        self._source = ""
        self._cached_key = None
        self._wanted_key = None
        self._failed_key = None
        self._worker = None
        self._closed = False

    def set_source(self, path: str) -> None:
        if path == self._source:
            return
        self._source = path
        self.image = QImage()
        self._cached_key = self._wanted_key = self._failed_key = None
        if self._worker:
            self._worker.requestInterruption()

    def request(self) -> None:
        if self._closed or not self._source:
            return
        try:
            key = source_key(self._source)
        except OSError:
            self.image = QImage()
            self._wanted_key = None
            if self._worker:
                self._worker.requestInterruption()
            return
        if key == self._cached_key or key == self._failed_key:
            return
        self.image = QImage()
        self._cached_key = None
        self._wanted_key = key
        if self._worker is None:
            self._start()
        elif self._worker.key != key:
            self._worker.requestInterruption()

    def _start(self) -> None:
        if self._closed or self._wanted_key is None:
            return
        self._worker = DetailPreviewWorker(self._wanted_key, self.max_pixels, self)
        self._worker.finished.connect(self._finished)
        self._worker.start()

    def _finished(self) -> None:
        worker = self._worker
        if worker is None:
            return
        self._worker = None
        wanted = not self._closed and worker.key == self._wanted_key
        if wanted:
            try:
                current_key = source_key(self._source)
            except OSError:
                current_key = None
            if current_key != worker.key:
                self._wanted_key = current_key
                wanted = False
        if wanted and not worker.isInterruptionRequested():
            if not worker.image.isNull():
                self.image = worker.image  # QImage 隐式共享，不再创建大尺寸 QPixmap 副本。
                self._cached_key = worker.key
                self.ready.emit()
            else:
                self._failed_key = worker.key
                self.failed.emit(worker.error or "无法读取高清预览")
            self._wanted_key = None
        worker.image = QImage()
        worker.deleteLater()
        # 快速切图时最多一个解码任务；完成后只处理最后选中的照片。
        self._start()

    def shutdown(self) -> None:
        self._closed = True
        self._wanted_key = None
        if self._worker:
            self._worker.requestInterruption()
            self._worker.wait()
        self.image = QImage()
