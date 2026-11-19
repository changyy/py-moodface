"""Turn a Face into a Mi Create .fprj project (XML + images folder)."""
from __future__ import annotations

import shutil
import xml.dom.minidom
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image

from .render import render_frame
from .spec import ALIGN, Face, Widget

SHAPE = {"image": "30", "imagelist": "31", "animation": "31", "number": "32"}
THUMB = "_preview.png"


def flat_name(rel: str) -> str:
    """assets/digits/0.png -> assets__digits__0.png (the compiler wants a flat images folder)."""
    return "__".join(Path(rel).parts)


def widget_name(w: Widget) -> str:
    if w.type == "animation":
        return f"anim_[{w.repeat}@{w.interval_ms}]"
    return w.name


def widget_attrs(face: Face, w: Widget) -> dict:
    width, height = face.widget_size(w)
    t = w.fprj_type
    a = {"Shape": SHAPE[t], "Name": widget_name(w), "X": w.x, "Y": w.y, "Width": width, "Height": height,
         "Alpha": w.alpha, "Visible_Src": 0}
    if t == "image":
        a["Bitmap"] = flat_name(w.images[0][1])
    elif t in ("imagelist", "animation"):
        a.update(Alignment=0, DefaultIndex=w.default_index if t == "imagelist" else 0,
                 Index_Src=w.source if t == "imagelist" else 0,
                 BitmapList="|".join(f"({i}):{flat_name(p)}" for i, p in w.images))
    else:
        a.update(Digits=w.digits, Alignment=ALIGN[w.align], Value_Src=w.source, Spacing=w.spacing,
                 Blanking=0 if w.zero_pad else 1, BitmapList="|".join(flat_name(p) for _, p in w.images))
    return {k: str(v) for k, v in a.items()}


def write_project(face: Face, out_dir: Path, thumb_size=None) -> Path:
    """Write <out_dir>/<name>.fprj and <out_dir>/images/. Returns the .fprj path."""
    out_dir = Path(out_dir)
    images = out_dir / "images"
    if images.exists():
        shutil.rmtree(images)
    images.mkdir(parents=True)
    (out_dir / "output").mkdir(exist_ok=True)

    for w in face.widgets:
        for _, key in w.images:
            target = images / flat_name(key)
            if not target.exists():
                face.image(key).save(target)

    thumb = face.image(face.preview) if face.preview else render_frame(face)
    thumb.convert("RGBA").resize(tuple(thumb_size or face.device.thumbnail_size), Image.LANCZOS).save(images / THUMB)

    root = ET.Element("FaceProject", DeviceType=face.device.device_type, Id=face.id)
    screen = ET.SubElement(root, "Screen", Title=face.title, Bitmap=THUMB)
    for w in face.widgets:
        ET.SubElement(screen, "Widget", widget_attrs(face, w))
    xml_str = xml.dom.minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(indent="  ")
    fprj = out_dir / f"{face.name}.fprj"
    fprj.write_text(xml_str, encoding="utf-8")
    return fprj
