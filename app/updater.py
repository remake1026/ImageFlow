"""GitHub Releases 更新检查和带校验的安装包下载。"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from app.qt.QtCore import QThread, Signal

RELEASE_URL = "https://api.github.com/repos/remake1026/ImageFlow/releases/latest"
MAX_INSTALLER_BYTES = 1024 * 1024 * 1024


def version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        raise ValueError("版本号格式无效")
    return tuple(int(part) for part in match.groups())


def parse_release(data: dict, current: str) -> dict | None:
    tag = data.get("tag_name", "")
    if version_tuple(tag) <= version_tuple(current):
        return None
    version = tag.lstrip("v")
    name = f"ImageFlow-{version}-Windows-x86-x64-Setup.exe"
    assets = [asset for asset in data.get("assets", []) if asset.get("name") == name]
    if len(assets) != 1:
        raise ValueError("新版本没有找到匹配的 Windows 安装包。")
    asset = assets[0]
    url = asset.get("browser_download_url", "")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or parsed.path != f"/remake1026/ImageFlow/releases/download/{tag}/{name}":
        raise ValueError("安装包下载地址无效。")
    digest = asset.get("digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise ValueError("安装包缺少 SHA-256 校验值，请联系发布者。")
    size = asset.get("size")
    if not isinstance(size, int) or not 0 < size <= MAX_INSTALLER_BYTES:
        raise ValueError("安装包大小无效。")
    return {"version": version, "notes": str(data.get("body") or "暂无更新说明"),
            "url": url, "sha256": digest[7:].lower(), "size": size, "name": name}


def _request(url: str):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ImageFlow-Updater", "Accept": "application/vnd.github+json"}), timeout=30)


class UpdateCheckWorker(QThread):
    result = Signal(object)
    failed = Signal(str)
    release_not_found = Signal()

    def __init__(self, current: str):
        super().__init__()
        self.current = current

    def run(self):
        try:
            with _request(RELEASE_URL) as response:
                data = json.loads(response.read(2 * 1024 * 1024))
            self.result.emit(parse_release(data, self.current))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                self.release_not_found.emit()
            else:
                self.failed.emit(str(error))
        except Exception as error:
            self.failed.emit(str(error))


class UpdateDownloadWorker(QThread):
    progress = Signal(int)
    result = Signal(str)
    failed = Signal(str)

    def __init__(self, release: dict):
        super().__init__()
        self.release = release

    def run(self):
        path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="ImageFlow-update-", suffix=".exe", delete=False) as output:
                path = Path(output.name)
                digest = hashlib.sha256()
                count = 0
                with _request(self.release["url"]) as response:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        count += len(block)
                        if count > self.release["size"]:
                            raise ValueError("下载文件大小与发布信息不符。")
                        digest.update(block)
                        output.write(block)
                        self.progress.emit(int(count * 100 / self.release["size"]))
            if count != self.release["size"] or digest.hexdigest() != self.release["sha256"]:
                raise ValueError("安装包校验失败，请重试。")
            self.result.emit(str(path))
        except Exception as error:
            if path:
                path.unlink(missing_ok=True)
            self.failed.emit(str(error))
