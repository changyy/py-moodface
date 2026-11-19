"""face.yaml: the declarative face spec.

A face is either a list of low-level `widgets`, a `layout` with `slots`, or both
(layout widgets first, then `widgets` on top). See README for the full reference.

Low-level widget types:
  image      one picture (or `text:` rendered with a font)
  imagelist  picture chosen by a data source; `images:` or `texts:` keyed by rules (see rules.py)
  number     a value drawn with digit images, or digits generated from `font:`
  animation  frames played in a loop
  text       static text rendered to an image
  bar        progress bar generated for a data source

Positions accept pixels or percentages of the screen ("50%"); `anchor` picks which point
of the widget sits at (x, y). `box: [x, y, w, h]` + `fit: contain | cover | stretch`
scales pictures into a frame of any device size.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from PIL import Image, ImageDraw

from . import fonts
from .devices import Device, get_device
from .rules import build_thresholds, resolve_source
from .sources import ID_TO_NAME

TYPES = ("image", "imagelist", "number", "animation", "text", "bar")
ALIGN = {"left": 0, "center": 1, "right": 2}
ANCHORS = {
    "top-left": (0, 0), "top": (0.5, 0), "top-right": (1, 0),
    "left": (0, 0.5), "center": (0.5, 0.5), "right": (1, 0.5),
    "bottom-left": (0, 1), "bottom": (0.5, 1), "bottom-right": (1, 1),
}
DEFAULT_STYLE = {"font": "rounded", "text_font": "sans", "color": "#FFFFFF", "muted": "#A0A0A0",
                 "accent": "#FFC860", "weight": 700, "stroke": 0, "stroke_color": "#00000099"}


class SpecError(ValueError):
    pass


@dataclass
class Widget:
    type: str
    name: str
    x: int
    y: int
    images: List[Tuple[int, str]]          # (index / threshold, image key)
    source: str = "0"                      # fprj source id
    digits: int = 1
    align: str = "left"
    spacing: int = 0
    zero_pad: bool = True
    default_index: int = 0
    interval_ms: int = 120
    repeat: int = 0                        # 0 = forever
    alpha: int = 255

    @property
    def fprj_type(self) -> str:
        return {"text": "image", "bar": "imagelist"}.get(self.type, self.type)

    @property
    def source_name(self) -> str:
        return ID_TO_NAME.get(self.source, self.source)


ID_LENGTHS = (9, 12)


def check_id(face_id) -> str:
    """Return `face_id` as a string, or raise SpecError unless it is 9-12 digits not starting with 0."""
    face_id = str(face_id)
    if not re.fullmatch(r"[1-9][0-9]{8,11}", face_id):
        raise SpecError(f"id must be 9-12 digits and not start with 0, got '{face_id}'")
    return face_id


def check_id_length(n) -> int:
    if str(n) not in ("9", "12"):
        raise SpecError(f"id_length must be 9 or 12, got '{n}'")
    return int(n)


def time_id(now=None) -> str:
    """12-digit id from the local build time, yyMMddHHmmss (e.g. 261119213045): a new id on every
    build, so a rebuilt face installs next to the old one instead of being refused as a duplicate."""
    return (now or datetime.now()).strftime("%y%m%d%H%M%S")


def resolve_id(value) -> str:
    """An explicit id: 9-12 digits, or the word `time` for time_id()."""
    return time_id() if str(value).strip().lower() == "time" else check_id(value)


def derive_id(name: str, length: int = 9) -> str:
    """Stable face id from the face name: SHA-256 of the UTF-8 name, as an integer,
    mapped onto [10^(length-1), 10^length) so the first digit is never 0."""
    length = check_id_length(length)
    n = int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest(), "big")
    low = 10 ** (length - 1)
    return str(low + n % (9 * low))


@dataclass
class Face:
    name: str
    title: str
    device: Device
    base: Path
    widgets: List[Widget]
    id: str = "167210065"
    background: str = "#000000"
    preview: Optional[str] = None
    style: Dict = field(default_factory=lambda: dict(DEFAULT_STYLE))
    generated: Dict[str, Image.Image] = field(default_factory=dict, repr=False)
    _cache: Dict[str, Image.Image] = field(default_factory=dict, repr=False)

    def path(self, rel: str) -> Path:
        return self.base / rel

    def exists(self, key: str) -> bool:
        return key in self.generated or self.path(key).is_file()

    def image(self, key: str) -> Image.Image:
        if key in self.generated:
            return self.generated[key]
        if key not in self._cache:
            with Image.open(self.path(key)) as im:
                self._cache[key] = im.convert("RGBA")
        return self._cache[key]

    def widget_size(self, w: Widget) -> Tuple[int, int]:
        sizes = [self.image(p).size for _, p in w.images]
        iw = max(s[0] for s in sizes)
        ih = max(s[1] for s in sizes)
        if w.type == "number":
            return w.digits * iw + (w.digits - 1) * w.spacing, ih
        return iw, ih


# ---------- helpers ----------

def length(v, total: int) -> int:
    """Pixels (int) or a percentage string of `total`."""
    if v is None:
        return 0
    if isinstance(v, str) and v.strip().endswith("%"):
        return round(float(v.strip()[:-1]) * total / 100)
    return int(round(float(v)))


def _expand(base: Path, value) -> List[str]:
    """A list of paths, a glob ('frames/*.png') or a single path."""
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    s = str(value)
    if any(ch in s for ch in "*?["):
        found = sorted(base.glob(s), key=lambda p: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.name)])
        return [str(p.relative_to(base)) for p in found]
    return [s]


class _Ctx:
    """Parsing context: device, style, base folder and generated images."""

    def __init__(self, face: Face):
        self.face = face
        self.dev = face.device

    def gen(self, key: str, im: Image.Image) -> str:
        self.face.generated[key] = im
        return key

    def text_style(self, raw: dict, default_font_key: str) -> dict:
        st = self.face.style
        size = raw.get("size", 16)
        return {"font": raw.get("font", st[default_font_key]),
                "size": length(size, self.dev.height) if isinstance(size, str) else int(size),
                "color": raw.get("color", st["color"]), "weight": raw.get("weight", st.get("weight")),
                "stroke": int(raw.get("stroke", st.get("stroke", 0))),
                "stroke_color": raw.get("stroke_color", st.get("stroke_color", "#00000099"))}

    def badge(self, raw: dict, ims: List[Image.Image]) -> List[Image.Image]:
        """Optional `bg` behind text images (`pad`, `radius`, `outline`, `outline_width`)."""
        if not raw.get("bg"):
            return ims
        h = ims[0].height
        pad = raw.get("pad", [max(2, h // 3), max(1, h // 10)])
        px, py = (pad, pad) if isinstance(pad, (int, float)) else pad
        return [fonts.badge(im, raw["bg"], int(px), int(py), raw.get("radius"), raw.get("outline"),
                            int(raw.get("outline_width", 1 if raw.get("outline") else 0))) for im in ims]

    def fit(self, wname: str, keys: List[str], box: Tuple[int, int, int, int], mode: str) -> List[str]:
        """Scale pictures into the box; every output is exactly box-sized."""
        _, _, bw, bh = box
        out = []
        for i, k in enumerate(keys):
            if not self.face.exists(k):
                out.append(k)
                continue
            im = self.face.image(k)
            if mode == "stretch":
                res = im.resize((bw, bh), Image.LANCZOS)
            else:
                scale = (max if mode == "cover" else min)(bw / im.width, bh / im.height)
                sw, sh = max(1, round(im.width * scale)), max(1, round(im.height * scale))
                scaled = im.resize((sw, sh), Image.LANCZOS)
                res = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
                res.paste(scaled, ((bw - sw) // 2, (bh - sh) // 2))
            out.append(self.gen(f"_gen/{wname}/fit_{i}.png", res))
        return out


def _blank_like(ctx: _Ctx, wname: str, keys: List[Optional[str]], fallback=(1, 1)) -> List[str]:
    """Replace None (gap) entries with a transparent image of the list's size."""
    real = [k for k in keys if k is not None and ctx.face.exists(k)]
    size = ctx.face.image(real[0]).size if real else fallback
    blank = None
    out = []
    for k in keys:
        if k is None:
            blank = blank or ctx.gen(f"_gen/{wname}/blank.png", Image.new("RGBA", size, (0, 0, 0, 0)))
            out.append(blank)
        else:
            out.append(k)
    return out


