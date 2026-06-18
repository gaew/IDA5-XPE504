import threading
from collections import deque
from typing import Optional, Callable, Tuple, List

from core.record import WeightRecord, IDA5Record, CombinedRecord
from utils.csv_logger import CSV_HEADER
from config import MAX_POINTS


class DataHub:
    """Thread-safe shared state between serial reader threads and the UI thread.

    Reader threads call push_weight() / push_ida5() — these are the only writers.
    The UI thread calls snapshot() / snapshot_chart_data() — read-only copies.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        self.latest_weight: Optional[WeightRecord] = None
        self.latest_ida:    Optional[IDA5Record]   = None

        # Per-source ring buffers used by the chart
        self.weight_buf: deque = deque(maxlen=MAX_POINTS)
        self.ida_buf:    deque = deque(maxlen=MAX_POINTS)

        # Combined ring buffer used by the table (every new event appends a row)
        self.combined_buf: deque = deque(maxlen=MAX_POINTS)

        # CSV log
        self.logging: bool = False
        self._log_lines: List[str] = [CSV_HEADER]

    # ------------------------------------------------------------------ writers (called from reader threads)

    def push_weight(self, rec: WeightRecord) -> None:
        with self._lock:
            self.latest_weight = rec
            self.weight_buf.append(rec)
            combined = CombinedRecord(
                wall_time=rec.wall_time,
                perf_ns=rec.perf_ns,
                weight_g=rec.weight_g,
                flow_ml_h=self.latest_ida.flow_ml_h if self.latest_ida else None,
                vol_ml=self.latest_ida.vol_ml        if self.latest_ida else None,
                source="mettler",
            )
            self.combined_buf.append(combined)
            if self.logging:
                self._log_lines.append(combined.as_csv_row())

    def push_ida5(self, rec: IDA5Record) -> None:
        with self._lock:
            self.latest_ida = rec
            self.ida_buf.append(rec)
            combined = CombinedRecord(
                wall_time=rec.wall_time,
                perf_ns=rec.perf_ns,
                weight_g=self.latest_weight.weight_g if self.latest_weight else None,
                flow_ml_h=rec.flow_ml_h,
                vol_ml=rec.vol_ml,
                source="ida5",
            )
            self.combined_buf.append(combined)
            if self.logging:
                self._log_lines.append(combined.as_csv_row())

    # ------------------------------------------------------------------ logging control (called from UI thread)

    def start_log(self) -> None:
        with self._lock:
            self.logging = True
            self._log_lines = [CSV_HEADER]

    def stop_log(self) -> List[str]:
        with self._lock:
            self.logging = False
            return list(self._log_lines)

    # ------------------------------------------------------------------ readers (called from UI thread)

    def snapshot(self) -> Tuple[Optional[WeightRecord], Optional[IDA5Record], List[CombinedRecord]]:
        """Consistent snapshot of latest values + combined table buffer."""
        with self._lock:
            return self.latest_weight, self.latest_ida, list(self.combined_buf)

    def snapshot_chart_data(self) -> Tuple[List[WeightRecord], List[IDA5Record]]:
        """Copies of per-source ring buffers for chart rendering."""
        with self._lock:
            return list(self.weight_buf), list(self.ida_buf)
