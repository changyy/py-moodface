"""Switching rules: turn friendly keys into image-list thresholds.

An image list maps keys to images (or texts). Keys can be:

  40          threshold — used from 40 until the next key
  "6-11"      inclusive range; values outside every range show nothing
  "22-5"      a range that wraps around (hour 22..23 and 0..5)
  spring      a named key of a rule source, e.g. source: season

Rule sources are virtual sources that map onto a real one:

  season         month    spring, summer, autumn, winter   (hemisphere: north | south)
  time_of_day    hour     night, dawn, day, dusk
  weekday        week     sun, mon, tue, wed, thu, fri, sat
  weekpart       week     weekday, weekend
  stress_level   stress   calm, normal, medium, high
  battery_level  battery  low, mid, high
  hr_level       heart_rate  rest, normal, active, high
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .sources import ID_TO_NAME, resolve

Range = Tuple[int, int]

RULES: Dict[str, Tuple[str, Dict[str, List[Range]]]] = {
    "season": ("month", {"spring": [(3, 5)], "summer": [(6, 8)], "autumn": [(9, 11)], "winter": [(12, 12), (1, 2)]}),
    "time_of_day": ("hour", {"night": [(0, 4), (19, 23)], "dawn": [(5, 7)], "day": [(8, 16)], "dusk": [(17, 18)]}),
    "weekday": ("week", {k: [(i, i)] for i, k in enumerate(["sun", "mon", "tue", "wed", "thu", "fri", "sat"])}),
    "weekpart": ("week", {"weekday": [(1, 5)], "weekend": [(0, 0), (6, 6)]}),
    "stress_level": ("stress", {"calm": [(0, 39)], "normal": [(40, 59)], "medium": [(60, 79)], "high": [(80, 100)]}),
    "battery_level": ("battery", {"low": [(0, 19)], "mid": [(20, 59)], "high": [(60, 100)]}),
    "hr_level": ("heart_rate", {"rest": [(0, 69)], "normal": [(70, 99)], "active": [(100, 139)], "high": [(140, 250)]}),
}
SOUTH = {"spring": "autumn", "autumn": "spring", "summer": "winter", "winter": "summer"}

DOMAIN = {"hour": (0, 23), "minute": (0, 59), "second": (0, 59), "month": (1, 12), "day": (1, 31), "week": (0, 6),
          "stress": (0, 100), "battery": (0, 100), "heart_rate": (0, 250), "steps_percent": (0, 100),
          "calories_percent": (0, 100), "sleep_score": (0, 100), "hr_zone": (1, 5)}


def domain(source_name: str) -> Tuple[int, int]:
    return DOMAIN.get(source_name, (0, 10 ** 6))


def rule_ranges(rule: str, hemisphere: str = "north", boundaries: Optional[dict] = None) -> Dict[str, List[Range]]:
    real, table = RULES[rule]
    table = {k: list(v) for k, v in table.items()}
    if rule == "season" and hemisphere == "south":
        table = {SOUTH[k]: v for k, v in table.items()}
    if boundaries:  # e.g. {calm: 0, normal: 35, medium: 55, high: 75} → threshold style
        lo, hi = domain(real)
        starts = sorted((int(v), k) for k, v in boundaries.items())
        table = {k: [(s, (starts[i + 1][0] - 1) if i + 1 < len(starts) else hi)] for i, (s, k) in enumerate(starts)}
    return table


def resolve_source(source) -> Tuple[str, Optional[str]]:
    """Return (fprj source id, rule name or None)."""
    s = str(source).strip()
    if s in RULES:
        return resolve(RULES[s][0]), s
    return resolve(s), None


def _parse_range(key: str, lo: int, hi: int) -> List[Range]:
    a, b = (int(x) for x in key.split("-", 1))
    if a <= b:
        return [(a, b)]
    return [(a, hi), (lo, b)]


def build_thresholds(mapping: dict, source_id: str, rule: Optional[str] = None, hemisphere: str = "north",
                     boundaries: Optional[dict] = None) -> List[Tuple[int, Optional[object]]]:
    """Map keys → [(threshold, value-or-None)] sorted; None means 'show nothing' (a gap)."""
    name = ID_TO_NAME.get(source_id, source_id)
    lo, hi = domain(name)
    named = rule_ranges(rule, hemisphere, boundaries) if rule else {}
    spans: List[Tuple[int, int, object]] = []
    plain: List[Tuple[int, object]] = []
    for key, value in mapping.items():
        k = str(key).strip()
        if k in named:
            spans += [(a, b, value) for a, b in named[k]]
        elif "-" in k[1:] and all(p.strip().lstrip("-").isdigit() for p in k.split("-", 1)):
            spans += [(a, b, value) for a, b in _parse_range(k, lo, hi)]
        elif k.lstrip("-").isdigit():
            plain.append((int(k), value))
        else:
            known = ", ".join(named) if named else "numbers or ranges like 6-11"
            raise ValueError(f"unknown key '{k}' (expected {known})")
    if spans and plain:
        raise ValueError("mix of thresholds and ranges/named keys; use one style per list")
    if plain:
        out = sorted(plain, key=lambda t: t[0])
        if out[0][0] > lo:
            out.insert(0, (lo, None))
        return out

    spans.sort(key=lambda t: t[0])
    out: List[Tuple[int, Optional[object]]] = []
    cursor = lo
    for a, b, v in spans:
        if a < cursor:
            raise ValueError(f"overlapping ranges around {a}")
        if a > cursor:
            out.append((cursor, None))
        out.append((a, v))
        cursor = b + 1
    if cursor <= hi:
        out.append((cursor, None))
    # merge neighbours showing the same value
    merged: List[Tuple[int, Optional[object]]] = []
    for t, v in out:
        if merged and merged[-1][1] == v:
            continue
        merged.append((t, v))
    return merged
