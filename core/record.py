from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class WeightRecord:
    """One Mettler weight reading.

    wall_time: datetime.now() captured the instant in_waiting > 0 (≈ OS rx-buffer arrival)
    perf_ns:   time.perf_counter_ns() at the same moment — use for sub-ms delta calculations
    """
    wall_time: datetime
    perf_ns: int
    weight_g: float


@dataclass
class IDA5Record:
    """One IDA5 poll cycle (FLOW + VOL queried back-to-back).

    Timestamps are captured immediately when readline() returns for the VOL
    response (the last query of the cycle), so perf_ns reflects the network
    round-trip latency of that final response.
    """
    wall_time: datetime
    perf_ns: int
    flow_ml_h: Optional[float]
    vol_ml: Optional[float]


@dataclass
class CombinedRecord:
    """Merged snapshot written to the CSV log and shown in the UI table.

    Each row carries the latest known value from *both* devices at the
    moment one device produced new data (source tells you which triggered it).
    """
    wall_time: datetime
    perf_ns: int
    weight_g: Optional[float]
    flow_ml_h: Optional[float]
    vol_ml: Optional[float]
    source: str  # "mettler" | "ida5" | "tick"

    def iso(self) -> str:
        # microsecond resolution — datetime.now() on Windows 10+ gives ~100 ns
        return self.wall_time.isoformat(timespec="microseconds")

    def as_csv_row(self) -> str:
        w = "" if self.weight_g  is None else f"{self.weight_g:.9f}"
        f = "" if self.flow_ml_h is None else f"{self.flow_ml_h:.6f}"
        v = "" if self.vol_ml    is None else f"{self.vol_ml:.6f}"
        return f"{self.iso()},{self.perf_ns},{self.source},{w},{f},{v}"
