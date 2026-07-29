"""项目的数据模型。所有编辑参数只保存为数值，绝不修改原始图片。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass
class SizeTemplate:
    id: str
    name: str
    width: int
    height: int
    selected: bool = False
    builtin: bool = True

    @property
    def aspect(self) -> float:
        return self.width / self.height

    @property
    def display_name(self) -> str:
        """界面只显示比例/模板名，不展示括号内的输出像素。"""
        return self.name.split("（", 1)[0].strip()

    @property
    def folder_name(self) -> str:
        """输出子文件夹只使用比例，例如 4:5 对应 4x5。"""
        return self.display_name.replace(':', 'x').replace('，', '_').replace(' ', '')

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SizeTemplate":
        return cls(**data)


def builtin_templates() -> list[SizeTemplate]:
    return [
        SizeTemplate("original", "原图比例", 0, 0),
        SizeTemplate("1x1", "1:1（1080×1080）", 1080, 1080),
        SizeTemplate("4x5", "4:5（1080×1350）", 1080, 1350, True),
        SizeTemplate("3x4", "3:4（1080×1440）", 1080, 1440, True),
        SizeTemplate("9x16", "9:16（1080×1920）", 1080, 1920),
        SizeTemplate("16x9", "16:9（1920×1080）", 1920, 1080),
    ]


@dataclass
class CropSettings:
    """offset 范围为 -1 至 1；zoom=1 是自动适配，数值越大越放大。"""
    zoom: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    guide_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CropSettings":
        return cls(**data)


@dataclass
class WatermarkSettings:
    enabled: bool = False
    anchor: str = "右下"
    offset_x: float = 0.0  # 输出宽度的百分比
    offset_y: float = 0.0  # 输出高度的百分比
    size_percent: float = 18.0
    opacity: int = 100
    rotation: float = 0.0
    margin_percent: float = 3.0
    safe_area: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WatermarkSettings":
        return cls(**data)


@dataclass
class PhotoItem:
    path: str
    id: str = field(default_factory=lambda: uuid4().hex)
    crop_by_template: dict[str, CropSettings] = field(default_factory=dict)
    watermark_by_template: dict[str, WatermarkSettings] = field(default_factory=dict)

    @property
    def filename(self) -> str:
        return Path(self.path).name

    def crop(self, template_id: str) -> CropSettings:
        return self.crop_by_template.setdefault(template_id, CropSettings())

    def watermark(self, template_id: str) -> WatermarkSettings:
        return self.watermark_by_template.setdefault(template_id, WatermarkSettings())

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "id": self.id,
            "crop_by_template": {key: value.to_dict() for key, value in self.crop_by_template.items()},
            "watermark_by_template": {key: value.to_dict() for key, value in self.watermark_by_template.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PhotoItem":
        return cls(
            path=data["path"],
            id=data.get("id", uuid4().hex),
            crop_by_template={k: CropSettings.from_dict(v) for k, v in data.get("crop_by_template", {}).items()},
            watermark_by_template={k: WatermarkSettings.from_dict(v) for k, v in data.get("watermark_by_template", {}).items()},
        )


@dataclass
class ExportSettings:
    output_folder: str = ""
    image_format: str = "JPG"
    jpg_quality: int = 100
    subfolders: bool = True
    overwrite: bool = False
    keep_icc: bool = True
    keep_exif: bool = False
    naming_pattern: str = "{brand} {sku} {color} {original}"
    brand: str = "NuPhy"
    sku: str = ""
    color: str = ""
    date: str = ""
    start_sequence: int | None = None
    # 仅用于当前界面与导出任务，不写入项目或命名预设。
    replace_original_name: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("replace_original_name", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExportSettings":
        return cls(**data)
