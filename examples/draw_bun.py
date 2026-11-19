#!/usr/bin/env python3
"""Draw your own character for moodface — a complete example: the stress bun.

This script draws a steamed bun in a bamboo steamer in four moods (calm, normal,
medium, high stress), saves them as PNGs and writes a face.yaml that uses the
`classic` layout. moodface does the rest: layout, digits, captions, preview, build.

    python examples/draw_bun.py my_bun          # writes my_bun/face.yaml + my_bun/assets/
    moodface preview my_bun                     # GIFs for every stress level + a simulated day
    moodface build my_bun                       # → my_bun/build/my_bun.bin

Only Pillow is needed. Swap `draw_bun` for your own drawing code to make another character.
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 184          # output size of each character image (px)
SS = 4              # draw 4x larger, then downscale for smooth edges
INK = (52, 34, 28, 255)

MOODS = {           # stress level -> (bun color, face)
    "calm": ((255, 249, 238), "calm"),
    "normal": ((255, 244, 228), "normal"),
    "medium": ((255, 232, 212), "worried"),
    "high": ((255, 212, 196), "panic"),
}
CAPTIONS = {
    "calm": "熱呼呼，好放鬆～",
    "normal": "剛出爐，狀態不錯！",
    "medium": "蒸氣有點多，深呼吸",
    "high": "快蒸爆了，休息一下",
}


def draw_face(d, o, cx, cy, u, mood, lw):
    """Eyes, mouth and blush. `d` draws solid shapes, `o` translucent ones."""
    ex, er = u * 0.36, u * 0.075
    for s in (-1, 1):  # blush
        bx = cx + s * u * 0.58
        o.ellipse([bx - u * 0.14, cy + u * 0.16, bx + u * 0.14, cy + u * 0.28], fill=(255, 140, 140, 140))

    def dot_eyes():
        for s in (-1, 1):
            x = cx + s * ex
            d.ellipse([x - er, cy - er * 1.3, x + er, cy + er * 1.3], fill=INK)
            d.ellipse([x - er * 0.2, cy - er * 0.9, x + er * 0.45, cy - er * 0.25], fill=(255, 255, 255, 255))

    if mood == "calm":  # closed eyes, smile
        for s in (-1, 1):
            x = cx + s * ex
            d.arc([x - er * 1.6, cy - er * 1.2, x + er * 1.6, cy + er * 1.6], 200, 340, fill=INK, width=lw)
        d.arc([cx - u * 0.16, cy + u * 0.10, cx + u * 0.16, cy + u * 0.32], 20, 160, fill=INK, width=lw)
    elif mood == "normal":
        dot_eyes()
        d.arc([cx - u * 0.13, cy + u * 0.08, cx + u * 0.13, cy + u * 0.28], 20, 160, fill=INK, width=lw)
    elif mood == "worried":  # raised brows, small o mouth
        dot_eyes()
        for s in (-1, 1):
            x = cx + s * ex
            d.line([x - s * er * 0.2, cy - er * 3.4, x + s * er * 1.9, cy - er * 2.4], fill=INK, width=lw)
        m = u * 0.08
        d.ellipse([cx - m, cy + u * 0.16, cx + m, cy + u * 0.16 + m * 1.6], fill=INK)
    else:  # panic: > < eyes, wavy mouth
        for s in (-1, 1):
            x, k = cx + s * ex, er * 1.4
            d.line([(x - s * k, cy - k), (x + s * k * 0.6, cy), (x - s * k, cy + k)], fill=INK, width=lw, joint="curve")
        pts = [(cx - u * 0.22 + u * 0.44 * i / 8, cy + u * 0.26 + u * 0.05 * (1 if i % 2 else -1)) for i in range(9)]
        d.line(pts, fill=INK, width=lw, joint="curve")


def steam(o, x0, y0, length, amp, width, alpha):
    """A wavy, fading line of steam rising from (x0, y0)."""
    pts = [(x0 + amp * math.sin(i / 20 * math.pi * 3), y0 - length * i / 20) for i in range(21)]
    for i in range(20):
        o.line([pts[i], pts[i + 1]], fill=(255, 255, 255, int(alpha * (1 - i / 20))), width=width)


def draw_bun(level: str) -> Image.Image:
    S = SIZE * SS
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ov = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d, o = ImageDraw.Draw(im), ImageDraw.Draw(ov)
    lw = int(S * 0.022)
    color, mood = MOODS[level]
    bamboo, bamboo_dark = (196, 150, 92, 255), (150, 108, 62, 255)

    cx, bw, bh, bcy = S * 0.5, S * 0.34, S * 0.25, S * 0.58
    top, rim = bcy - bh, S * 0.74

    d.ellipse([cx - S * 0.42, rim - S * 0.06, cx + S * 0.42, rim + S * 0.06], fill=bamboo_dark)       # steamer back
    d.ellipse([cx - bw, top, cx + bw, bcy + bh * 0.85], fill=color + (255,))                        # bun
    for ang in (-60, -30, 0, 30, 60):                                                               # pleats
        a = math.radians(ang)
        d.line([cx, top + S * 0.03, cx + math.sin(a) * S * 0.1, top + S * 0.03 + math.cos(a) * S * 0.05],
               fill=(222, 200, 176, 255), width=max(2, lw // 2))
    o.ellipse([cx - bw * 0.7, top + bh * 0.35, cx - bw * 0.35, top + bh * 0.6], fill=(255, 255, 255, 150))  # shine
    draw_face(d, o, cx, bcy + bh * 0.05, bw * 0.95, mood, lw)

    d.chord([cx - S * 0.42, rim - S * 0.06, cx + S * 0.42, rim + S * 0.06], 0, 180, fill=bamboo)    # steamer front
    d.rounded_rectangle([cx - S * 0.42, rim, cx + S * 0.42, S * 0.9], radius=S * 0.03, fill=bamboo)
    for i in range(1, 8):
        x = cx - S * 0.42 + S * 0.84 * i / 8
        d.line([x, rim + S * 0.02, x, S * 0.88], fill=bamboo_dark, width=max(2, lw // 2))

    n, length, alpha = {"calm": (2, 0.13, 150), "normal": (3, 0.16, 180), "medium": (4, 0.2, 220), "high": (5, 0.24, 255)}[level]
    for i in range(n):                                                                              # more stress, more steam
        steam(o, cx + (i - (n - 1) / 2) * S * 0.09, top - S * 0.01, S * length, S * 0.018, lw, alpha)

    im.alpha_composite(ov)
    return im.resize((SIZE, SIZE), Image.LANCZOS)


FACE_YAML = """\
name: {name}
title: Stress Bun
device: band9                 # see `moodface devices`; also works for watches
background: "#161210"
layout: classic               # see `moodface layouts`
style: {{accent: "#F0A060", muted: "#9A8F88"}}
slots:
  character:
    source: stress_level      # calm 0-39, normal 40-59, medium 60-79, high 80-100
    images: {{calm: assets/calm.png, normal: assets/normal.png, medium: assets/medium.png, high: assets/high.png}}
  caption:
    texts: {{calm: {calm}, normal: {normal}, medium: {medium}, high: {high}}}
  bar: {{}}
  stats: [stress, steps, heart_rate]
"""


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "my_bun")
    (out / "assets").mkdir(parents=True, exist_ok=True)
    for level in MOODS:
        draw_bun(level).save(out / "assets" / f"{level}.png")
    name = "".join(c if c.isalnum() or c in "_-" else "_" for c in out.name) or "my_bun"
    (out / "face.yaml").write_text(FACE_YAML.format(name=name, **CAPTIONS), encoding="utf-8")
    print(f"wrote {out}/face.yaml and 4 images")
    print(f"next: moodface preview {out}   |   moodface build {out}")


if __name__ == "__main__":
    main()
