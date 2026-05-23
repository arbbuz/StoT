from __future__ import annotations

from collections import deque
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
DARK_CORNER_THRESHOLD = 12


def is_corner_background(pixel: tuple[int, int, int, int]) -> bool:
    red, green, blue, alpha = pixel
    return alpha == 0 or (
        alpha > 0
        and red <= DARK_CORNER_THRESHOLD
        and green <= DARK_CORNER_THRESHOLD
        and blue <= DARK_CORNER_THRESHOLD
    )


def clear_connected_corner_background(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA").copy()
    pixels = image.load()
    width, height = image.size
    queue: deque[tuple[int, int]] = deque()
    seen: set[tuple[int, int]] = set()

    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))

    while queue:
        x, y = queue.popleft()
        if (x, y) in seen:
            continue
        seen.add((x, y))

        if not is_corner_background(pixels[x, y]):
            continue

        pixels[x, y] = (0, 0, 0, 0)
        if x > 0:
            queue.append((x - 1, y))
        if x + 1 < width:
            queue.append((x + 1, y))
        if y > 0:
            queue.append((x, y - 1))
        if y + 1 < height:
            queue.append((x, y + 1))

    return image


def load_icon_png(path: Path, size: int) -> Image.Image:
    if not path.exists():
        raise FileNotFoundError(f"Icon PNG is missing: {path}")

    with Image.open(path) as image:
        if image.size != (size, size):
            raise ValueError(f"Icon PNG has size {image.size}, expected {(size, size)}: {path}")
        return clear_connected_corner_background(image)


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

    icon_images = {size: load_icon_png(path, size) for size, path in EXPECTED_PNGS.items()}
    verify_source_ico()

    icon_images[256].save(PNG_PATH)
    icon_images[256].save(
        SOURCE_ICO_PATH,
        append_images=[icon_images[16], icon_images[24], icon_images[32], icon_images[48]],
        sizes=sorted(EXPECTED_ICO_SIZES),
    )
    icon_images[256].save(
        ICO_PATH,
        append_images=[icon_images[16], icon_images[24], icon_images[32], icon_images[48]],
        sizes=sorted(EXPECTED_ICO_SIZES),
    )
    print(f"Wrote {PNG_PATH}")
    print(f"Wrote {ICO_PATH}")


if __name__ == "__main__":
    main()
