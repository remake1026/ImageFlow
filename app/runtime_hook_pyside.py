"""冻结应用启动时注册 PySide6 的原生 DLL 目录。"""
from __future__ import annotations

import os
import sys


if sys.platform == "win32" and getattr(sys, "frozen", False):
    _bundle_dir = getattr(sys, "_MEIPASS", "")
    # os.add_dll_directory() 返回的句柄一旦被回收，目录就会立刻从搜索路径
    # 移除。将句柄挂到 sys 上，确保它们在应用整个生命周期内有效。
    sys._imageflow_dll_directory_handles = []
    for _directory in (
        _bundle_dir,
        os.path.join(_bundle_dir, "PySide6"),
        os.path.join(_bundle_dir, "shiboken6"),
    ):
        if os.path.isdir(_directory):
            sys._imageflow_dll_directory_handles.append(os.add_dll_directory(_directory))
