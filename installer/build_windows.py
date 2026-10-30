"""Build both architectures and combine them into one offline Windows installer."""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "installer_staging"
X86_PACKAGE = "https://api.nuget.org/v3-flatcontainer/pythonx86/3.10.11/pythonx86.3.10.11.nupkg"
# Official Python NuGet package SHA512, published in the NuGet blob metadata.
X86_SHA512 = "yK6TY6DllG1579KZyq4KQjbwzEaidL5Qj/HugPmyVajA8zqND6CZpIjlWlvAWY9dkAgQVP6/KZHyi97AB0hdpQ=="


def run(*args: str | Path, env=None) -> None:
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True, cwd=ROOT, env=env)


def python_x86() -> Path:
    target = STAGE / "toolchain/pythonx86-nuget"
    python = target / "tools/python.exe"
    if not python.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        archive = target.parent / "pythonx86-nuget.zip"
        print("Downloading the official Python 3.10.11 x86 build toolchain...", flush=True)
        with urllib.request.urlopen(X86_PACKAGE, timeout=120) as source, archive.open("wb") as output:
            while block := source.read(1024 * 1024):
                output.write(block)
        digest = hashlib.sha512(archive.read_bytes()).digest()
        if base64.b64encode(digest).decode() != X86_SHA512:
            raise RuntimeError("Python x86 package checksum mismatch")
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(target)
    return python


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-x64", type=Path, default=Path(sys.executable))
    parser.add_argument("--python-x86", type=Path)
    parser.add_argument("--makensis", type=Path)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Build this installer on Windows.")
    interpreters = {"x64": args.python_x64, "x86": args.python_x86 or python_x86()}
    for arch, python in interpreters.items():
        expected = "64" if arch == "x64" else "32"
        bits = subprocess.check_output([str(python), "-c", "import struct; print(struct.calcsize('P') * 8)"], text=True).strip()
        if bits != expected:
            parser.error(f"{python} is {bits}-bit; {arch} requires {expected}-bit Python.")
        environment = STAGE / f"venv-{arch}"
        if not (environment / "Scripts/python.exe").is_file():
            run(python, "-m", "venv", environment)
        python = environment / "Scripts/python.exe"
        requirements = "requirements-build.txt" if arch == "x64" else "requirements-build-x86.txt"
        run(python, "-m", "pip", "install", "-r", ROOT / "installer" / requirements)
        run(python, "-m", "unittest", "discover", "-s", "tests", "-v",
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        run(python, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", f"dist/{arch}",
            "--workpath", f"build/{arch}", "ImageFlow.spec")
    command = [sys.executable, str(ROOT / "installer/build_installer.py")]
    if args.makensis:
        command.extend(["--makensis", str(args.makensis)])
    run(*command)


if __name__ == "__main__":
    main()
