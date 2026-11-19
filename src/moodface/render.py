"""Simulate a face on screen: single frames, per-stress-level GIFs and a full-day GIF."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageColor, ImageDraw

from .sources import SOURCES
from .spec import Face, Widget

DEFAULT_VALUES: Dict[str, int] = {
    "hour": 13, "minute": 35, "second": 0, "day": 18, "week": 3, "month": 11, "year": 2026, "ampm": 1,
    "weather": 1, "temp_c": 24, "temp_f": 75, "battery": 80, "sleep_mode": 0, "bluetooth": 1, "screen_lock": 0,
    "heart_rate": 78, "hr_zone": 1, "steps": 2560, "steps_percent": 32, "steps_km": 2, "calories": 120,
    "calories_percent": 40, "stand": 4, "stress": 48, "sleep_score": 82,
}
STRESS_SAMPLES = [22, 48, 67, 88]


def source_value(source_id: str, values: Dict[str, int]) -> int:
    for name, (sid, _) in SOURCES.items():
        if sid != source_id:
            continue
        for base in ("hour", "minute", "second", "day"):
            if name == f"{base}_low":
                return values.get(base, 0) % 10
            if name == f"{base}_high":
                return values.get(base, 0) // 10
        return int(values.get(name, 0))
    return 0


def pick_index(w: Widget, value: int) -> str:
    """Image list: the image of the largest threshold <= value (first image below all thresholds)."""
    chosen = w.images[0][1]
    for threshold, path in w.images:
        if value >= threshold:
            chosen = path
    return chosen


def _draw_number(face: Face, canvas: Image.Image, w: Widget, value: int) -> None:
    digits = [face.image(p) for _, p in w.images]
    dw, dh = digits[0].size
    s = str(max(0, int(value)))
    if w.zero_pad:
        s = s.zfill(w.digits)
    s = s[-w.digits:]
    box_w = w.digits * dw + (w.digits - 1) * w.spacing
    text_w = len(s) * dw + (len(s) - 1) * w.spacing
    x = w.x + {"left": 0, "center": (box_w - text_w) // 2, "right": box_w - text_w}[w.align]
    for ch in s:
        canvas.alpha_composite(digits[int(ch)], (x, w.y))
        x += dw + w.spacing


def _paste(canvas: Image.Image, im: Image.Image, x: int, y: int, alpha: int) -> None:
    if alpha < 255:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda a: a * alpha // 255))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(im, (x, y))
    canvas.alpha_composite(layer)


def render_frame(face: Face, values: Optional[Dict[str, int]] = None, frame: int = 0, mask: bool = True) -> Image.Image:
    vals = dict(DEFAULT_VALUES, **(values or {}))
    dev = face.device
    canvas = Image.new("RGBA", (dev.width, dev.height), ImageColor.getrgb(face.background) + (255,))
    for w in face.widgets:
        if w.type == "number":
            _draw_number(face, canvas, w, source_value(w.source, vals))
            continue
        if w.type in ("image", "text"):
            path = w.images[0][1]
        elif w.type == "animation":
            path = w.images[frame % len(w.images)][1]
        else:
            path = pick_index(w, source_value(w.source, vals))
        _paste(canvas, face.image(path), w.x, w.y, w.alpha)
    if mask:
        canvas = apply_screen_mask(canvas, dev.radius)
    return canvas


def apply_screen_mask(im: Image.Image, radius: int) -> Image.Image:
    w, h = im.size
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=min(radius, w // 2), fill=255)
    out = Image.new("RGBA", im.size, (0, 0, 0, 255))
    out.paste(im, (0, 0), m)
    return out


def animation_frames(face: Face) -> int:
    counts = [len(w.images) for w in face.widgets if w.type == "animation"]
    if not counts:
        return 1
    n = 1
    for c in counts:
        n = n * c // math.gcd(n, c)
    return min(n, 60)


def frame_interval(face: Face) -> int:
    anim = [w.interval_ms for w in face.widgets if w.type == "animation"]
    return anim[0] if anim else 500


VARY_ORDER = ["stress", "hour", "month", "week", "battery", "heart_rate", "day"]
FALLBACK_SAMPLES = {"stress": STRESS_SAMPLES, "hour": [2, 6, 10, 14, 18, 22], "month": [1, 4, 7, 10],
                    "week": list(range(7)), "battery": [10, 40, 80], "heart_rate": [60, 85, 120, 150]}


def varying_sources(face: Face) -> List[str]:
    # skip lists that only swap generated text (e.g. the weekday in a date) — not worth a preview series
    names = {w.source_name for w in face.widgets if w.type in ("imagelist", "bar")
             and not all(k.startswith("_gen/") and "/text_" in k for _, k in w.images)}
    return sorted(names, key=lambda n: (VARY_ORDER.index(n) if n in VARY_ORDER else 99, n))


def samples_for(face: Face, source: str) -> List[int]:
    """One value inside each band the face switches on for this source."""
    from .rules import domain
    lists = [w for w in face.widgets if w.type == "imagelist" and w.source_name == source]
    ths = sorted({t for w in lists for t, _ in w.images})
    if not ths:
        return FALLBACK_SAMPLES.get(source, [0, 50, 100])
    hi = domain(source)[1]
    bounds = ths + [hi + 1]
    return [min(hi, (bounds[i] + bounds[i + 1] - 1) // 2) for i in range(len(ths))]


def stress_samples(face: Face) -> List[int]:
    return samples_for(face, "stress")


def day_curve():
    """Simulated stress from 08:00 to 23:00, every 30 minutes."""
    for i in range(31):
        hour = 8 + i / 2
        v = int(30 + 25 * math.sin((hour - 8) / 15 * math.pi * 2.2) + 20 * math.exp(-((hour - 15) ** 2) / 3))
        yield i, hour, max(5, min(99, v))


def save_gif(frames: List[Image.Image], path: Path, ms: int) -> None:
    rgb = [f.convert("RGB") for f in frames]
    rgb[0].save(path, save_all=True, append_images=rgb[1:], duration=ms, loop=0, optimize=True)


def _sheet(face: Face, renders: List[Image.Image]) -> Image.Image:
    W, H = face.device.width, face.device.height
    gap = 16
    sheet = Image.new("RGB", (len(renders) * (W + gap) + gap, H + 2 * gap), (40, 40, 44))
    for i, im in enumerate(renders):
        sheet.paste(im.convert("RGB"), (gap + i * (W + gap), gap))
    return sheet


def write_previews(face: Face, out: Path, vary: Optional[List[str]] = None) -> List[Path]:
    """Per-value GIFs and an overview sheet for each varying source, plus a simulated day."""
    out.mkdir(parents=True, exist_ok=True)
    written = []
    n, ms = animation_frames(face), frame_interval(face)
    sources = vary or varying_sources(face) or ["stress"]

    for idx, src in enumerate(sources):
        values = samples_for(face, src)
        for v in values:
            p = out / f"{src}_{v:02d}.gif"
            save_gif([render_frame(face, {src: v}, f) for f in range(n)], p, ms)
            written.append(p)
        sheet = _sheet(face, [render_frame(face, {src: v}) for v in values])
        p = out / f"overview_{src}.png"
        sheet.save(p)
        written.append(p)
        if idx == 0:
            sheet.save(out / "overview.png")
            written.append(out / "overview.png")

    frames = []
    for i, hour, v in day_curve():
        vals = {"stress": v, "hour": int(hour), "minute": 30 if i % 2 else 0, "steps": 300 + i * 280,
                "heart_rate": 70 + v // 5, "battery": 95 - i}
        for f in range(max(2, min(n, 6))):
            frames.append(render_frame(face, vals, f))
    p = out / "day.gif"
    save_gif(frames, p, max(60, ms))
    written.append(p)

    if "month" in sources:
        p = out / "year.gif"
        save_gif([render_frame(face, {"month": m, "day": 15}) for m in range(1, 13)], p, 600)
        written.append(p)
    return written
