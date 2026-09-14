"""Build the Windows wizard from an already frozen dist/ImageFlow payload."""
from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.1.0"


def nsis_path(path: Path) -> str:
    return str(path).replace("$", "$$").replace('"', '$\\"')


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
    payload = ROOT / "dist/ImageFlow"
    for required in ("ImageFlow.exe", "_internal/PySide6/Qt6Core.dll", "_internal/PySide6/plugins/platforms/qwindows.dll"):
        if not (payload / required).is_file():
            parser.error(f"Missing {required}; run PyInstaller with ImageFlow.spec first.")
    stage = ROOT / "installer_staging/nsis"
    stage.mkdir(parents=True, exist_ok=True)
    release = ROOT / "releases"
    release.mkdir(exist_ok=True)
    files = sorted(p for p in payload.rglob("*") if p.is_file())
    dirs = sorted((p for p in payload.rglob("*") if p.is_dir()), key=lambda p: (-len(p.parts), str(p)))
    manifest = stage / "delete-files.nsh"
    # Preserve the legacy user-editable root products.csv, if present.
    lines = [f'Delete "$INSTDIR\\{nsis_path(p.relative_to(payload))}"' for p in files if p.relative_to(payload).as_posix() != "products.csv"]
    lines += [f'RMDir "$INSTDIR\\{nsis_path(p.relative_to(payload))}"' for p in dirs]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    output = release / f"ImageFlow-{VERSION}-Win10-11-Setup.exe"
    subprocess.run([str(compiler), "/INPUTCHARSET", "UTF8", "/V3", f"/DVERSION={VERSION}",
                    f"/DPAYLOAD={payload}", f"/DOUTPUT={output}", f"/DDELETE_MANIFEST={manifest}",
                    f"/DSIZE_KB={sum(p.stat().st_size for p in files) // 1024}",
                    str(ROOT / "installer/ImageFlow.nsi")], check=True, cwd=ROOT / "installer")
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
