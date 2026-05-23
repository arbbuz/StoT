from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

SOURCE_ICO_PATH = ASSETS / "app_icon_source.ico"
SOURCE_PNG_PATH = ASSETS / "app_icon_source.png"
PNG_PATH = ASSETS / "app_icon.png"
ICO_PATH = ASSETS / "app_icon.ico"

EXPECTED_PNGS = {
    16: ASSETS / "app_icon_16x16.png",
    24: ASSETS / "app_icon_24x24.png",
    32: ASSETS / "app_icon_32x32.png",
    48: ASSETS / "app_icon_48x48.png",
    256: SOURCE_PNG_PATH,
}
EXPECTED_ICO_SIZES = {(16, 16), (24, 24), (32, 32), (48, 48), (256, 256)}


def verify_png_size(path: Path, size: int) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Icon PNG is missing: {path}")

    with Image.open(path) as image:
        if image.size != (size, size):
            raise ValueError(f"Icon PNG has size {image.size}, expected {(size, size)}: {path}")


def verify_source_ico() -> None:
    if not SOURCE_ICO_PATH.exists():
        raise FileNotFoundError(f"Icon ICO is missing: {SOURCE_ICO_PATH}")

    with Image.open(SOURCE_ICO_PATH) as image:
        sizes = image.ico.sizes()
        missing = EXPECTED_ICO_SIZES - sizes
        if missing:
            raise ValueError(f"Icon ICO is missing sizes: {sorted(missing)}")


def main() -> None:
    ASSETS.mkdir(exist_ok=True)

    for size, path in EXPECTED_PNGS.items():
        verify_png_size(path, size)
    verify_source_ico()

    shutil.copyfile(SOURCE_PNG_PATH, PNG_PATH)
    shutil.copyfile(SOURCE_ICO_PATH, ICO_PATH)
    print(f"Wrote {PNG_PATH}")
    print(f"Wrote {ICO_PATH}")


if __name__ == "__main__":
    main()
