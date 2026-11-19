"""Fonts and generated text images.

Built-in font names (both SIL Open Font License, downloaded from Google Fonts on first use
into ~/.cache/moodface/fonts; no font files ship with moodface):
  rounded   Nunito — digits and Latin text
  sans      Noto Sans TC — Traditional Chinese
Any other value is treated as a path to a .ttf/.otf file.
"""
from __future__ import annotations

import math
import sys
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageColor, ImageDraw, ImageFont

from .compiler import home

GOOGLE_FONTS = "https://github.com/google/fonts/raw/main/ofl"
# name -> (cache file, font URL, license URL, approx size)
DOWNLOADS = {
    "rounded": ("Nunito.ttf", f"{GOOGLE_FONTS}/nunito/Nunito%5Bwght%5D.ttf", f"{GOOGLE_FONTS}/nunito/OFL.txt", "0.3 MB"),
    "sans": ("NotoSansTC.ttf", f"{GOOGLE_FONTS}/notosanstc/NotoSansTC%5Bwght%5D.ttf", f"{GOOGLE_FONTS}/notosanstc/OFL.txt", "12 MB"),
}
ALIASES = {"nunito": "rounded", "tc": "sans", "noto-sans-tc": "sans", "cjk": "sans"}


def download_font(key: str, quiet: bool = False) -> Path:
    """Fetch an OFL font from Google Fonts into the moodface cache (once). Fonts are not bundled."""
    fname, url, lic, size = DOWNLOADS[key]
    dest = home() / "fonts" / fname
    if dest.is_file():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not quiet:
        print(f"downloading {fname} (SIL Open Font License, ~{size}) ...", file=sys.stderr)
    for src, target in ((url, dest), (lic, dest.with_name(dest.stem + "-OFL.txt"))):
        with urllib.request.urlopen(src, timeout=300) as r:
            data = r.read()
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(target)
    return dest


def download_cjk_font(quiet: bool = False) -> Path:
    return download_font("sans", quiet)


def font_path(name: str) -> Path:
    key = ALIASES.get(str(name).lower(), str(name).lower())
    if key in DOWNLOADS:
        return download_font(key)
    p = Path(name).expanduser()
    if not p.is_file():
        raise ValueError(f"font '{name}' not found (use rounded, sans or a font file path)")
    return p


@lru_cache(maxsize=256)
def get_font(name: str, size: int, weight: Optional[int] = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(font_path(name)), max(4, int(size)))
    if weight:
        try:
            f.set_variation_by_axes([int(weight)])
        except (OSError, ValueError):
            pass
    return f


def rgba(color) -> Tuple[int, int, int, int]:
    c = ImageColor.getrgb(str(color))
    return c if len(c) == 4 else c + (255,)


def text_size(text: str, font: str, size: int, weight: Optional[int] = None, stroke: int = 0) -> Tuple[int, int]:
    f = get_font(font, size, weight)
    asc, desc = f.getmetrics()
    return math.ceil(f.getlength(text)) + 2 + 2 * stroke, asc + desc + 2 * stroke


def text_image(text: str, font: str, size: int, color="#FFFFFF", weight: Optional[int] = None,
               stroke: int = 0, stroke_color="#00000099") -> Image.Image:
    """Text on a transparent image, tight horizontally, full line height vertically.
    `stroke` draws an outline (in px) so text stays readable on busy pictures."""
    f = get_font(font, size, weight)
    w, h = text_size(text, font, size, weight, stroke)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((1 + stroke, stroke), text, font=f, fill=rgba(color),
                            stroke_width=stroke, stroke_fill=rgba(stroke_color) if stroke else None)
    return im


def pad_to(images: Sequence[Image.Image], align: str = "center", size: Optional[Tuple[int, int]] = None) -> List[Image.Image]:
    """Pad images onto equal-size transparent canvases (lists need one size)."""
    w = size[0] if size else max(i.width for i in images)
    h = size[1] if size else max(i.height for i in images)
    out = []
    for im in images:
        c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        x = {"left": 0, "center": (w - im.width) // 2, "right": w - im.width}[align]
        c.paste(im, (x, (h - im.height) // 2))
        out.append(c)
    return out


def digit_images(font: str, size: int, color="#FFFFFF", weight: Optional[int] = None,
                 stroke: int = 0, stroke_color="#00000099") -> List[Image.Image]:
    """0-9 rendered into equal cells so numbers line up."""
    return pad_to([text_image(str(n), font, size, color, weight, stroke, stroke_color) for n in range(10)])


def digit_cell(font: str, size: int, weight: Optional[int] = None, stroke: int = 0) -> Tuple[int, int]:
    sizes = [text_size(str(n), font, size, weight, stroke) for n in range(10)]
    return max(s[0] for s in sizes), max(s[1] for s in sizes)


def badge(im: Image.Image, bg, pad_x: int, pad_y: int, radius: Optional[int] = None, outline=None,
          outline_width: int = 0) -> Image.Image:
    """Put a (rounded) background behind a text image, e.g. a weekday tag."""
    w, h = im.width + 2 * pad_x, im.height + 2 * pad_y
    r = h // 2 if radius is None else radius
    big = Image.new("RGBA", (w * 4, h * 4), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle([0, 0, w * 4 - 1, h * 4 - 1], radius=r * 4, fill=rgba(bg),
                                          outline=rgba(outline) if outline else None, width=outline_width * 4)
    out = big.resize((w, h), Image.LANCZOS)
    out.alpha_composite(im, (pad_x, pad_y))
    return out
