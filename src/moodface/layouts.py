"""Layouts: named slot arrangements expanded into low-level widgets for any screen size.

A layout file (resources/layouts/<name>.yaml, or any path) looks like this; `variants`
adjust slots for square and round screens (band is the base):

    description: Big time on top, artwork in the middle, stats below
    slots:
      time:      {kind: time, x: 50%, y: 7%, anchor: top, size: 11%, default: true}
      character: {kind: art, box: [2%, 27%, 96%, 37%], fit: contain}
      stats:     {kind: stats, box: [10%, 80%, 80%, 12%], arrange: rows, size: 2.8%,
                  items: [stress, steps, heart_rate], default: true}
    variants:
      round:
        slots:
          time:  {y: 12%, size: 14%}
          stats: {box: [20%, 78%, 60%, 10%], arrange: inline}

Slot kinds: art, time, date, weekday, caption, bar, stats, panel, text.
In face.yaml, `slots:` fills or tweaks them: `false` hides a slot, a mapping overrides keys,
and art slots take a picture, an image list, an animation or a list of layers.
"""
from __future__ import annotations

import re
from importlib import resources
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

from . import fonts
from .rules import RULES
from .spec import ANCHORS, length

LABELS = {"stress": "壓力", "steps": "步數", "heart_rate": "心率", "battery": "電量", "calories": "卡路里",
          "sleep_score": "睡眠", "temp_c": "溫度", "steps_percent": "目標", "stand": "站立", "steps_km": "公里"}
DIGITS = {"steps": 5, "calories": 4, "temp_c": 2, "temp_f": 3}
WEEK_ZH = ["日", "一", "二", "三", "四", "五", "六"]
WEEK_EN = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def layout_dir() -> Path:
    return Path(str(resources.files("moodface").joinpath("resources/layouts")))


def list_layouts() -> Dict[str, str]:
    out = {}
    for p in sorted(layout_dir().glob("*.yaml")):
        out[p.stem] = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("description", "")
    return out


def load_layout(name: str, base: Path) -> dict:
    p = Path(name)
    for cand in (base / p, p, layout_dir() / f"{name}.yaml"):
        if cand.is_file() and cand.suffix in (".yaml", ".yml"):
            return yaml.safe_load(cand.read_text(encoding="utf-8")) or {}
    raise ValueError(f"unknown layout '{name}' (built-in: {', '.join(list_layouts())})")


# Devices whose firmware mis-draws 2-digit hour / minute number widgets (see sequence()).
SPLIT_TIME_DEVICE_TYPES = {"9", "366"}   # Xiaomi Smart Band 8, Band 9
SPLIT_DIGITS = {"hour": ("hour_high", "hour_low"), "minute": ("minute_high", "minute_low")}