def _bar_images(ctx: _Ctx, wname: str, raw: dict, steps: int) -> List[str]:
    st = ctx.face.style
    w = length(raw.get("w", 100), ctx.dev.width)
    h = length(raw.get("h", 6), ctx.dev.height)
    color = fonts.rgba(raw.get("color", st["accent"]))
    track = fonts.rgba(raw.get("track", "#FFFFFF33"))
    r = (min(w, h) // 2 if raw.get("radius") is None else length(raw["radius"], ctx.dev.width)) if raw.get("rounded", True) else 0
    keys = []
    for i in range(steps + 1):
        im = Image.new("RGBA", (w * 4, h * 4), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, w * 4 - 1, h * 4 - 1], radius=r * 4, fill=track)
        if raw.get("direction", "right") == "up":
            fh = round((h * 4) * i / steps)
            if fh > 0:
                d.rounded_rectangle([0, h * 4 - max(fh, r * 8), w * 4 - 1, h * 4 - 1], radius=r * 4, fill=color)
        else:
            fw = round((w * 4) * i / steps)
            if fw > 0:
                d.rounded_rectangle([0, 0, max(fw, r * 8) - 1, h * 4 - 1], radius=r * 4, fill=color)
        keys.append(ctx.gen(f"_gen/{wname}/bar_{i}.png", im.resize((w, h), Image.LANCZOS)))
    return keys


