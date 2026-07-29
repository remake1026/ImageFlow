"""项目文件序列化；项目只引用图片路径，不复制原文件。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ExportSettings, PhotoItem, SizeTemplate


def save_project(path: str, photos: list[PhotoItem], templates: list[SizeTemplate], watermark_path: str, export: ExportSettings) -> None:
    payload: dict[str, Any] = {
        "version": 1,
        "photos": [photo.to_dict() for photo in photos],
        "templates": [template.to_dict() for template in templates],
        "watermark_path": watermark_path,
        "export": export.to_dict(),
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_project(path: str) -> tuple[list[PhotoItem], list[SizeTemplate], str, ExportSettings]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return (
        [PhotoItem.from_dict(item) for item in data.get("photos", [])],
        [SizeTemplate.from_dict(item) for item in data.get("templates", [])],
        data.get("watermark_path", ""),
        ExportSettings.from_dict(data.get("export", {})),
    )
