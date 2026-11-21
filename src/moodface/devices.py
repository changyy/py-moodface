"""Device profiles.

Values follow the device data shipped with Mi Create (https://github.com/ooflet/Mi-Create).
Shapes: `band` (tall strip), `square` (rounded rectangle) and `round` (circle); layouts pick
a variant per shape. `preview_size` is the thumbnail size the compiler expects (collected by compiling a test
face for each model); `moodface build` retries with the size the compiler reports if it differs.
`compile_status` records whether that compiler accepts the model. None of this means the face
was tested on the physical device.
Legacy models with a different data-source scheme (Xiaomi Watch Color, 70mai Saphir) are
not included.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Tuple

SHAPES = ("band", "square", "round")


@dataclass(frozen=True)
class Device:
    key: str
    name: str
    device_type: str
    width: int
    height: int
    radius: int
    shape: str = "band"
    preview_size: Optional[Tuple[int, int]] = None
    missing_sources: Tuple[str, ...] = ()
    compile_status: str = "untested"   # ok | fails | untested — with the Mi Create compiler (v4.22)
    note: str = ""

    @property
    def thumbnail_size(self) -> Tuple[int, int]:
        if self.preview_size:
            return self.preview_size
        return round(self.width * 122 / 192), round(self.height * 310 / 490)


def _shape(w: int, h: int, r: int) -> str:
    if w == h and r * 2 >= w - 4:
        return "round"
    return "band" if h > w * 1.35 else "square"


OLD = ("1821", "40009031")  # distance km, temperature °F

# key: (preview size reported by the compiler, compile status, note)
_COMPILER = {
    "band7pro": ((220, 358), "ok", ""),
    "band8": ((122, 310), "ok", ""),
    "band8pro": ((230, 328), "ok", ""),
    "band9": ((122, 310), "ok", ""),
    "band9pro": ((230, 328), "ok", ""),
    "band10": ((212, 520), "ok", "output is uncompressed (~2 MB)"),
    "band11": ((212, 520), "ok", "same build as Band 10; output is uncompressed (~2–3 MB)"),
    "redmibandpro": ((110, 208), "ok", "output is uncompressed"),
    "redmiwatch": ((178, 178), "ok", "output is uncompressed"),
    "redmiwatch2lite": ((178, 178), "ok", "output is uncompressed"),
    "redmiwatch3": ((234, 270), "ok", ""),
    "redmiwatch3active": (None, "fails", "compiler: 'Input string was not in a correct format'"),
    "redmiwatch4": ((234, 270), "ok", ""),
    "redmiwatch5": ((432, 514), "ok", ""),
    "redmiwatch5active": (None, "fails", "compiler: image list compression fails; needs a newer compiler"),
    "redmiwatch5lite": (None, "fails", "compiler: image list compression fails; needs a newer compiler"),
    "watchs1": ((246, 246), "ok", "output is uncompressed (~2 MB)"),
    "watchs1pro": ((280, 280), "ok", "output is uncompressed (~2 MB)"),
    "watchs3": ((326, 326), "ok", ""),
    "watchs4": ((326, 326), "ok", ""),
}

_RAW = [
    # key, name, DeviceType, width, height, radius, missing sources
    ("band7pro", "Xiaomi Smart Band 7 Pro", "6", 280, 456, 28, OLD),
    ("band8", "Xiaomi Smart Band 8", "9", 192, 490, 100, ("1821",)),
    ("band8pro", "Xiaomi Smart Band 8 Pro", "11", 336, 480, 48, ()),
    ("band9", "Xiaomi Smart Band 9", "366", 192, 490, 100, ()),
    ("band9pro", "Xiaomi Smart Band 9 Pro", "367", 336, 480, 48, ()),
    ("band10", "Xiaomi Smart Band 10", "466", 212, 520, 106, ("1821",)),
    ("band11", "Xiaomi Smart Band 11", "466", 212, 520, 106, ("1821",)),
    ("redmibandpro", "Redmi Smart Band Pro", "8", 194, 368, 28, OLD),
    ("redmiwatch", "Redmi Watch / POCO Watch", "5", 320, 360, 60, OLD),
    ("redmiwatch2lite", "Redmi Watch 2 Lite", "10", 320, 360, 60, OLD),
    ("redmiwatch3", "Redmi Watch 3", "7", 390, 450, 86, OLD),
    ("redmiwatch3active", "Redmi Watch 3 Active", "12", 240, 280, 55, OLD),
    ("redmiwatch4", "Redmi Watch 4", "365", 390, 450, 90, ()),
    ("redmiwatch5", "Redmi Watch 5", "465", 432, 514, 103, ()),
    ("redmiwatch5active", "Redmi Watch 5 Active", "3651", 320, 385, 82, ("1821",)),
    ("redmiwatch5lite", "Redmi Watch 5 Lite", "3652", 410, 502, 110, ()),
    ("watchs1", "Xiaomi Watch S1 / S2 / Watch 2", "3", 466, 466, 233, ("0828",) + OLD),
    ("watchs1pro", "Xiaomi Watch S1 Pro", "4", 480, 480, 240, OLD),
    ("watchs3", "Xiaomi Watch S3", "362", 466, 466, 233, ()),
    ("watchs4", "Xiaomi Watch S4", "462", 466, 466, 233, ()),
]

DEVICES = {}
for _k, _n, _t, _w, _h, _r, _miss in _RAW:
    _ps, _st, _note = _COMPILER.get(_k, (None, "untested", ""))
    DEVICES[_k] = Device(_k, _n, _t, _w, _h, _r, _shape(_w, _h, _r), preview_size=_ps, missing_sources=_miss,
                         compile_status=_st, note=_note)

DEFAULT_DEVICE = "band9"


def get_device(key: Optional[str] = None, *, width: Optional[int] = None, height: Optional[int] = None,
               radius: Optional[int] = None, device_type: Optional[str] = None,
               preview_size: Optional[Tuple[int, int]] = None, shape: Optional[str] = None) -> Device:
    """Return a device profile, optionally overriding any field (for new or custom models)."""
    key = (key or DEFAULT_DEVICE).lower().replace("_", "").replace("-", "").replace(" ", "")
    if key in DEVICES:
        dev = DEVICES[key]
    elif None not in (width, height, device_type):
        r = int(radius or 0)
        dev = Device(key, key, str(device_type), int(width), int(height), r, _shape(int(width), int(height), r))
    else:
        raise ValueError(f"unknown device '{key}' (known: {', '.join(DEVICES)}); "
                         "pass width, height and device_type for a custom device")
    if shape is not None and shape not in SHAPES:
        raise ValueError(f"shape must be one of {', '.join(SHAPES)}")
    changes = {k: v for k, v in dict(width=width, height=height, radius=radius,
                                     device_type=None if device_type is None else str(device_type),
                                     preview_size=preview_size, shape=shape).items() if v is not None}
    if changes:
        if shape is None and ({"width", "height", "radius"} & set(changes)):
            changes["shape"] = _shape(changes.get("width", dev.width), changes.get("height", dev.height),
                                      changes.get("radius", dev.radius))
        dev = replace(dev, compile_status="untested", **changes)
    return dev
