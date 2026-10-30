"""Build the Windows wizard from frozen x64 and x86 payloads."""
from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.2.0"


def nsis_path(path: Path) -> str:
    return str(path).replace("$", "$$").replace('"', '$\\"')


def pe_machine(path: Path) -> int:
    """Read the Windows PE COFF Machine field."""
    import struct
    with path.open("rb") as handle:
        if handle.read(2) != b"MZ":
            raise ValueError(f"Not a PE binary: {path}")
        handle.seek(0x3c)
        handle.seek(struct.unpack("<I", handle.read(4))[0])
        if handle.read(4) != b"PE\0\0":
            raise ValueError(f"Invalid PE signature: {path}")
        return struct.unpack("<H", handle.read(2))[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--makensis", type=Path, help="NSIS 3 Unicode makensis.exe")
    args = parser.parse_args()
    compiler = args.makensis or shutil.which("makensis")
    if not compiler:
        candidates = [Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "NSIS/makensis.exe"]
        cache = Path(os.environ.get("LOCALAPPDATA", "")) / "electron-builder/Cache"
        candidates.extend(sorted(cache.glob("nsis-*/*/makensis.exe")))
        compiler = next((p for p in candidates if p.is_file()), None)
    if not compiler:
        parser.error("Install NSIS 3 (https://nsis.sourceforge.io/Download), or pass --makensis.")
    payloads = {"x64": ROOT / "dist/x64/ImageFlow", "x86": ROOT / "dist/x86/ImageFlow"}
    all_files, all_dirs, sizes = set(), set(), {}
    for arch, payload in payloads.items():
        binding, qt = ("PySide6", "Qt6") if arch == "x64" else ("PySide2", "Qt5")
        for required in ("ImageFlow.exe", f"_internal/{binding}/{qt}Core.dll",
                         f"_internal/{binding}/plugins/platforms/qwindows.dll"):
            if not (payload / required).is_file():
                parser.error(f"Missing {arch}/{required}; run installer/build_windows.py first.")
        # Check PE machine types, not folder names, before advertising either architecture.
        expected = 0x8664 if arch == "x64" else 0x14c
        for binary in payload.rglob("*"):
            if binary.suffix.lower() in (".exe", ".dll", ".pyd"):
                if pe_machine(binary) != expected:
                    parser.error(f"Wrong architecture for {arch}: {binary}")
        files = [p for p in payload.rglob("*") if p.is_file()]
        sizes[arch] = (sum(p.stat().st_size for p in files) + 1023) // 1024
        all_files.update(p.relative_to(payload) for p in files)
        all_dirs.update(p.relative_to(payload) for p in payload.rglob("*") if p.is_dir())
    stage = ROOT / "installer_staging/nsis"
    stage.mkdir(parents=True, exist_ok=True)
    release = ROOT / "releases"
    release.mkdir(exist_ok=True)
    manifest = stage / "delete-files.nsh"
    # Delete only known application files, preserving user-added files and legacy catalogs.
    lines = [f'Delete "$INSTDIR\\{nsis_path(p)}"' for p in sorted(all_files) if p.as_posix() != "products.csv"]
    lines += [f'RMDir "$INSTDIR\\{nsis_path(p)}"' for p in sorted(all_dirs, key=lambda p: (-len(p.parts), str(p)))]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    output = release / f"ImageFlow-{VERSION}-Windows-x86-x64-Setup.exe"
    subprocess.run([str(compiler), "/INPUTCHARSET", "UTF8", "/V3", f"/DVERSION={VERSION}",
                    f"/DPAYLOAD_X64={payloads['x64']}", f"/DPAYLOAD_X86={payloads['x86']}",
                    f"/DOUTPUT={output}", f"/DDELETE_MANIFEST={manifest}",
                    f"/DSIZE_X64_KB={sizes['x64']}", f"/DSIZE_X86_KB={sizes['x86']}",
                    str(ROOT / "installer/ImageFlow.nsi")], check=True, cwd=ROOT / "installer")
    if pe_machine(output) != 0x14c:
        raise RuntimeError("The universal installer bootstrap must be x86 to run on 32-bit Windows.")
    # Keep the existing download URL, with the new wizard inside the ZIP.
    archive = release / "ImageFlow-Installer.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        bundle.write(output, output.name)
        bundle.write(ROOT / "installer/README.txt", "README.txt")
    checksums = []
    for artifact in (output, archive):
        with artifact.open("rb") as handle:
            checksums.append(f"{hashlib.file_digest(handle, 'sha256').hexdigest()}  {artifact.name}")
    (release / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="ascii")
    print(f"Built {output} ({output.stat().st_size / 1024**2:.1f} MiB)")


if __name__ == "__main__":
    main()