def _parse_widget(ctx: _Ctx, i: int, raw: dict) -> Widget:
    face, dev = ctx.face, ctx.dev
    t = raw.get("type")
    if t not in TYPES:
        raise SpecError(f"widget #{i}: type must be one of {', '.join(TYPES)}, got {t!r}")
    name = str(raw.get("name") or f"{t}_{i}")
    kw = dict(type=t, name=name, x=length(raw.get("x", 0), dev.width), y=length(raw.get("y", 0), dev.height),
              alpha=int(raw.get("alpha", 255)))
    rule = None
    try:
        if "source" in raw:
            kw["source"], rule = resolve_source(raw["source"])
    except ValueError as e:
        raise SpecError(f"widget '{name}': {e}") from None

    keys: List[str]
    if t == "image":
        if "text" in raw:
            st = ctx.text_style(raw, "text_font")
            im = fonts.text_image(str(raw["text"]), st["font"], st["size"], st["color"], st["weight"], st["stroke"], st["stroke_color"])
            keys = [ctx.gen(f"_gen/{name}/text.png", ctx.badge(raw, [im])[0])]
        elif "fill" in raw:  # solid (rounded) rectangle, e.g. a translucent panel
            pw, ph = length(raw.get("w", 0), dev.width), length(raw.get("h", 0), dev.height)
            if pw <= 0 or ph <= 0:
                raise SpecError(f"widget '{name}': a fill needs w and h")
            r = length(raw.get("radius", 0), dev.width)
            im = Image.new("RGBA", (pw * 4, ph * 4), (0, 0, 0, 0))
            ow = int(raw.get("outline_width", 2 if raw.get("outline") else 0))
            ImageDraw.Draw(im).rounded_rectangle([0, 0, pw * 4 - 1, ph * 4 - 1], radius=r * 4, fill=fonts.rgba(raw["fill"]),
                                                 outline=fonts.rgba(raw["outline"]) if raw.get("outline") else None,
                                                 width=ow * 4)
            keys = [ctx.gen(f"_gen/{name}/fill.png", im.resize((pw, ph), Image.LANCZOS))]
        elif "image" in raw:
            keys = [str(raw["image"])]
        else:
            raise SpecError(f"widget '{name}': 'image', 'text' or 'fill' is required")
        kw["images"] = [(0, keys[0])]
    elif t == "text":
        st = ctx.text_style(raw, "text_font")
        if "text" not in raw:
            raise SpecError(f"widget '{name}': 'text' is required")
        im = fonts.text_image(str(raw["text"]), st["font"], st["size"], st["color"], st["weight"], st["stroke"], st["stroke_color"])
        keys = [ctx.gen(f"_gen/{name}/text.png", ctx.badge(raw, [im])[0])]
        kw["images"] = [(0, keys[0])]
    elif t in ("imagelist", "bar"):
        if kw.get("source", "0") == "0":
            raise SpecError(f"widget '{name}': {t} needs a 'source'")
        if t == "bar":
            steps = int(raw.get("steps", 10))
            vmax = int(raw.get("max", 100))
            bars = _bar_images(ctx, name, raw, steps)
            pairs = [(round(vmax * j / steps), b) for j, b in enumerate(bars)]
        else:
            if "texts" in raw:
                st = ctx.text_style(raw, "text_font")
                mapping = dict(raw["texts"])
                rendered = fonts.pad_to([fonts.text_image(str(v), st["font"], st["size"], st["color"], st["weight"], st["stroke"], st["stroke_color"])
                                         for v in mapping.values()], raw.get("text_align", "center"))
                rendered = ctx.badge(raw, rendered)
                mapping = {k: ctx.gen(f"_gen/{name}/text_{j}.png", im) for j, (k, im) in enumerate(zip(mapping, rendered))}
            elif isinstance(raw.get("images"), dict) and raw["images"]:
                mapping = {k: str(v) for k, v in raw["images"].items()}
            else:
                raise SpecError(f"widget '{name}': imagelist needs 'images' or 'texts' (a mapping)")
            try:
                pairs = build_thresholds(mapping, kw["source"], rule, str(raw.get("hemisphere", "north")),
                                         raw.get("boundaries"))
            except ValueError as e:
                raise SpecError(f"widget '{name}': {e}") from None
        keys = _blank_like(ctx, name, [p for _, p in pairs])
        kw["images"] = [(th, k) for (th, _), k in zip(pairs, keys)]
        kw["type"] = "imagelist" if t == "imagelist" else "bar"
        kw["default_index"] = int(raw.get("default", kw["images"][0][0]))
    elif t == "animation":
        frames = _expand(face.base, raw.get("frames", []))
        kw["images"] = list(enumerate(frames))
        kw["interval_ms"] = int(raw.get("interval_ms", 120))
        kw["repeat"] = int(raw.get("repeat", 0))
    else:  # number
        if kw.get("source", "0") == "0":
            raise SpecError(f"widget '{name}': number needs a 'source'")
        if rule:
            raise SpecError(f"widget '{name}': numbers need a real data source, not the rule '{rule}'")
        imgs = raw.get("images")
        if imgs is None:
            st = ctx.text_style(raw, "font")
            digs = fonts.digit_images(st["font"], st["size"], st["color"], st["weight"], st["stroke"], st["stroke_color"])
            paths = [ctx.gen(f"_gen/{name}/digit_{n}.png", im) for n, im in enumerate(digs)]
        elif isinstance(imgs, str) and "{n}" in imgs:
            paths = [imgs.replace("{n}", str(n)) for n in range(10)]
        else:
            paths = _expand(face.base, imgs)
        if len(paths) != 10:
            raise SpecError(f"widget '{name}': number needs 10 digit images (0-9), got {len(paths)}")
        kw["images"] = list(enumerate(paths))
        kw["digits"] = int(raw.get("digits", 1))
        kw["spacing"] = int(raw.get("spacing", 0))
        kw["zero_pad"] = bool(raw.get("zero_pad", True))
        align = str(raw.get("align", "left")).lower()
        if align not in ALIGN:
            raise SpecError(f"widget '{name}': align must be left, center or right")
        kw["align"] = align

    # box + fit for pictures
    if "box" in raw and kw["type"] in ("image", "imagelist", "animation"):
        bx = raw["box"]
        if not isinstance(bx, (list, tuple)) or len(bx) != 4:
            raise SpecError(f"widget '{name}': box must be [x, y, w, h]")
        box = (length(bx[0], dev.width), length(bx[1], dev.height), length(bx[2], dev.width), length(bx[3], dev.height))
        fitted = ctx.fit(name, [k for _, k in kw["images"]], box, str(raw.get("fit", "contain")))
        kw["images"] = [(th, k) for (th, _), k in zip(kw["images"], fitted)]
        kw["x"], kw["y"] = box[0], box[1]

    w = Widget(**kw)
    anchor = str(raw.get("anchor", "top-left"))
    if anchor not in ANCHORS:
        raise SpecError(f"widget '{name}': anchor must be one of {', '.join(ANCHORS)}")
    if anchor != "top-left" and "box" not in raw and all(face.exists(k) for _, k in w.images):
        ax, ay = ANCHORS[anchor]
        ww, wh = face.widget_size(w)
        w.x -= round(ww * ax)
        w.y -= round(wh * ay)
    return w


