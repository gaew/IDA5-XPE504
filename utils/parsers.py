import re
from typing import Optional

WEIGHT_RE    = re.compile(r"(?P<value>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>mg|g|kg)\b", re.IGNORECASE)
VOL_RE       = re.compile(r"\[\s*VOL\s*,\s*(?P<vol>\d+\.\d+)", re.IGNORECASE)
FLOW_RE      = re.compile(r"\[\s*FLOW\s*,\s*(?P<flow>\d+\.\d+)", re.IGNORECASE)
HEX_FRAME_RE = re.compile(r"^\d+:[0-9A-Fa-f]+$")


def to_grams(value: float, unit: str) -> float:
    u = unit.lower()
    if u == "mg":
        return value / 1000.0
    if u == "kg":
        return value * 1000.0
    return value


def parse_weight_line(line: str) -> Optional[float]:
    m = WEIGHT_RE.search(line)
    if m:
        return to_grams(float(m.group("value")), m.group("unit"))
    return None


def parse_flow_line(line: str) -> Optional[float]:
    m = FLOW_RE.search(line)
    return float(m.group("flow")) if m else None


def parse_vol_line(line: str) -> Optional[float]:
    m = VOL_RE.search(line)
    return float(m.group("vol")) if m else None
