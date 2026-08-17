"""后台导入图片缩略图，避免批量导入时阻塞主界面。"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image
from PySide6.QtCore import QThread, Signal

from .image_processor import load_thumbnail


@dataclass
class ImportResult:
    """导入任务的成功结果与无法读取的文件。"""

    thumbnails: list[tuple[str, Image.Image]]
    failed_paths: list[str]


class ImportWorker(QThread):
    """在后台读取并校正图片方向，同时生成预览缩略图。"""

    progress = Signal(int, int, str)
    completed = Signal(object)
    cancelled = Signal(object)

    def __init__(self, paths: list[str]) -> None:
        super().__init__()
        self.paths = paths
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        thumbnails: list[tuple[str, Image.Image]] = []
        failed_paths: list[str] = []
        total = len(self.paths)
        for current, path in enumerate(self.paths, start=1):
            if self._cancelled:
                self.cancelled.emit(ImportResult(thumbnails, failed_paths))
                return
            try:
                thumbnails.append((path, load_thumbnail(path)))
            except Exception:
                failed_paths.append(path)
            self.progress.emit(current, total, path)
        self.completed.emit(ImportResult(thumbnails, failed_paths))