def load_face(path, device: Optional[Device] = None, style_override: Optional[dict] = None,
              face_id: Optional[str] = None, id_length: Optional[int] = None) -> Face:
    """Load a face from a folder containing face.yaml, or from a yaml file.
    `style_override` overrides the face's style (e.g. fonts chosen at run time);
    `face_id` / `id_length` override `id` / `id_length` in face.yaml."""
    p = Path(path)
    spec = p / "face.yaml" if p.is_dir() else p
    if not spec.is_file():
        raise SpecError(f"{spec} not found")
    data = yaml.safe_load(spec.read_text(encoding="utf-8")) or {}
    base = spec.parent
    name = str(data.get("name") or base.name)
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", name):
        raise SpecError(f"name '{name}' may only contain letters, digits, '_' and '-'")
    if device is None:
        try:
            device = get_device(data.get("device"))
        except ValueError as e:
            raise SpecError(str(e)) from None
    variant = (data.get("variants") or {}).get(device.shape) or {}
    style = dict(DEFAULT_STYLE)
    style.update(data.get("style") or {})
    style.update(variant.get("style") or {})
    import os
    for key, env in (("font", "MOODFACE_FONT"), ("text_font", "MOODFACE_TEXT_FONT")):
        if os.environ.get(env):
            style[key] = os.environ[env]
    style.update({k: v for k, v in (style_override or {}).items() if v})
    # id: --id, else face.yaml `id` (digits or `time`), else derived from the name (--id-length / `id_length`, default 9)
    length = check_id_length(id_length if id_length is not None else data.get("id_length", 9))
    if face_id is not None:
        fid = resolve_id(face_id)
    elif data.get("id") is not None:
        fid = resolve_id(data["id"])
    else:
        fid = derive_id(name, length)
    face = Face(name=name, title=str(data.get("title") or name), device=device, base=base, widgets=[],
                id=fid, background=str(data.get("background", "#000000")),
                preview=data.get("preview"), style=style)

    raw_widgets = []
    if variant.get("layout", data.get("layout")):
        from .layouts import expand_layout
        try:
            from .layouts import merge_slots
            slots = merge_slots(data.get("slots") or {}, variant.get("slots"))
            raw_widgets += expand_layout(variant.get("layout", data["layout"]), slots, face)
        except ValueError as e:
            raise SpecError(str(e)) from None
    raw_widgets += list(variant.get("widgets", data.get("widgets")) or [])
    if not raw_widgets:
        raise SpecError("face has no widgets (add `widgets:` or a `layout:` with `slots:`)")
    ctx = _Ctx(face)
    face.widgets = [_parse_widget(ctx, i, w) for i, w in enumerate(raw_widgets)]
    return face


