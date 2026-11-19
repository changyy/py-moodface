"""Data sources a face widget can bind to (Mi Create .fprj IDs, Band 8/9/10 generation)."""
from __future__ import annotations

# name: (fprj id, description)
SOURCES = {
    "hour": ("0811", "Hour, 0-23"),
    "hour_low": ("0911", "Hour, low digit"),
    "hour_high": ("1000911", "Hour, high digit"),
    "minute": ("1011", "Minute, 0-59"),
    "minute_low": ("1111", "Minute, low digit"),
    "minute_high": ("1211", "Minute, high digit"),
    "second": ("1811", "Second, 0-59"),
    "second_low": ("1911", "Second, low digit"),
    "second_high": ("1001911", "Second, high digit"),
    "day": ("1812", "Day of month"),
    "day_low": ("1912", "Day of month, low digit"),
    "day_high": ("1001912", "Day of month, high digit"),
    "week": ("2012", "Day of week, 0 = Sunday"),
    "month": ("1012", "Month, 1-12"),
    "year": ("0812", "Year"),
    "ampm": ("0813", "AM/PM"),
    "weather": ("3031", "Weather type (icon index)"),
    "temp_c": ("2031", "Current temperature, Celsius"),
    "temp_f": ("40009031", "Current temperature, Fahrenheit"),
    "battery": ("0841", "Battery percent"),
    "sleep_mode": ("1841", "Sleep mode, 0 off / 1 on"),
    "bluetooth": ("2041", "Bluetooth connected, 0 / 1"),
    "screen_lock": ("3041", "Screen locked, 0 / 1"),
    "heart_rate": ("0822", "Heart rate, bpm"),
    "hr_zone": ("1022", "Heart rate zone, 1-5"),
    "steps": ("0821", "Steps today"),
    "steps_percent": ("1021", "Step goal progress, percent"),
    "steps_km": ("1821", "Distance, km"),
    "calories": ("0823", "Active calories"),
    "calories_percent": ("1023", "Calorie goal progress, percent"),
    "stand": ("0824", "Stand count"),
    "stress": ("0826", "Psychological stress, 0-100"),
    "sleep_score": ("0828", "Sleep score"),
}

ID_TO_NAME = {v[0]: k for k, v in SOURCES.items()}


def resolve(name_or_id) -> str:
    """Return the fprj source id for a source name or a raw numeric id."""
    s = str(name_or_id).strip()
    if s in SOURCES:
        return SOURCES[s][0]
    if s.isdigit():
        return s
    raise ValueError(f"unknown data source '{s}' (see `moodface sources`)")
