"""Create reproducible gzip file records and their range-download manifest."""
import gzip
import hashlib
import json
from pathlib import Path

from app.delta_update import MANIFEST, safe_path, validate_manifest


def build_delta(payload: Path, output: Path, version: str, arch: str) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    pack = output / f'ImageFlow-{version}-{arch}-files.bin'
    records = []
    with pack.open('wb') as stream:
        for path in sorted(p for p in payload.rglob('*') if p.is_file() and p.name != MANIFEST):
            name = path.relative_to(payload).as_posix()
            safe_path(payload, name)
            raw = path.read_bytes()
            data = gzip.compress(raw, compresslevel=9, mtime=0)
            records.append({'path': name, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                            'offset': stream.tell(), 'length': len(data)})
            stream.write(data)
    manifest = {'schema': 1, 'version': version, 'architecture': arch, 'pack_size': pack.stat().st_size, 'files': records}
    validate_manifest(manifest, version, arch)
    content = json.dumps(manifest, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    path = output / f'ImageFlow-{version}-{arch}-manifest.json'
    path.write_bytes(content)
    (payload / MANIFEST).write_bytes(content)
    return [pack, path]
