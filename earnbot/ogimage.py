"""1200x630 social-share / cover images (Open Graph) rendered with Pillow."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
_BOLD = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
_REGULAR = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]


@lru_cache(maxsize=None)
def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    for path in _BOLD if bold else _REGULAR:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


@lru_cache(maxsize=1)
def _background() -> Image.Image:
    # Diagonal indigo -> violet -> cyan gradient matching the site's --grad.
    stops = [(0.0, (79, 70, 229)), (0.45, (124, 58, 237)), (1.0, (6, 182, 212))]
    small = Image.new("RGB", (120, 63))
    px = small.load()
    for y in range(63):
        for x in range(120):
            t = (x / 119 * 0.7 + y / 62 * 0.3)
            for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
                if t <= t1:
                    k = (t - t0) / (t1 - t0)
                    px[x, y] = tuple(int(a + (b - a) * k) for a, b in zip(c0, c1))
                    break
    return small.resize((W, H), Image.BICUBIC)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    return lines + ([line] if line else [])


def render(path: Path, title: str, kicker: str, brand: str) -> None:
    img = _background().copy()
    draw = ImageDraw.Draw(img)
    pad = 80
    # Shrink the title until it fits in at most 4 lines.
    for size in (72, 64, 56, 50, 44):
        font = _font(True, size)
        lines = _wrap(draw, title, font, W - 2 * pad)
        if len(lines) <= 4:
            break
    lines = lines[:4]
    if kicker:
        draw.text((pad, 80), kicker.upper()[:60], font=_font(True, 26), fill=(255, 255, 255, 220))
    y = (H - len(lines) * int(size * 1.18)) // 2 + 10
    for ln in lines:
        draw.text((pad, y), ln, font=font, fill="white")
        y += int(size * 1.18)
    # Mountain-peak brand mark ("ascent").
    x, y = pad, H - 112
    draw.polygon([(x, y + 38), (x + 14, y + 14), (x + 20, y + 24), (x + 28, y + 4), (x + 40, y + 38)], fill="white")
    draw.text((pad + 52, H - 108), brand, font=_font(True, 30), fill="white")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
