import re
import time
import threading
from datetime import datetime
from typing import Optional, Callable

import serial

from utils.parsers import parse_weight_line
from core.record import WeightRecord
from config import METTLER_POLL_SLEEP


class MettlerReader:
    """Background thread that reads weight lines from the Mettler scale.

    The Mettler pushes data continuously (no request needed).  We poll
    in_waiting at 2 ms intervals and timestamp the moment bytes appear in
    the OS receive buffer — this gives ≈ 2 ms timestamp accuracy, far better
    than the original 250 ms UI-tick approach.

    High-resolution timestamp strategy:
      1. Spin on s.in_waiting every METTLER_POLL_SLEEP seconds.
      2. The instant in_waiting > 0, capture time.perf_counter_ns() and
         datetime.now() BEFORE calling s.read() — these are the closest
         Python can get to the true hardware arrival time.
      3. Store both in WeightRecord so callers can compute sub-ms deltas
         via perf_ns while still having an absolute wall_time for logging.
    """

    def __init__(self, port: str, baud: int, on_record: Callable[[WeightRecord], None]) -> None:
        self._port = port
        self._baud = baud
        self._on_record = on_record
        self._ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ lifecycle

    def open(self) -> str:
        """Open the serial port. Returns empty string on success, error text otherwise."""
        try:
            s = serial.Serial(
                port=self._port, baudrate=self._baud,
                bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.05, write_timeout=0.5,
                rtscts=False, dsrdtr=False, xonxoff=False,
            )
            s.reset_input_buffer()
            with self._lock:
                self._ser = s
            return ""
        except Exception as e:
            return str(e)

    def close(self) -> None:
        with self._lock:
            s, self._ser = self._ser, None
        if s:
            try:
                s.close()
            except Exception:
                pass

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="mettler-reader")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._ser is not None and self._ser.is_open

    # ------------------------------------------------------------------ reader loop

    def _run(self) -> None:
        buf = ""
        while not self._stop.is_set():
            with self._lock:
                s = self._ser
            if not (s and s.is_open):
                time.sleep(METTLER_POLL_SLEEP)
                continue
            try:
                waiting = s.in_waiting
                if not waiting:
                    time.sleep(METTLER_POLL_SLEEP)
                    continue

                # --- HIGH RESOLUTION TIMESTAMP ---
                # Captured the instant we detect bytes in the OS receive buffer,
                # before the read() call adds any latency.
                recv_ns   = time.perf_counter_ns()
                recv_wall = datetime.now()
                # ---------------------------------

                chunk = s.read(waiting)
                buf += chunk.decode("ascii", errors="ignore")
                parts = re.split(r"[\r\n]+", buf)
                buf = parts[-1]  # keep incomplete tail

                for line in parts[:-1]:
                    line = line.strip()
                    if not line:
                        continue
                    w = parse_weight_line(line)
                    if w is not None:
                        self._on_record(WeightRecord(
                            wall_time=recv_wall,
                            perf_ns=recv_ns,
                            weight_g=w,
                        ))
            except Exception:
                time.sleep(0.05)
