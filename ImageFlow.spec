# -*- mode: python ; coding: utf-8 -*-


import struct

_qt_binding = 'PySide2' if struct.calcsize('P') == 4 else 'PySide6'

if _qt_binding == 'PySide2':
    # Qt5's embedded qt.conf loses non-ASCII prefixes on Windows. Use the
    # installed wheel location so builds also work in Chinese project paths.
    from PyInstaller.utils.hooks.qt import pyside2_library_info as _qt_info
    _old_prefix = _qt_info.location['PrefixPath'].rstrip('/.')
    _new_prefix = _qt_info.package_location.as_posix()
    for _key, _value in _qt_info.location.items():
        if _value.startswith(_old_prefix):
            _qt_info.location[_key] = _new_prefix + _value[len(_old_prefix):]
    _qt_info.qt_inside_package = True
    _qt_info.qt_lib_dir = _qt_info.package_location

a = Analysis(
    ['main.py'],
    pathex=[SPECPATH],
    binaries=[],
    datas=[('resources', 'resources'), ('products.csv', '.')],
    hiddenimports=['app.qt'] + [f'{_qt_binding}.{module}' for module in ('QtCore', 'QtGui', 'QtWidgets', 'QtTest', 'QtNetwork')],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['app/runtime_hook_pyside.py'],
    excludes=['numpy', 'PySide6' if _qt_binding == 'PySide2' else 'PySide2'],
    noarchive=False,
    optimize=0,
)

# Codex/开发环境的 PATH 中可能包含 Poppler 自带的 ICU。PyInstaller 会误将
# 这套 ICU 当成 Qt6Core 的依赖收集，但其导出符号与 Windows 版 Qt 不兼容，
# 最终导致冻结程序启动时报“DLL load failed while importing QtCore”。Qt6Core
# 应使用 Windows 系统自带的 icuuc.dll，因此从发行包中排除误收集的两个文件。
_incompatible_icu = {'icuuc.dll', 'icudt78.dll'}
a.binaries = [
    entry for entry in a.binaries
    if entry[0].replace('\\', '/').rsplit('/', 1)[-1].lower() not in _incompatible_icu
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ImageFlow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/imageflow-logo.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ImageFlow',
)
