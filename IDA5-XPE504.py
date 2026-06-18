import re
import time
import threading
from collections import deque
from datetime import datetime

import serial
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


DEFAULT_METTLER_PORT = "COM8"
DEFAULT_METTLER_BAUD = 9600

DEFAULT_IDA_PORT = "COM11"
DEFAULT_IDA_BAUD = 115200

DEFAULT_IDA_CH = 1
DEFAULT_A = "1"
DEFAULT_B = "kaew"
DEFAULT_C = "100"

POLL_SEC = 0.5
UI_REFRESH_MS = 250
MAX_POINTS = 600
TABLE_ROWS = 35


WEIGHT_RE = re.compile(r"(?P<value>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>mg|g|kg)\b", re.IGNORECASE)
VOL_RE = re.compile(r"\[\s*VOL\s*,\s*(?P<vol>\d+\.\d+)", re.IGNORECASE)
FLOW_RE = re.compile(r"\[\s*FLOW\s*,\s*(?P<flow>\d+\.\d+)", re.IGNORECASE)
HEX_FRAME_RE = re.compile(r"^\d+:[0-9A-Fa-f]+$")


def to_grams(value: float, unit: str) -> float:
    u = unit.lower()
    if u == "mg":
        return value / 1000.0
    if u == "kg":
        return value * 1000.0
    return value