def _outside_circle(face: Face, w: Widget) -> bool:
    """True if opaque pixels of the widget land outside a round screen (checks up to 6 images)."""
    from PIL import ImageChops
    W, H = face.device.width, face.device.height
    outside = Image.new("L", (W, H), 255)
    ImageDraw.Draw(outside).ellipse([1, 1, W - 2, H - 2], fill=0)
    for _, key in w.images[:6]:
        layer = Image.new("L", (W, H), 0)
        layer.paste(face.image(key).getchannel("A").point(lambda a: 255 if a > 40 else 0), (w.x, w.y))
        hits = ImageChops.multiply(layer, outside).histogram()[255]
        if hits > 30:
            return True
    return False


def validate(face: Face) -> Tuple[List[str], List[str]]:
    """Return (errors, warnings). Errors would make the compiler fail or the face break."""
    errors: List[str] = []
    warnings: List[str] = []
    dev = face.device

    try:
        check_id(face.id)
    except SpecError as e:
        errors.append(str(e))
    if face.preview and not face.path(face.preview).is_file():
        errors.append(f"preview image not found: {face.preview}")

    names = [w.name for w in face.widgets]
    for n in sorted({n for n in names if names.count(n) > 1}):
        errors.append(f"duplicate widget name '{n}'")

    anim = [w for w in face.widgets if w.type == "animation"]
    if len({(w.repeat, w.interval_ms) for w in anim}) < len(anim):
        warnings.append("several animations share the same repeat/interval; the compiler keys animations by name")

    total_px = 0
    for w in face.widgets:
        missing = [p for _, p in w.images if not face.exists(p)]
        if missing:
            errors.append(f"{w.name}: missing image(s): {', '.join(missing[:3])}{' ...' if len(missing) > 3 else ''}")
            continue
        sizes = {face.image(p).size for _, p in w.images}
        if len(sizes) > 1 and w.type in ("imagelist", "animation", "number", "bar"):
            errors.append(f"{w.name}: all images must have the same size, found {sorted(sizes)}")
        if w.source in dev.missing_sources:
            errors.append(f"{w.name}: source '{w.source_name}' is not available on {dev.name}")
        if w.type == "animation":
            if len(w.images) < 2:
                errors.append(f"{w.name}: animation needs at least 2 frames")
            if w.interval_ms < 20:
                warnings.append(f"{w.name}: interval_ms {w.interval_ms} is very short")
            if len(w.images) > 30:
                warnings.append(f"{w.name}: {len(w.images)} frames may exceed the band's memory")
        if w.type == "number" and not 1 <= w.digits <= 10:
            errors.append(f"{w.name}: digits must be 1-10")
        ww, wh = face.widget_size(w)
        if w.x < 0 or w.y < 0 or w.x + ww > dev.width or w.y + wh > dev.height:
            warnings.append(f"{w.name}: {ww}x{wh} at ({w.x},{w.y}) goes outside the {dev.width}x{dev.height} screen")
        elif dev.shape == "round" and ww < dev.width * 0.95 and _outside_circle(face, w):
            warnings.append(f"{w.name}: part of the picture falls outside the round screen and will be clipped")
        total_px += sum(face.image(p).width * face.image(p).height for p in {p for _, p in w.images})
    est_kb = total_px * 4 // 1024 // 3  # rough: RGBA, ~3x compression
    limit = 1500 * max(1.0, dev.width * dev.height / (192 * 490))
    if est_kb > limit:
        warnings.append(f"assets are large (~{est_kb} KB estimated); the band may refuse big faces")
    return errors, warnings