class _L:
    """Layout expansion helpers bound to a face (device + style)."""

    def __init__(self, face):
        self.face = face
        self.W, self.H = face.device.width, face.device.height
        self.st = face.style

    def px(self, v, axis="h") -> int:
        return length(v, self.W if axis == "w" else self.H)

    def font_for(self, text: str, d: dict) -> str:
        if any(ord(c) > 0x2E7F for c in text):
            return d.get("text_font", self.st["text_font"])
        return d.get("font", self.st["font"])

    def stroke(self, d: dict) -> dict:
        return {"stroke": int(d.get("stroke", self.st.get("stroke", 0))),
                "stroke_color": d.get("stroke_color", self.st.get("stroke_color", "#00000099"))}

    def place(self, d: dict, w: int, h: int) -> Tuple[int, int]:
        ax, ay = ANCHORS[str(d.get("anchor", "top-left"))]
        return self.px(d.get("x", 0), "w") - round(w * ax), self.px(d.get("y", 0)) - round(h * ay)

    # ----- sequences of numbers and literals (time, date) -----

    def sequence(self, slot: str, d: dict, parts: List[tuple]) -> List[dict]:
        size = self.px(d.get("size", "10%"))
        weight = d.get("weight", self.st.get("weight"))
        color = d.get("color", self.st["color"])
        nfont = d.get("font", self.st["font"])
        gap = self.px(d.get("gap", 0), "w")
        spacing = self.px(d.get("spacing", 0), "w")   # between digits; negative tightens
        sk = self.stroke(d)
        cw, ch = fonts.digit_cell(nfont, size, weight, sk["stroke"])
        measured = []
        for p in parts:
            if p[0] == "num":
                measured.append((p, p[2] * cw + (p[2] - 1) * spacing, ch, None))
            elif p[0] == "week":
                labels = p[1]
                f = self.font_for("".join(labels), d)
                sizes = [fonts.text_size(t, f, size, weight, sk["stroke"]) for t in labels]
                measured.append((p, max(s[0] for s in sizes), max(s[1] for s in sizes), f))
            else:
                f = self.font_for(p[1], d)
                tw, th = fonts.text_size(p[1], f, size, weight, sk["stroke"])
                measured.append((p, tw, th, f))
        total = sum(m[1] for m in measured) + gap * (len(measured) - 1)
        row_h = max(m[2] for m in measured)
        x, y = self.place(d, total, row_h)
        out = []
        for i, (p, w, h, f) in enumerate(measured):
            top = y + (row_h - h) // 2
            base = dict({"name": f"{slot}_{i}", "x": x, "y": top, "size": size, "weight": weight, "color": color}, **sk)
            if p[0] == "num" and p[2] == 2 and p[1] in SPLIT_DIGITS and \
                    self.face.device.device_type in SPLIT_TIME_DEVICE_TYPES:
                # Band 8 firmware shows a 2-digit hour / minute number widget one too high at
                # times (23:36 drawn as 24:37, seen on a real band); its per-digit sources are
                # right, so draw the tens and the units as two 1-digit widgets. Band 9 shares the
                # same screen and widget set, so it gets the same treatment.
                hi, lo = SPLIT_DIGITS[p[1]]
                out.append(dict(base, name=f"{slot}_{i}h", type="number", source=hi, digits=1, font=nfont,
                                zero_pad=True, spacing=0))
                out.append(dict(base, name=f"{slot}_{i}l", x=x + cw + spacing, type="number", source=lo,
                                digits=1, font=nfont, zero_pad=True, spacing=0))
            elif p[0] == "num":
                out.append(dict(base, type="number", source=p[1], digits=p[2], font=nfont, zero_pad=True, spacing=spacing))
            elif p[0] == "week":
                out.append(dict(base, type="imagelist", source="week", font=f,
                                texts={str(k): v for k, v in enumerate(p[1])}))
            elif p[1].strip():
                out.append(dict(base, type="text", text=p[1], font=f))
            x += w + gap
        return out

    def kind_time(self, slot, d):
        fmt = str(d.get("format", "HH:MM"))
        tokens = {"HH": ("hour", 2), "MM": ("minute", 2), "SS": ("second", 2)}
        return self.sequence(slot, d, _tokenize(fmt, tokens))

    def kind_date(self, slot, d):
        fmt = str(d.get("format", "MM/DD 週W"))
        tokens = {"YYYY": ("year", 4), "MM": ("month", 2), "DD": ("day", 2), "WWW": "week_en", "W": "week_zh"}
        parts = []
        for p in _tokenize(fmt, tokens):
            if p == ("num", "week_en", None):
                parts.append(("week", WEEK_EN))
            elif p == ("num", "week_zh", None):
                parts.append(("week", WEEK_ZH))
            else:
                parts.append(p)
        return self.sequence(slot, d, parts)

    def kind_caption(self, slot, d):
        if not d.get("texts"):
            return []
        size = self.px(d.get("size", "3.4%"))
        texts = d["texts"]
        f = self.font_for("".join(map(str, texts.values())), d)
        sk = self.stroke(d)
        # the widget anchors itself once its (badge-padded) text images exist
        return [{"type": "imagelist", "name": slot, "x": d.get("x", 0), "y": d.get("y", 0),
                 "anchor": d.get("anchor", "top-left"), "source": d.get("source", "stress_level"),
                 "texts": texts, "font": f, "size": size, "color": d.get("color", self.st["color"]),
                 "weight": d.get("weight", self.st.get("weight")), "hemisphere": d.get("hemisphere", "north"), **sk,
                 **{k: d[k] for k in ("bg", "pad", "radius", "outline", "outline_width", "boundaries") if k in d}}]

    def kind_bar(self, slot, d):
        w, h = self.px(d.get("w", "50%"), "w"), self.px(d.get("h", "1%"))
        x, y = self.place(d, w, h)
        return [{"type": "bar", "name": slot, "x": x, "y": y, "w": w, "h": h, "source": d.get("source", "stress"),
                 "max": d.get("max", 100), "steps": d.get("steps", 10), "color": d.get("color", self.st["accent"]),
                 "track": d.get("track", "#FFFFFF33"), "direction": d.get("direction", "right"),
                 "radius": d.get("radius")}]

    def kind_text(self, slot, d):
        size = self.px(d.get("size", "3%"))
        f = self.font_for(str(d.get("text", "")), d)
        sk = self.stroke(d)
        w, h = fonts.text_size(str(d["text"]), f, size, d.get("weight", self.st.get("weight")), sk["stroke"])
        x, y = self.place(d, w, h)
        return [{"type": "text", "name": slot, "x": x, "y": y, "text": d["text"], "font": f, "size": size,
                 "color": d.get("color", self.st["color"]), "weight": d.get("weight", self.st.get("weight")), **sk}]

    def kind_panel(self, slot, d):
        bx = d.get("box", [0, 0, "100%", "100%"])
        return [{"type": "image", "name": slot, "x": bx[0], "y": bx[1], "w": bx[2], "h": bx[3],
                 "fill": d.get("fill", "#00000080"), "radius": d.get("radius", 12), "outline": d.get("outline"),
                 "outline_width": d.get("outline_width", 2 if d.get("outline") else 0)}]

    def kind_stats(self, slot, d):
        """Labelled values. Item keys: source, label, icon (image path, replaces the label),
        unit (text after the value, e.g. "°" or "%"), digits, color.
        `card: {fill, outline, radius, pad}` draws a box behind each item."""
        items = []
        for it in d.get("items") or []:
            it = {"source": it} if isinstance(it, str) else dict(it)
            src = it["source"]
            it.setdefault("label", LABELS.get(src, src))
            it.setdefault("digits", DIGITS.get(src, 3))
            items.append(it)
        if not items:
            return []
        size = self.px(d.get("size", "2.8%"))
        vsize = self.px(d.get("value_size", round(size * 1.3)))
        weight = d.get("weight", self.st.get("weight"))
        label_color = d.get("label_color", self.st["muted"])
        value_color = d.get("color", self.st["color"])
        bx = d.get("box", ["10%", "80%", "80%", "12%"])
        X, Y, BW, BH = self.px(bx[0], "w"), self.px(bx[1]), self.px(bx[2], "w"), self.px(bx[3])
        nfont = d.get("font", self.st["font"])
        sk = self.stroke(d)
        cw, ch = fonts.digit_cell(nfont, vsize, weight, sk["stroke"])
        usize = round(vsize * 0.75)
        arrange = d.get("arrange", "rows")
        gap = self.px(d.get("gap", "1.2%"), "w")
        card = d.get("card")
        cards: List[dict] = []
        out: List[dict] = []

        def lead_size(it):
            if it.get("icon"):
                s_ = round(vsize * 1.1)
                return s_, s_
            if str(it["label"]) == "":
                return 0, 0
            return fonts.text_size(str(it["label"]), self.font_for(str(it["label"]), d), size, weight, sk["stroke"])

        def lead(i, it, x, y):
            """Top-left placement of the label or icon (None when the label is empty)."""
            if not it.get("icon") and str(it["label"]) == "":
                return None
            if it.get("icon"):
                s_ = lead_size(it)[0]
                return {"type": "image", "name": f"{slot}_{i}_icon", "image": it["icon"], "box": [x, y, s_, s_],
                        "fit": "contain"}
            return {"type": "text", "name": f"{slot}_{i}_label", "text": str(it["label"]), "x": x, "y": y,
                    "font": self.font_for(str(it["label"]), d), "size": size, "color": label_color,
                    "weight": weight, **sk}

        def unit_w(it):
            return fonts.text_size(str(it["unit"]), self.font_for(str(it["unit"]), d), usize, weight, sk["stroke"])[0] if it.get("unit") else 0

        def value(i, it, x, y, align):
            """Value box (+ unit) with its top-left at x, y."""
            res = [{"type": "number", "name": f"{slot}_{i}_value", "source": it["source"], "digits": it["digits"],
                    "x": x, "y": y, "font": nfont, "size": vsize, "color": it.get("color", value_color),
                    "weight": weight, "zero_pad": False, "align": "right" if it.get("unit") and align == "left" else align, **sk}]
            if it.get("unit"):
                uh = fonts.text_size(str(it["unit"]), self.font_for(str(it["unit"]), d), usize, weight, sk["stroke"])[1]
                res.append({"type": "text", "name": f"{slot}_{i}_unit", "text": str(it["unit"]),
                            "x": x + it["digits"] * cw, "y": y + ch - uh, "font": self.font_for(str(it["unit"]), d),
                            "size": usize, "color": it.get("color", value_color), "weight": weight, **sk})
            return res

        def add_card(i, x0, y0, x1, y1):
            if not card:
                return
            pad = self.px(card.get("pad", "1%"))
            cards.append({"type": "image", "name": f"{slot}_{i}_card", "x": x0 - pad, "y": y0 - pad,
                          "w": x1 - x0 + 2 * pad, "h": y1 - y0 + 2 * pad, "fill": card.get("fill", "#FFFFFF22"),
                          "outline": card.get("outline"), "outline_width": card.get("outline_width", 0),
                          "radius": card.get("radius", 10)})

        if arrange == "rows":
            row_h = BH / len(items)
            cx = X + BW // 2
            for i, it in enumerate(items):
                cy = round(Y + row_h * (i + 0.5))
                lw, lh = lead_size(it)
                out.append(lead(i, it, cx - gap - lw, cy - lh // 2))
                out += value(i, it, cx + gap, cy - ch // 2, "left")
                add_card(i, X, round(Y + row_h * i) + 2, X + BW, round(Y + row_h * (i + 1)) - 2)
        elif arrange == "grid":
            cols = d.get("cols", "auto")
            cols = (1 if self.W < 250 else 2) if cols == "auto" else int(cols)
            rows = -(-len(items) // cols)
            cell_w, cell_h = BW / cols, BH / rows
            for i, it in enumerate(items):
                r, c = divmod(i, cols)
                ccx = round(X + cell_w * (c + 0.5))
                lw, lh = lead_size(it)
                top = round(Y + cell_h * r + (cell_h - lh - ch) / 2)
                out.append(lead(i, it, ccx - lw // 2, top))
                vw = it["digits"] * cw + unit_w(it)
                out += value(i, it, ccx - vw // 2, top + lh, "center")
                m = self.px("1%")
                add_card(i, round(X + cell_w * c) + m, round(Y + cell_h * r) + m,
                         round(X + cell_w * (c + 1)) - m, round(Y + cell_h * (r + 1)) - m)
        elif arrange == "inline":
            pieces = [(i, it, lead_size(it), it["digits"] * cw + unit_w(it)) for i, it in enumerate(items)]
            total = sum(ls[0] + gap // 2 + vw for _, _, ls, vw in pieces) + gap * 2 * (len(pieces) - 1)
            x = X + ((BW - total) // 2 if d.get("align", "center") == "center" else 0)
            cy = Y + BH // 2
            for i, it, (lw, lh), vw in pieces:
                x0 = x
                out.append(lead(i, it, x, cy - lh // 2))
                x += lw + gap // 2
                out += value(i, it, x, cy - ch // 2, "left")
                x += vw
                add_card(i, x0, cy - max(lh, ch) // 2, x, cy + max(lh, ch) // 2)
                x += gap * 2
        else:
            raise ValueError(f"stats '{slot}': arrange must be rows, grid or inline")
        return cards + [w for w in out if w is not None]

    def kind_weekday(self, slot, d):
        """Weekday tag, e.g. 週三 / Wed, optionally on a badge (bg, pad, radius, outline)."""
        names = WEEK_EN if d.get("lang", "zh") == "en" else WEEK_ZH
        prefix = d.get("prefix", "週" if d.get("lang", "zh") != "en" else "")
        texts = {str(i): f"{prefix}{n}" for i, n in enumerate(names)}
        size = self.px(d.get("size", "3%"))
        w = {"type": "imagelist", "name": slot, "source": "week", "texts": texts, "size": size,
             "x": d.get("x", 0), "y": d.get("y", 0), "anchor": d.get("anchor", "top-left"),
             "font": self.font_for("".join(texts.values()), d), "color": d.get("color", self.st["color"]),
             "weight": d.get("weight", self.st.get("weight")), **self.stroke(d)}
        for k in ("bg", "pad", "radius", "outline", "outline_width"):
            if k in d:
                w[k] = d[k]
        return [w]

    def kind_art(self, slot, d):
        layers = d.get("layers") or [d]
        out = []
        for j, layer in enumerate(layers):
            layer = {"image": layer} if isinstance(layer, str) else dict(layer)
            w = {"name": slot if len(layers) == 1 else f"{slot}_{j}"}
            if "box" in d and not {"x", "y"} & set(layer):
                w.update(box=layer.get("box", d["box"]), fit=layer.get("fit", d.get("fit", "contain")))
            for k in ("x", "y", "anchor", "alpha", "hemisphere", "boundaries", "default", "interval_ms", "repeat",
                      "font", "size", "color", "weight", "text_align"):
                if k in layer:
                    w[k] = layer[k]
            if "frames" in layer:
                w.update(type="animation", frames=layer["frames"])
            elif "images" in layer or "texts" in layer:
                w.update(type="imagelist", source=layer.get("source", "stress_level"))
                w["images" if "images" in layer else "texts"] = layer.get("images") or layer.get("texts")
            elif "image" in layer:
                w.update(type="image", image=layer["image"])
            else:
                raise ValueError(f"slot '{slot}': give image, images (+ source), texts or frames")
            out.append(w)
        return out


def _tokenize(fmt: str, tokens: dict) -> List[tuple]:
    pattern = "|".join(sorted(map(re.escape, tokens), key=len, reverse=True))
    parts: List[tuple] = []
    pos = 0
    for m in re.finditer(pattern, fmt):
        if m.start() > pos:
            parts.append(("lit", fmt[pos:m.start()]))
        tok = tokens[m.group()]
        parts.append(("num",) + (tok if isinstance(tok, tuple) else (tok, None)))
        pos = m.end()
    if pos < len(fmt):
        parts.append(("lit", fmt[pos:]))
    return parts


def merge_slots(base: dict, extra: dict) -> dict:
    """Overlay slot definitions: a mapping updates a slot, null removes it, new names are added."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for name, v in (extra or {}).items():
        if v is None:
            out.pop(name, None)
        elif isinstance(v, dict) and isinstance(out.get(name), dict):
            out[name] = dict(out[name], **v)
        else:
            out[name] = v
    return out


def expand_layout(layout: str, user_slots: dict, face) -> List[dict]:
    spec = load_layout(str(layout), face.base)
    L = _L(face)
    shape = face.device.shape
    defs = merge_slots(spec.get("slots") or {}, ((spec.get("variants") or {}).get(shape) or {}).get("slots"))
    for name, val in user_slots.items():
        if name not in defs:
            if isinstance(val, dict) and "kind" in val:
                defs[name] = {}
            else:
                raise ValueError(f"layout '{layout}' has no slot '{name}' (slots: {', '.join(defs)}); "
                                 "add `kind:` to define a new one")
    widgets: List[dict] = []
    for name, base in defs.items():
        val = user_slots.get(name)
        if val is False or (val is None and not base.get("default")):
            continue
        d = dict(base)
        kind = d.get("kind")
        if isinstance(val, dict):
            d.update(val)
            kind = val.get("kind", kind)
        elif isinstance(val, list):
            d["layers" if kind == "art" else "items"] = val
        elif isinstance(val, str):
            if kind == "art":
                d["image"] = val
            elif kind in ("time", "date"):
                d["format"] = val
            elif kind == "text":
                d["text"] = val
        handler = getattr(L, f"kind_{kind}", None)
        if handler is None:
            raise ValueError(f"slot '{name}': unknown kind '{kind}'")
        widgets += handler(name, d)
    return widgets


__all__ = ["expand_layout", "list_layouts", "load_layout", "RULES"]
