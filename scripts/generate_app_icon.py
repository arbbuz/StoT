from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SOURCE_PATH = ASSETS / "app_icon_source.jpg"
PNG_PATH = ASSETS / "app_icon.png"
ICO_PATH = ASSETS / "app_icon.ico"


def make_icon(size: int = 1024) -> Image.Image:
    source = Image.open(SOURCE_PATH).convert("RGBA")
    side = min(source.size)
    left = (source.width - side) // 2
    top = (source.height - side) // 2
    source = source.crop((left, top, left + side, top + side))
    return source.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(f"Icon source not found: {SOURCE_PATH}")

    ASSETS.mkdir(exist_ok=True)
    icon = make_icon()
    icon.save(PNG_PATH)
    icon.save(
        ICO_PATH,
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )
    print(f"Wrote {PNG_PATH}")
    print(f"Wrote {ICO_PATH}")


if __name__ == "__main__":
    main()
