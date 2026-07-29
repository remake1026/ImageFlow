"""轻量 JSON 预设存储。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStandardPaths


def _path() -> Path:
    root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation))
    root.mkdir(parents=True, exist_ok=True)
    return root / "presets.json"


def load_presets() -> dict[str, Any]:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"watermarks": {}, "naming": {}, "last_output": ""}


def save_presets(data: dict[str, Any]) -> None:
    _path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
