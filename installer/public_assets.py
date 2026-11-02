"""Allow only reviewed application assets into public installers."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path


RESOURCE_FILES = (
    "imageflow-logo.ico", "imageflow-logo.png", "install_update.ps1",
    "install_delta.ps1", "remove_updated_files.ps1",
    "photo-next.svg", "photo-previous.svg", "spin-arrow-down.svg",
    "spin-arrow-up.svg", "trash.svg", "styles/imageflow_dark_orange.qss",
    "styles/imageflow_glass_dark.qss",
)


def check_catalog(path: Path) -> None:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if rows != [["Product", "Colors"]]:
        raise ValueError("Public products.csv must contain only the Product,Colors header.")


def release_datas(root: Path) -> list[tuple[str, str]]:
    check_catalog(root / "products.csv")
    datas = [(str(root / "products.csv"), ".")]
    for name in RESOURCE_FILES:
        path = root / "resources" / name
        if not path.is_file():
            raise ValueError(f"Missing public resource: {name}")
        datas.append((str(path), (Path("resources") / name).parent.as_posix()))
    return datas


def check_payload(root: Path, payload: Path) -> None:
    internal = payload / "_internal"
    check_catalog(internal / "products.csv")
    resource_root = internal / "resources"
    actual = {p.relative_to(resource_root).as_posix() for p in resource_root.rglob("*") if p.is_file()}
    if actual != set(RESOURCE_FILES):
        raise ValueError("Frozen resources do not match the public asset allowlist.")
    for name in RESOURCE_FILES:
        source = (root / "resources" / name).read_bytes()
        frozen = (resource_root / name).read_bytes()
        if hashlib.sha256(source).digest() != hashlib.sha256(frozen).digest():
            raise ValueError(f"Frozen resource is outdated: {name}")
    for path in payload.rglob("*"):
        if path.is_file() and (path.name.lower() == "presets.json" or path.suffix.lower() in {".imageflowproject", ".key", ".pem"}):
            raise ValueError(f"Private data must not be packaged: {path.name}")