def is_nan(x: float) -> bool:
    return x != x


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mettler + IDA5 Dashboard")
        self.geometry("1320x840")

        self.mettler = None
        self.ida = None
        self.ser_lock = threading.Lock()
        self.stop_event = threading.Event()

        self.running_ida = False
        self.connected = False

        self.latest_weight_g = None
        self.latest_vol = None
        self.latest_flow = None

        self.last_tx = "-"
        self.last_rx = "-"

        self.times = deque(maxlen=MAX_POINTS)
        self.weights = deque(maxlen=MAX_POINTS)
        self.vols = deque(maxlen=MAX_POINTS)
        self.flows = deque(maxlen=MAX_POINTS)

        self.logging = False
        self.log_lines = []
        self._threads_started = False

        self._build_ui()
        self.after(UI_REFRESH_MS, self._ui_tick)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)

        self.status_var = tk.StringVar(value="DISCONNECTED")
        self.last_var = tk.StringVar(value="Weight: - | Flow: - | Vol: -")
        self.tx_var = tk.StringVar(value="Last TX: -")
        self.rx_var = tk.StringVar(value="Last RX: -")

        ttk.Label(top, textvariable=self.status_var).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(top, textvariable=self.last_var).pack(side=tk.LEFT)

        info = ttk.Frame(self, padding=(10, 0, 10, 10))
        info.pack(fill=tk.X)
        ttk.Label(info, textvariable=self.tx_var).pack(anchor="w")
        ttk.Label(info, textvariable=self.rx_var).pack(anchor="w")

        cfg = ttk.LabelFrame(self, text="Connection Settings", padding=10)
        cfg.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.var_m_port = tk.StringVar(value=DEFAULT_METTLER_PORT)
        self.var_m_baud = tk.IntVar(value=DEFAULT_METTLER_BAUD)
        self.var_i_port = tk.StringVar(value=DEFAULT_IDA_PORT)
        self.var_i_baud = tk.IntVar(value=DEFAULT_IDA_BAUD)

        self.var_ch = tk.IntVar(value=DEFAULT_IDA_CH)
        self.var_a = tk.StringVar(value=DEFAULT_A)
        self.var_b = tk.StringVar(value=DEFAULT_B)
        self.var_c = tk.StringVar(value=DEFAULT_C)

        ttk.Label(cfg, text="Mettler COM").grid(row=0, column=0, sticky="w")
        ttk.Entry(cfg, textvariable=self.var_m_port, width=10).grid(row=0, column=1, padx=6)
        ttk.Label(cfg, text="Baud").grid(row=0, column=2, sticky="w")
        ttk.Entry(cfg, textvariable=self.var_m_baud, width=8).grid(row=0, column=3, padx=6)

        ttk.Label(cfg, text="IDA COM").grid(row=0, column=4, sticky="w")
        ttk.Entry(cfg, textvariable=self.var_i_port, width=10).grid(row=0, column=5, padx=6)
        ttk.Label(cfg, text="Baud").grid(row=0, column=6, sticky="w")
        ttk.Entry(cfg, textvariable=self.var_i_baud, width=8).grid(row=0, column=7, padx=6)

        ttk.Label(cfg, text="IDA CH").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(cfg, textvariable=self.var_ch, width=6).grid(row=1, column=1, padx=6, pady=(6, 0))

        ttk.Label(cfg, text="a").grid(row=1, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(cfg, textvariable=self.var_a, width=10).grid(row=1, column=3, padx=6, pady=(6, 0))

        ttk.Label(cfg, text="b").grid(row=1, column=4, sticky="w", pady=(6, 0))
        ttk.Entry(cfg, textvariable=self.var_b, width=12).grid(row=1, column=5, padx=6, pady=(6, 0))

        ttk.Label(cfg, text="c").grid(row=1, column=6, sticky="w", pady=(6, 0))
        ttk.Entry(cfg, textvariable=self.var_c, width=10).grid(row=1, column=7, padx=6, pady=(6, 0))

        btns = ttk.Frame(cfg)
        btns.grid(row=0, column=8, rowspan=2, padx=12)

        ttk.Button(btns, text="CONNECT", command=self.connect_only).pack(fill=tk.X, pady=(0, 6))
        ttk.Button(btns, text="DISCONNECT", command=self.disconnect).pack(fill=tk.X)

        act = ttk.Frame(self, padding=(10, 0, 10, 10))
        act.pack(fill=tk.X)

        ttk.Button(act, text="CONNECT & PRIME", command=self.connect_and_prime).pack(side=tk.LEFT, padx=5)
        ttk.Button(act, text="AFTER PRIME", command=self.after_prime).pack(side=tk.LEFT, padx=5)
        ttk.Button(act, text="STOP", command=self.stop_ida).pack(side=tk.LEFT, padx=5)

        ttk.Separator(act, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=10)

        self.btn_log_start = ttk.Button(act, text="START LOG", command=self.start_log)
        self.btn_log_stop = ttk.Button(act, text="STOP & SAVE", command=self.stop_and_save, state=tk.DISABLED)
        self.btn_log_start.pack(side=tk.LEFT, padx=5)
        self.btn_log_stop.pack(side=tk.LEFT, padx=5)

        mid = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        mid.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        left = ttk.Frame(mid, padding=(0, 0, 10, 0))
        mid.add(left, weight=1)

        ttk.Label(left, text="Table (latest on top)").pack(anchor="w")

        cols = ("time", "weight_g", "flow_ml_h", "vol_ml")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=TABLE_ROWS)

        self.tree.heading("time", text="Time")
        self.tree.heading("weight_g", text="Weight (g)")
        self.tree.heading("flow_ml_h", text="Flow (ml/h)")
        self.tree.heading("vol_ml", text="Vol (ml)")

        self.tree.column("time", width=180, anchor="w")
        self.tree.column("weight_g", width=120, anchor="e")
        self.tree.column("flow_ml_h", width=120, anchor="e")
        self.tree.column("vol_ml", width=120, anchor="e")

        yscroll = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)

        right = ttk.Frame(mid)
        mid.add(right, weight=1)

        ttk.Label(right, text="Graph (Weight + Flow + Vol)").pack(anchor="w")

        self.fig = Figure(figsize=(6.2, 4.3), dpi=100)
        self.ax_w = self.fig.add_subplot(111)
        self.ax_f = self.ax_w.twinx()
        self.ax_v = self.ax_w.twinx()
        self.ax_v.spines["right"].set_position(("axes", 1.12))
        self.ax_v.spines["right"].set_visible(True)

        self.ax_w.set_xlabel("Time (s)")
        self.ax_w.set_ylabel("Weight (g)")
        self.ax_f.set_ylabel("Flow (ml/h)")
        self.ax_v.set_ylabel("Vol (ml)")

        self.line_w, = self.ax_w.plot([], [], color="tab:blue", linewidth=2, label="Weight (g)")
        self.line_f, = self.ax_f.plot([], [], color="tab:orange", linewidth=2, label="Flow (ml/h)")
        self.line_v, = self.ax_v.plot([], [], color="tab:green", linewidth=2, label="Vol (ml)")

        self.ax_w.yaxis.label.set_color("tab:blue")
        self.ax_f.yaxis.label.set_color("tab:orange")
        self.ax_v.yaxis.label.set_color("tab:green")
        self.ax_w.grid(True, alpha=0.3)

        handles = [self.line_w, self.line_f, self.line_v]
        self.ax_w.legend(handles, [h.get_label() for h in handles], loc="upper left")

        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def connect_only(self):
        self._open_ports()

    def connect_and_prime(self):
        self._open_ports()
        if not (self.ida and self.ida.is_open):
            return

        try:
            self.send_ida("[POLL]", ending="\r\n")
            time.sleep(0.5)
            self.read_ida_line()

            ch = self.var_ch.get()
            a = self.var_a.get().strip()
            b = self.var_b.get().strip()
            c = self.var_c.get().strip()

            self.send_ida(f"[C{ch}F,{a},{b},{c}]", ending="\r\n")
            time.sleep(0.8)
            self.read_ida_line()

            self.status_var.set("CONNECTED | PRIME NOW ON IDA5")
        except Exception as e:
            messagebox.showerror("IDA Error", str(e))

    def after_prime(self):
        if not (self.ida and self.ida.is_open):
            messagebox.showwarning("Warning", "Please connect first.")
            return

        try:
            ch = self.var_ch.get()
            a = self.var_a.get().strip()
            b = self.var_b.get().strip()
            c = self.var_c.get().strip()

            self.send_ida(f"[C{ch}F,{a},{b},{c}]", ending="\r\n")
            time.sleep(0.8)
            self.read_ida_line()

            self.running_ida = True
            self.status_var.set("CONNECTED | IDA RUNNING")
        except Exception as e:
            messagebox.showerror("IDA Error", str(e))

    def stop_ida(self):
        self.running_ida = False
        try:
            ch = self.var_ch.get()
            self.send_ida(f"[END,{ch}]", ending="\r\n")
            time.sleep(0.3)
            self.read_ida_line()
        except Exception:
            pass
        self.status_var.set("CONNECTED | IDA STOPPED")

    def _open_ports(self):
        self.disconnect()

        m_port = self.var_m_port.get().strip()
        m_baud = int(self.var_m_baud.get())
        i_port = self.var_i_port.get().strip()
        i_baud = int(self.var_i_baud.get())

        try:
            self.mettler = serial.Serial(
                port=m_port,
                baudrate=m_baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.05,
                write_timeout=0.5,
                rtscts=False,
                dsrdtr=False,
                xonxoff=False,
            )
            self.mettler.reset_input_buffer()
        except Exception as e:
            self.mettler = None
            messagebox.showerror("Serial Error", f"Cannot open Mettler {m_port}: {e}")

        try:
            self.ida = serial.Serial(
                port=i_port,
                baudrate=i_baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0,
                write_timeout=0.5,
                rtscts=False,
                dsrdtr=False,
                xonxoff=False,
            )
            self.ida.reset_input_buffer()
        except Exception as e:
            self.ida = None
            messagebox.showerror("Serial Error", f"Cannot open IDA {i_port}: {e}")

        ok_m = self.mettler is not None and self.mettler.is_open
        ok_i = self.ida is not None and self.ida.is_open
        self.connected = ok_m or ok_i
        self.status_var.set(f"Status: Mettler={'OK' if ok_m else 'NO'} | IDA={'OK' if ok_i else 'NO'}")

        if not self._threads_started:
            self._threads_started = True
            threading.Thread(target=self.reader_mettler, daemon=True).start()
            threading.Thread(target=self.reader_ida, daemon=True).start()

    def disconnect(self):
        self.running_ida = False
        with self.ser_lock:
            try:
                if self.mettler and self.mettler.is_open:
                    self.mettler.close()
            except Exception:
                pass
            try:
                if self.ida and self.ida.is_open:
                    self.ida.close()
            except Exception:
                pass
            self.mettler = None
            self.ida = None

        self.connected = False
        self.status_var.set("DISCONNECTED")

    def send_ida(self, cmd, ending="\r\n"):
        with self.ser_lock:
            if not (self.ida and self.ida.is_open):
                return
            self.ida.write((cmd + ending).encode("ascii", errors="ignore"))
            self.ida.flush()
            self.last_tx = f"{cmd} [{repr(ending)}]"
            self.tx_var.set(f"Last TX: {self.last_tx}")

    def read_ida_line(self):
        with self.ser_lock:
            if not (self.ida and self.ida.is_open):
                return ""
            line = self.ida.readline().decode(errors="ignore").strip()
        if line:
            self.last_rx = line
            self.rx_var.set(f"Last RX: {line}")
        return line

    def reader_mettler(self):
        buf = ""
        while not self.stop_event.is_set():
            try:
                with self.ser_lock:
                    s = self.mettler
                if not (s and s.is_open):
                    time.sleep(0.05)
                    continue

                n = s.in_waiting
                chunk = s.read(n if n else 1)
                if not chunk:
                    time.sleep(0.01)
                    continue

                buf += chunk.decode("ascii", errors="ignore")
                parts = re.split(r"[\r\n]+", buf)
                buf = parts[-1]

                for line in parts[:-1]:
                    line = line.strip()
                    if not line:
                        continue
                    m = WEIGHT_RE.search(line)
                    if m:
                        self.latest_weight_g = to_grams(float(m.group("value")), m.group("unit"))
            except Exception:
                time.sleep(0.1)

    def _read_ida_value(self, cmd, regex, group_name):
        self.send_ida(cmd, ending="\r\n")
        t_end = time.time() + 1.0

        while time.time() < t_end:
            line = self.read_ida_line()

            if not line:
                continue

            if HEX_FRAME_RE.match(line):
                continue

            m = regex.search(line)
            if m:
                return float(m.group(group_name))

        return None

    def reader_ida(self):
        last_vol = None
        last_flow = None

        while not self.stop_event.is_set():
            try:
                if not self.running_ida:
                    time.sleep(0.1)
                    continue

                ch = self.var_ch.get()

                flow = self._read_ida_value(f"[FLOW,{ch}]", FLOW_RE, "flow")
                if flow is not None and flow != last_flow:
                    self.latest_flow = flow
                    last_flow = flow

                vol = self._read_ida_value(f"[VOL,{ch}]", VOL_RE, "vol")
                if vol is not None and vol != last_vol:
                    self.latest_vol = vol
                    last_vol = vol

            except Exception:
                time.sleep(0.2)

            time.sleep(POLL_SEC)

    def start_log(self):
        self.logging = True
        self.log_lines = ["timestamp_iso,weight_g,flow_ml_h,vol_ml"]
        self.btn_log_start.config(state=tk.DISABLED)
        self.btn_log_stop.config(state=tk.NORMAL)

    def stop_and_save(self):
        self.logging = False
        self.btn_log_start.config(state=tk.NORMAL)
        self.btn_log_stop.config(state=tk.DISABLED)

        if len(self.log_lines) <= 1:
            messagebox.showinfo("Info", "Log is empty (no data).")
            return

        default_name = f"METTLER_IDA5_LOG_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[("Text/CSV", "*.txt *.csv"), ("All files", "*.*")]
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.log_lines))
        messagebox.showinfo("Saved", f"Saved log to:\n{path}")

    def _ui_tick(self):
        w = self.latest_weight_g
        f = self.latest_flow
        v = self.latest_vol

        wtxt = f"{w:.6f} g" if w is not None else "-"
        ftxt = f"{f:.2f} ml/h" if f is not None else "-"
        vtxt = f"{v:.2f} ml" if v is not None else "-"
        self.last_var.set(f"Weight={wtxt} | Flow={ftxt} | Vol={vtxt}")

        ts = datetime.now()
        self.times.append(ts)
        self.weights.append(w if w is not None else float("nan"))
        self.flows.append(f if f is not None else float("nan"))
        self.vols.append(v if v is not None else float("nan"))

        if self.logging:
            iso = ts.isoformat(timespec="milliseconds")
            wg = "" if w is None else f"{w:.9f}"
            fm = "" if f is None else f"{f:.6f}"
            vm = "" if v is None else f"{v:.6f}"
            self.log_lines.append(f"{iso},{wg},{fm},{vm}")

        for item in self.tree.get_children():
            self.tree.delete(item)

        n = min(TABLE_ROWS, len(self.times))
        for i in range(1, n + 1):
            t = self.times[-i].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            wg = self.weights[-i]
            fl = self.flows[-i]
            vv = self.vols[-i]

            wg_txt = "-" if is_nan(wg) else f"{wg:.6f}"
            fl_txt = "-" if is_nan(fl) else f"{fl:.2f}"
            vv_txt = "-" if is_nan(vv) else f"{vv:.2f}"

            self.tree.insert("", "end", values=(t, wg_txt, fl_txt, vv_txt))

        if len(self.times) >= 2:
            t0 = self.times[0]
            xs = [(t - t0).total_seconds() for t in self.times]

            self.line_w.set_data(xs, list(self.weights))
            self.line_f.set_data(xs, list(self.flows))
            self.line_v.set_data(xs, list(self.vols))

            self.ax_w.relim()
            self.ax_w.autoscale_view()
            self.ax_f.relim()
            self.ax_f.autoscale_view()
            self.ax_v.relim()
            self.ax_v.autoscale_view()

            self.canvas.draw_idle()

        self.after(UI_REFRESH_MS, self._ui_tick)

    def _on_close(self):
        self.stop_event.set()
        self.disconnect()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()