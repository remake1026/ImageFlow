"""GitHub Releases 更新检查和带校验的安装包下载。"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import shutil
import sys

from app.delta_update import prepare_delta
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
    result = {"current": current, "version": version, "notes": str(data.get("body") or "暂无更新说明"),
            "url": url, "sha256": digest[7:].lower(), "size": size, "name": name}
    result['delta'] = {}
    for arch in ('x64', 'x86'):
        try:
            entries = {}
            for kind, suffix in (('manifest', 'manifest.json'), ('pack', 'files.bin')):
                filename = f'ImageFlow-{version}-{arch}-{suffix}'
                matches = [a for a in data.get('assets', []) if a.get('name') == filename]
                if len(matches) != 1:
                    raise ValueError('Missing delta asset')
                item = matches[0]
                expected_url = f'https://github.com/remake1026/ImageFlow/releases/download/{tag}/{filename}'
                if item.get('browser_download_url') != expected_url or not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', item.get('digest') or ''):
                    raise ValueError('Invalid delta asset')
                if type(item.get('size')) is not int or not 0 < item['size'] <= MAX_INSTALLER_BYTES:
                    raise ValueError('Invalid delta size')
                entries[kind] = {'url': expected_url, 'size': item['size'], 'sha256': item['digest'][7:].lower()}
            result['delta'][arch] = entries
        except (ValueError, KeyError, TypeError):
            pass  # A release without a usable delta always retains full-install fallback.
    return result


def _request(url: str, headers: dict | None = None):
    accept = "application/vnd.github+json" if url.startswith("https://api.github.com/") else "application/octet-stream"
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ImageFlow-Updater", "Accept": accept, **(headers or {})}), timeout=30)


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
    status = Signal(str)
    result = Signal(str)
    failed = Signal(str)

    def __init__(self, release: dict, install_dir: Path | None = None):
        super().__init__()
        self.release = release
        self.install_dir = install_dir or (Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else None)

    def run(self):
        path = None
        if self.install_dir and self.release.get('delta'):
            stage = Path(tempfile.mkdtemp(prefix='ImageFlow-delta-'))
            try:
                self.status.emit('正在检查增量更新……')
                plan = prepare_delta(self.release, self.install_dir, stage, _request, self.progress.emit, self.status.emit)
                self.result.emit(str(plan))
                return
            except Exception:
                # This directory was created by this worker, never an installation or user-data directory.
                if stage.parent.resolve() == Path(tempfile.gettempdir()).resolve() and stage.name.startswith('ImageFlow-delta-'):
                    shutil.rmtree(stage, ignore_errors=True)
                self.status.emit('增量更新不可用，正在下载完整安装包……')
                self.progress.emit(0)
        else:
            self.status.emit('正在下载完整安装包……')
        try:
            with tempfile.NamedTemporaryFile(prefix="ImageFlow-update-", suffix=".exe", delete=False) as output:
                path = Path(output.name)
                digest = hashlib.sha256()
                count = 0
                with _request(self.release["url"]) as response:
                    while True:
                        block = response.read(64 * 1024)
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
