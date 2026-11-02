"""Optional independent user-data location for portable and test profiles."""
from __future__ import annotations

import os
from pathlib import Path


def configured_data_directory() -> Path | None:
    value = os.environ.get("IMAGEFLOW_DATA_DIR", "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise RuntimeError("IMAGEFLOW_DATA_DIR must be an absolute directory path.")
    return path.resolve()
