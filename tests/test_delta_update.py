import copy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from app.delta_update import MANIFEST, prepare_delta, safe_path, sha256, validate_manifest
from app.updater import UpdateDownloadWorker, parse_release
from installer.build_delta import build_delta


class Response(BytesIO):
    def __init__(self, raw, status=200, headers=None):
        super().__init__(raw)
        self.status, self.headers = status, headers or {}


class DeltaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.old, self.new, self.stage = (self.base / n for n in ('installed', 'new', 'stage'))
        for p in (self.old, self.new, self.stage):
            p.mkdir()
        pe = bytearray(128)
        pe[:2] = b'MZ'; struct.pack_into('<I', pe, 0x3c, 64)
        pe[64:68] = b'PE\0\0'; struct.pack_into('<H', pe, 68, 0x8664)
        for p in (self.old, self.new):
            (p / 'ImageFlow.exe').write_bytes(pe)
            (p / '_internal').mkdir()
            (p / '_internal/stable.dll').write_bytes(b'stable runtime')
            (p / '_internal/changed.dat').write_bytes(b'old')
        (self.new / '_internal/changed.dat').write_bytes(b'new')
        self.full = b'full-installer-fixture'
        build_delta(self.old, self.base / 'old-release', '1.3.1', 'x64')
        self.rebuild()

    def rebuild(self):
        self.pack, self.manifest = build_delta(self.new, self.base / 'release', '1.4.0', 'x64')
        self.release = {'current': '1.3.1', 'version': '1.4.0', 'url': 'full', 'size': 100000,
                        'sha256': hashlib.sha256(self.full).hexdigest(), 'name': 'setup.exe',
                        'delta': {'x64': {'manifest': {'url': 'manifest', 'size': self.manifest.stat().st_size, 'sha256': sha256(self.manifest)},
                                          'pack': {'url': 'pack', 'size': self.pack.stat().st_size, 'sha256': sha256(self.pack)}}}}
        self.calls = []

    def request(self, url, headers=None):
        self.calls.append((url, headers))
        if url == 'manifest':
            return Response(self.manifest.read_bytes())
        if url == 'full':
            return Response(self.full)
        start, end = map(int, re.fullmatch(r'bytes=(\d+)-(\d+)', headers['Range']).groups())
        return Response(self.pack.read_bytes()[start:end+1], 206, {'Content-Range': f'bytes {start}-{end}/{self.pack.stat().st_size}'})

    def prepare(self):
        return prepare_delta(self.release, self.old, self.stage, self.request, lambda p: None, lambda s: None)

    def test_downloads_only_changed_file_not_runtime(self):
        plan = json.loads(self.prepare().read_text(encoding='utf-8'))
        self.assertEqual([e['path'] for e in plan['changed']], ['_internal/changed.dat'])
        self.assertEqual(len([c for c in self.calls if c[0] == 'pack']), 1)
        self.assertEqual((self.stage / 'files/_internal/changed.dat').read_bytes(), b'new')
        self.assertEqual((self.old / '_internal/changed.dat').read_bytes(), b'old')

    def test_missing_and_new_files_are_downloaded_removed_files_recorded(self):
        (self.old / '_internal/stable.dll').unlink()
        (self.new / '_internal/changed.dat').unlink()
        (self.new / '_internal/new.dat').write_bytes(b'added')
        self.rebuild()
        plan = json.loads(self.prepare().read_text(encoding='utf-8'))
        self.assertEqual({e['path'] for e in plan['changed']}, {'_internal/new.dat', '_internal/stable.dll'})
        self.assertEqual([e['path'] for e in plan['removed']], ['_internal/changed.dat'])

    def test_identical_files_need_no_pack_request(self):
        (self.new / '_internal/changed.dat').write_bytes(b'old')
        self.rebuild(); self.prepare()
        self.assertEqual([c[0] for c in self.calls], ['manifest'])

    def test_manifest_corruption_rejected(self):
        self.manifest.write_bytes(b'corrupt')
        with self.assertRaises(ValueError): self.prepare()

    def test_bad_range_or_corrupt_payload_rejected(self):
        good_request = self.request
        for kind in ('ignored_range', 'wrong_range', 'corrupt'):
            with self.subTest(kind=kind):
                def request(url, headers=None):
                    response = good_request(url, headers)
                    if url == 'pack':
                        if kind == 'ignored_range': response.status = 200
                        elif kind == 'wrong_range': response.headers['Content-Range'] = 'bytes 1-2/3'
                        else: return Response(b'x' * len(response.getvalue()), 206, response.headers)
                    return response
                with self.assertRaises((ValueError, OSError, EOFError)):
                    prepare_delta(self.release, self.old, self.stage, request, lambda p: None, lambda s: None)

    def test_paths_and_case_collisions_rejected(self):
        for name in ('../escape', '_internal/../escape', '_internal/CON.txt', '_internal/a:stream', '_internal/a.', '_internal\\escape', 'products.csv', '_internal/presets.json'):
            with self.subTest(name=name), self.assertRaises(ValueError): safe_path(self.old, name)
        data = json.loads(self.manifest.read_text())
        data['files'].append(copy.deepcopy(data['files'][0]))
        with self.assertRaises(ValueError): validate_manifest(data, '1.4.0', 'x64')

    def test_wrong_architecture_rejected(self):
        data = json.loads(self.manifest.read_text())
        with self.assertRaises(ValueError): validate_manifest(data, '1.4.0', 'x86')

    def test_auto_full_fallback_for_missing_manifest_and_bad_ranges(self):
        # A deliberately generous full-file size is used for delta selection;
        # actual fallback downloads still enforce exact length.
        self.full = b'F' * 100000
        self.release['sha256'] = hashlib.sha256(self.full).hexdigest()
        for reason in ('missing_manifest', 'bad_range'):
            with self.subTest(reason=reason):
                if reason == 'missing_manifest': (self.old / MANIFEST).unlink()
                else: build_delta(self.old, self.base / 'old-release', '1.3.1', 'x64')
                def request(url, headers=None):
                    result = self.request(url, headers)
                    if url == 'pack': result.status = 200
                    return result
                worker = UpdateDownloadWorker(self.release, self.old)
                paths, failures, statuses = [], [], []
                worker.result.connect(paths.append); worker.failed.connect(failures.append); worker.status.connect(statuses.append)
                with patch('app.updater._request', side_effect=request): worker.run()
                self.assertFalse(failures)
                self.assertTrue(any('完整安装包' in s for s in statuses))
                self.assertEqual(Path(paths[0]).read_bytes(), self.full)
                Path(paths[0]).unlink()

    @unittest.skipUnless(os.name == 'nt', 'Windows apply helper')
    def test_apply_preserves_user_files_and_updates_manifest(self):
        (self.old / 'my-photo.txt').write_text('personal')
        plan = self.prepare()
        result = self.apply(plan)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr + self.logs())
        self.assertEqual((self.old / '_internal/changed.dat').read_bytes(), b'new')
        self.assertEqual((self.old / 'my-photo.txt').read_text(), 'personal')
        self.assertEqual(json.loads((self.old / MANIFEST).read_text())['version'], '1.4.0')

    def logs(self):
        return '\n'.join(p.read_text(encoding='utf-8-sig') for p in self.stage.glob('*.log'))

    def fallback_fixture(self, plan):
        # A small real executable stands in for the trusted full installer.
        exe = self.stage / 'full.exe'
        code = 'using System; using System.IO; class Setup { static int Main(string[] a) { foreach(var v in a) if(v.StartsWith("/D=")) File.WriteAllText(Path.Combine(v.Substring(3),"fallback-marker"),"installed"); return 0; } }'
        script = self.stage / 'compile.ps1'
        script.write_text("Add-Type -TypeDefinition '" + code + "' -OutputAssembly '" + str(exe).replace("'", "''") + "' -OutputType ConsoleApplication", encoding='utf-8-sig')
        compiled = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)], capture_output=True, text=True, errors='replace')
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        data = json.loads(plan.read_text(encoding='utf-8'))
        data['full'] = {'url': 'https://github.com/remake1026/ImageFlow/releases/download/v1.4.0/ImageFlow-1.4.0-Windows-x86-x64-Setup.exe', 'size': exe.stat().st_size, 'sha256': sha256(exe)}
        plan.write_text(json.dumps(data), encoding='utf-8')

    @unittest.skipUnless(os.name == 'nt', 'Windows apply helper')
    def test_apply_corruption_automatically_runs_full_installer(self):
        plan = self.prepare(); self.fallback_fixture(plan)
        (self.stage / 'files/_internal/changed.dat').write_bytes(b'corrupt')
        result = self.apply(plan)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr + self.logs())
        self.assertTrue((self.old / 'fallback-marker').is_file())
        self.assertEqual((self.stage / 'result.txt').read_text().strip(), 'full')
        self.assertEqual((self.old / '_internal/changed.dat').read_bytes(), b'old')

    @unittest.skipUnless(os.name == 'nt', 'Windows file locks')
    def test_locked_second_file_rolls_back_first_then_runs_full_installer(self):
        import ctypes
        from ctypes import wintypes
        (self.new / '_internal/stable.dll').write_bytes(b'new runtime')
        self.rebuild(); plan = self.prepare(); self.fallback_fixture(plan)
        create = ctypes.windll.kernel32.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        handle = create(str(self.old / '_internal/stable.dll'), 0x80000000, 1, None, 3, 0, None)
        self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
        try:
            result = self.apply(plan)
        finally:
            ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(handle))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr + self.logs())
        self.assertEqual((self.old / '_internal/changed.dat').read_bytes(), b'old')
        self.assertEqual((self.old / '_internal/stable.dll').read_bytes(), b'stable runtime')
        self.assertTrue((self.old / 'fallback-marker').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows uninstaller')
    def test_uninstall_removes_incrementally_added_file_preserves_user_file(self):
        (self.new / '_internal/new.dat').write_bytes(b'added')
        self.rebuild(); plan = self.prepare()
        self.assertEqual(self.apply(plan).returncode, 0, self.logs())
        (self.old / 'my-photo.txt').write_text('personal')
        result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                 str(Path(__file__).resolve().parents[1] / 'resources/remove_updated_files.ps1'),
                                 '-InstallDir', str(self.old)], capture_output=True, text=True, errors='replace', timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.old / '_internal/new.dat').exists())
        self.assertEqual((self.old / 'my-photo.txt').read_text(), 'personal')

    def apply(self, plan):
        return subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                               str(Path(__file__).resolve().parents[1] / 'resources/install_delta.ps1'),
                               '-AppPid', '2147483647', '-Plan', str(plan), '-AppPath', str(self.old / 'ImageFlow.exe'),
                               '-NoRestart', '-QuietFailure'], capture_output=True, text=True, errors='replace', timeout=30)
