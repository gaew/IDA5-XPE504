import time
import threading
from datetime import datetime
from typing import Optional, Callable, Tuple

import serial

from utils.parsers import FLOW_RE, VOL_RE, HEX_FRAME_RE
from core.record import IDA5Record
from config import POLL_IDA_SEC, IDA_RESPONSE_TIMEOUT


class IDA5Reader:
    """Background thread that polls the IDA5 infusion device analyser.

    Protocol: request-response (we send [FLOW,ch] / [VOL,ch], device replies).

    High-resolution timestamp strategy:
      readline() blocks until the terminating newline arrives.  We capture
      time.perf_counter_ns() + datetime.now() immediately after readline()
      returns — this timestamps the moment the last byte of the response
      cleared the UART driver, giving ≈ 1–5 ms accuracy (dominated by
      Windows USB-UART latency timer, not Python overhead).

      The original code timestamped at the 250 ms UI tick — up to 250 ms late.
      This implementation timestamps at data arrival: ~245 ms improvement.

    Thread safety:
      _io_lock serialises all serial I/O.  The polling loop (_run) and the
      UI-thread command helpers (send_command) both acquire _io_lock, so
      they can never interleave bytes on the wire.
    """

    def __init__(self, port: str, baud: int, on_record: Callable[[IDA5Record], None]) -> None:
        self._port = port
        self._baud = baud
        self._on_record = on_record
        self._ser: Optional[serial.Serial] = None
        self._io_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._channel = 1
        self.running = False   # set True by App after AFTER PRIME

    # ------------------------------------------------------------------ lifecycle

    def open(self) -> str:
        try:
            s = serial.Serial(
                port=self._port, baudrate=self._baud,
                bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=IDA_RESPONSE_TIMEOUT, write_timeout=0.5,
                rtscts=False, dsrdtr=False, xonxoff=False,
            )
            s.reset_input_buffer()
            with self._io_lock:
                self._ser = s
            return ""
        except Exception as e:
            return str(e)

    def close(self) -> None:
        with self._io_lock:
            s, self._ser = self._ser, None
        if s:
            try:
                s.close()
            except Exception:
                pass

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ida5-reader")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.running = False

    def set_channel(self, ch: int) -> None:
        self._channel = ch

    @property
    def is_open(self) -> bool:
        with self._io_lock:
            return self._ser is not None and self._ser.is_open

    # ------------------------------------------------------------------ public command interface (UI thread)

    def send_command(self, cmd: str, ending: str = "\r\n") -> Tuple[str, str]:
        """Send a raw command and return (cmd_sent, response_line).

        Blocks for up to IDA_RESPONSE_TIMEOUT seconds.
        Safe to call from any thread — serialised by _io_lock.
        """
        with self._io_lock:
            s = self._ser
            if not (s and s.is_open):
                return cmd, ""
            try:
                s.reset_input_buffer()
                s.write((cmd + ending).encode("ascii", errors="ignore"))
                s.flush()
                raw = s.readline()
                return cmd, raw.decode(errors="ignore").strip()
            except Exception as e:
                return cmd, f"ERROR:{e}"

    # ------------------------------------------------------------------ internal poll

    def _query(
        self, cmd: str, regex, group: str
    ) -> Tuple[Optional[float], int, datetime]:
        """Send a poll command and parse the first matching response line.

        Returns (value_or_None, perf_counter_ns, wall_datetime).
        Timestamp is captured the instant readline() returns — i.e. when
        the response byte stream was fully received.
        """
        with self._io_lock:
            s = self._ser
            if not (s and s.is_open):
                return None, time.perf_counter_ns(), datetime.now()
            try:
                s.reset_input_buffer()
                s.write((cmd + "\r\n").encode("ascii", errors="ignore"))
                s.flush()

                # Read up to 5 lines to skip hex-frame noise
                for _ in range(5):
                    raw = s.readline()

                    # --- HIGH RESOLUTION TIMESTAMP ---
                    # Captured immediately when readline() unblocks, before any parsing.
                    recv_ns   = time.perf_counter_ns()
                    recv_wall = datetime.now()
                    # ---------------------------------

                    if not raw:
                        break  # timeout — no more data
                    line = raw.decode(errors="ignore").strip()
                    if not line or HEX_FRAME_RE.match(line):
                        continue
                    m = regex.search(line)
                    if m:
                        return float(m.group(group)), recv_ns, recv_wall
            except Exception:
                pass
        return None, time.perf_counter_ns(), datetime.now()

    def _run(self) -> None:
        while not self._stop.is_set():
            if not self.running:
                time.sleep(0.05)
                continue

            ch = self._channel
            flow, flow_ns, flow_wall = self._query(f"[FLOW,{ch}]", FLOW_RE, "flow")
            vol,  vol_ns,  vol_wall  = self._query(f"[VOL,{ch}]",  VOL_RE,  "vol")

            if flow is not None or vol is not None:
                # Use the timestamp of the VOL response (last query in the cycle)
                # so the record reflects when the full pair of values was known.
                rec_ns   = vol_ns   if vol  is not None else flow_ns
                rec_wall = vol_wall if vol  is not None else flow_wall
                self._on_record(IDA5Record(
                    wall_time=rec_wall,
                    perf_ns=rec_ns,
                    flow_ml_h=flow,
                    vol_ml=vol,
                ))

            time.sleep(POLL_IDA_SEC)
