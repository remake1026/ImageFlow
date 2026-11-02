"""Validated per-file updates fetched as byte ranges from a release pack."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import struct

SCHEMA = 1
MANIFEST = "update-manifest.json"
MAX_MANIFEST = 2 * 1024 * 1024
MAX_FILE = 1024 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path(root: Path, name: str) -> Path:
    # Only application-owned files. Never user catalogs, projects or presets.
    if not isinstance(name, str) or not (name == 'ImageFlow.exe' or name.startswith('_internal/')):
        raise ValueError('Invalid update path')
    parts = name.split('/')
    for part in parts:
        if (not part or part in ('.', '..') or part.endswith(('.', ' '))
                or re.search(r'[\\:<>"|?*\x00-\x1f]', part)
                or part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(1, 10)], *[f'LPT{i}' for i in range(1, 10)]}):
            raise ValueError('Unsafe update path')
    if parts[-1].lower() == 'presets.json' or Path(name).suffix.lower() in ('.key', '.pem', '.imageflowproject'):
        raise ValueError('User data cannot be updated')
    root = root.absolute()
    target = root.joinpath(*parts)
    for node in (root, *target.parents, target):
        try:
            info = node.lstat()
        except FileNotFoundError:
            continue
        if node.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Reparse points cannot be updated')
    return target


def validate_manifest(data: dict, version: str, arch: str) -> list[dict]:
    if data.get('schema') != SCHEMA or data.get('version') != version or data.get('architecture') != arch:
        raise ValueError('Incompatible update manifest')
    files = data.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= 5000:
        raise ValueError('Invalid file list')
    seen, total, end = set(), 0, 0
    for entry in files:
        name = entry['path']
        safe_path(Path.cwd(), name)
        if name.casefold() in seen or not re.fullmatch('[a-f0-9]{64}', entry['sha256']):
            raise ValueError('Duplicate path or invalid digest')
        seen.add(name.casefold())
        size, offset, length = (entry[key] for key in ('size', 'offset', 'length'))
        if any(type(value) is not int for value in (size, offset, length)) or not 0 <= size <= MAX_FILE or offset != end or not 1 <= length <= MAX_FILE:
            raise ValueError('Invalid file range')
        total += size
        end = offset + length
    if 'imageflow.exe' not in seen or total > 3 * MAX_FILE or data.get('pack_size') != end:
        raise ValueError('Incomplete update manifest')
    return files


def architecture(executable: Path) -> str:
    with executable.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('Missing installed executable')
        stream.seek(0x3c)
        stream.seek(struct.unpack('<I', stream.read(4))[0])
        if stream.read(4) != b'PE\0\0':
            raise ValueError('Invalid installed executable')
        return {0x8664: 'x64', 0x14c: 'x86'}[struct.unpack('<H', stream.read(2))[0]]


def prepare_delta(release: dict, root: Path, stage: Path, request, progress, status) -> Path:
    arch = architecture(root / 'ImageFlow.exe')
    previous = json.loads((root / MANIFEST).read_text(encoding='utf-8'))
    previous_files = validate_manifest(previous, previous['version'], arch)
    if previous['version'] != release['current']:
        raise ValueError('Installed version does not match its manifest')
    manifest_asset, pack = (release['delta'][arch][key] for key in ('manifest', 'pack'))
    if manifest_asset['size'] > MAX_MANIFEST:
        raise ValueError('Manifest too large')
    with request(manifest_asset['url']) as response:
        raw = response.read(MAX_MANIFEST + 1)
    if len(raw) != manifest_asset['size'] or hashlib.sha256(raw).hexdigest() != manifest_asset['sha256']:
        raise ValueError('Manifest checksum mismatch')
    target = json.loads(raw)
    files = validate_manifest(target, release['version'], arch)
    if target['pack_size'] != pack['size']:
        raise ValueError('Pack size mismatch')
    status('正在校验本地文件，计算需要下载的内容……')
    changed = [e for e in files if not safe_path(root, e['path']).is_file() or sha256(safe_path(root, e['path'])) != e['sha256']]
    total = sum(e['length'] for e in changed)
    if total >= release['size']:
        raise ValueError('Full installer is smaller than changed files')
    completed = 0
    for entry in changed:
        start, length = entry['offset'], entry['length']
        status(f"正在下载变化文件（{len(changed)} 个，共 {total / 1024**2:.1f} MB）……")
        expected_range = f"bytes {start}-{start + length - 1}/{pack['size']}"
        with request(pack['url'], {'Range': f'bytes={start}-{start + length - 1}', 'Accept-Encoding': 'identity'}) as response:
            if response.status != 206 or response.headers.get('Content-Range') != expected_range:
                raise ValueError('Server does not support exact range downloads')
            compressed = io.BytesIO()
            remaining = length
            while remaining:
                block = response.read(min(65536, remaining))
                if not block:
                    raise ValueError('Incomplete file download')
                compressed.write(block)
                remaining -= len(block)
                progress(int((completed + length - remaining) * 100 / max(1, total)))
            if response.read(1):
                raise ValueError('Excess range data')
        compressed.seek(0)
        destination = safe_path(stage / 'files', entry['path'])
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest, count = hashlib.sha256(), 0
        with gzip.GzipFile(fileobj=compressed) as source, destination.open('wb') as output:
            while block := source.read(min(65536, entry['size'] - count + 1)):
                count += len(block)
                if count > entry['size']:
                    raise ValueError('Expanded file exceeds declared size')
                digest.update(block)
                output.write(block)
        if count != entry['size'] or digest.hexdigest() != entry['sha256']:
            raise ValueError('Changed file checksum mismatch')
        completed += length
    new_names = {e['path'].casefold() for e in files}
    removed = [e for e in previous_files if e['path'].casefold() not in new_names]
    # Do not remove obsolete managed files modified by the user: use the full installer.
    for entry in removed:
        path = safe_path(root, entry['path'])
        if path.exists() and sha256(path) != entry['sha256']:
            raise ValueError('Obsolete file was modified locally')
    (stage / MANIFEST).write_bytes(raw)
    plan = {'schema': SCHEMA, 'install_dir': str(root.resolve()), 'version': release['version'],
            'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'changed': changed, 'removed': removed,
            'full': {k: release[k] for k in ('url', 'size', 'sha256', 'name')}}
    plan_path = stage / 'plan.json'
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')
    progress(100)
    return plan_path
