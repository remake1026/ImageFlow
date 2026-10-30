"""轻量 JSON 预设存储。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.qt.QtCore import QCoreApplication, QStandardPaths


def _path() -> Path:
    root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation))
    root.mkdir(parents=True, exist_ok=True)
    return root / "presets.json"


def load_presets() -> dict[str, Any]:
    try:
        path = _path()
        if not path.exists() and QCoreApplication.organizationName() == "ImageFlow":
            try:
                QCoreApplication.setOrganizationName("ImageFlow")
                legacy = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)) / "presets.json"
            finally:
                QCoreApplication.setOrganizationName("ImageFlow")
            if legacy.is_file():
                path = legacy
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"watermarks": {}, "naming": {}, "last_output": ""}


def save_presets(data: dict[str, Any]) -> None:
    _path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
