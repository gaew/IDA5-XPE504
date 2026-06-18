import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from typing import Optional

from core.data_hub import DataHub
from core.mettler_reader import MettlerReader
from core.ida5_reader import IDA5Reader
from ui.settings_panel import SettingsPanel
from ui.table_panel import TablePanel
from ui.chart_panel import ChartPanel
from utils.csv_logger import save_csv
from config import UI_REFRESH_MS


class App(tk.Tk):
    """Main application window.

    Wires together:
      DataHub   — thread-safe shared state
      MettlerReader  — pushes WeightRecord to hub.push_weight()
      IDA5Reader     — pushes IDA5Record   to hub.push_ida5()
      SettingsPanel  — connection/control UI
      TablePanel     — live table (refreshed by _tick)
      ChartPanel     — live chart  (refreshed by _tick)
    """

    def __init__(self) -> None:
        super().__init__()
        self.title("Mettler + IDA5 Dashboard  —  high-resolution timestamps")
        self.geometry("1420x860")

        self.hub = DataHub()
        self.mettler: Optional[MettlerReader] = None
        self.ida5: Optional[IDA5Reader] = None

        self._build_ui()
        self.after(UI_REFRESH_MS, self._tick)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI construction

    def _build_ui(self) -> None:
        # Status / reading bar
        top = ttk.Frame(self, padding=(10, 6))
        top.pack(fill=tk.X)
        self.status_var  = tk.StringVar(value="DISCONNECTED")
        self.reading_var = tk.StringVar(value="Weight: -  |  Flow: -  |  Vol: -")
        ttk.Label(top, textvariable=self.status_var, font=("", 10, "bold")).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(top, textvariable=self.reading_var).pack(side=tk.LEFT)

        # Last TX / RX display
        comms = ttk.Frame(self, padding=(10, 0, 10, 4))
        comms.pack(fill=tk.X)
        self.tx_var = tk.StringVar(value="TX: -")
        self.rx_var = tk.StringVar(value="RX: -")
        ttk.Label(comms, textvariable=self.tx_var).pack(anchor="w")
        ttk.Label(comms, textvariable=self.rx_var).pack(anchor="w")

        # Settings + control panel
        self.settings = SettingsPanel(
            self,
            on_connect=self._connect,
            on_disconnect=self._disconnect,
            on_prime=self._connect_and_prime,
            on_after_prime=self._after_prime,
            on_stop=self._stop_ida,
        )
        self.settings.pack(fill=tk.X, padx=10, pady=(0, 6))

        # Logging controls
        log_bar = ttk.Frame(self, padding=(10, 0, 10, 6))
        log_bar.pack(fill=tk.X)
        self.btn_start_log = ttk.Button(log_bar, text="START LOG",   command=self._start_log)
        self.btn_stop_log  = ttk.Button(log_bar, text="STOP & SAVE", command=self._stop_save_log,
                                        state=tk.DISABLED)
        self.btn_start_log.pack(side=tk.LEFT, padx=5)
        self.btn_stop_log.pack(side=tk.LEFT, padx=5)

        # Main content: table (left) + chart (right)
        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.table = TablePanel(pane)
        pane.add(self.table, weight=1)
        self.chart = ChartPanel(pane)
        pane.add(self.chart, weight=1)

    # ------------------------------------------------------------------ connection handlers

    def _connect(self) -> None:
        self._open_ports()

    def _disconnect(self) -> None:
        if self.mettler:
            self.mettler.stop()
            self.mettler.close()
            self.mettler = None
        if self.ida5:
            self.ida5.stop()
            self.ida5.close()
            self.ida5 = None
        self.status_var.set("DISCONNECTED")

    def _open_ports(self) -> None:
        self._disconnect()
        cfg = self.settings.get_config()

        self.mettler = MettlerReader(cfg["m_port"], cfg["m_baud"], self.hub.push_weight)
        err_m = self.mettler.open()
        if err_m:
            messagebox.showerror("Mettler", f"Cannot open {cfg['m_port']}:\n{err_m}")
            self.mettler = None

        self.ida5 = IDA5Reader(cfg["i_port"], cfg["i_baud"], self.hub.push_ida5)
        err_i = self.ida5.open()
        if err_i:
            messagebox.showerror("IDA5", f"Cannot open {cfg['i_port']}:\n{err_i}")
            self.ida5 = None

        ok_m = self.mettler is not None and self.mettler.is_open
        ok_i = self.ida5   is not None and self.ida5.is_open
        self.status_var.set(f"Mettler={'OK' if ok_m else 'NO'}  |  IDA5={'OK' if ok_i else 'NO'}")

        if self.mettler:
            self.mettler.start()
        if self.ida5:
            self.ida5.start()

    def _connect_and_prime(self) -> None:
        self._open_ports()
        if not (self.ida5 and self.ida5.is_open):
            return
        cfg = self.settings.get_config()
        ch, a, b, c = cfg["ch"], cfg["a"], cfg["b"], cfg["c"]

        tx, rx = self.ida5.send_command("[POLL]")
        self._show_comms(tx, rx)

        tx, rx = self.ida5.send_command(f"[C{ch}F,{a},{b},{c}]")
        self._show_comms(tx, rx)
        self.status_var.set("CONNECTED  |  PRIME NOW ON IDA5")

    def _after_prime(self) -> None:
        if not (self.ida5 and self.ida5.is_open):
            messagebox.showwarning("Not Connected", "Connect first.")
            return
        cfg = self.settings.get_config()
        ch, a, b, c = cfg["ch"], cfg["a"], cfg["b"], cfg["c"]

        tx, rx = self.ida5.send_command(f"[C{ch}F,{a},{b},{c}]")
        self._show_comms(tx, rx)
        self.ida5.set_channel(ch)
        self.ida5.running = True
        self.status_var.set("CONNECTED  |  IDA5 RUNNING")

    def _stop_ida(self) -> None:
        if self.ida5:
            self.ida5.running = False
            cfg = self.settings.get_config()
            tx, rx = self.ida5.send_command(f"[END,{cfg['ch']}]")
            self._show_comms(tx, rx)
        self.status_var.set("CONNECTED  |  IDA5 STOPPED")

    def _show_comms(self, tx: str, rx: str) -> None:
        self.tx_var.set(f"TX: {tx}")
        self.rx_var.set(f"RX: {rx}")

    # ------------------------------------------------------------------ logging handlers

    def _start_log(self) -> None:
        self.hub.start_log()
        self.btn_start_log.config(state=tk.DISABLED)
        self.btn_stop_log.config(state=tk.NORMAL)

    def _stop_save_log(self) -> None:
        lines = self.hub.stop_log()
        self.btn_start_log.config(state=tk.NORMAL)
        self.btn_stop_log.config(state=tk.DISABLED)

        if len(lines) <= 1:
            messagebox.showinfo("Log", "No data recorded.")
            return

        default = f"IDA5_LOG_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        save_csv(lines, path)
        messagebox.showinfo("Saved", f"Log saved:\n{path}")

    # ------------------------------------------------------------------ UI refresh tick

    def _tick(self) -> None:
        latest_w, latest_ida, combined = self.hub.snapshot()

        w_txt = f"{latest_w.weight_g:.6f} g"                                   if latest_w  else "-"
        f_txt = f"{latest_ida.flow_ml_h:.2f} ml/h" if latest_ida and latest_ida.flow_ml_h is not None else "-"
        v_txt = f"{latest_ida.vol_ml:.2f} ml"       if latest_ida and latest_ida.vol_ml    is not None else "-"
        self.reading_var.set(f"Weight={w_txt}  |  Flow={f_txt}  |  Vol={v_txt}")

        self.table.refresh(combined)

        wb, ib = self.hub.snapshot_chart_data()
        self.chart.refresh(wb, ib)

        self.after(UI_REFRESH_MS, self._tick)

    # ------------------------------------------------------------------ window close

    def _on_close(self) -> None:
        self._disconnect()
        self.destroy()
