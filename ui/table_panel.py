import math
import tkinter as tk
from tkinter import ttk
from typing import List

from core.record import CombinedRecord
from config import TABLE_ROWS


class TablePanel(ttk.Frame):
    """Live data table showing the most recent CombinedRecords.

    Time column displays microsecond precision (datetime.strftime %f gives 6 digits).
    Source column shows which device triggered the row: "mettler" or "ida5".
    """

    def __init__(self, parent) -> None:
        super().__init__(parent, padding=(0, 0, 10, 0))

        ttk.Label(self, text="Log  (latest on top — µs-precision timestamps)").pack(anchor="w")

        cols = ("time", "source", "weight_g", "flow_ml_h", "vol_ml")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=TABLE_ROWS)

        self.tree.heading("time",      text="Timestamp (µs)")
        self.tree.heading("source",    text="Source")
        self.tree.heading("weight_g",  text="Weight (g)")
        self.tree.heading("flow_ml_h", text="Flow (ml/h)")
        self.tree.heading("vol_ml",    text="Vol (ml)")

        self.tree.column("time",      width=230, anchor="w")
        self.tree.column("source",    width=65,  anchor="center")
        self.tree.column("weight_g",  width=115, anchor="e")
        self.tree.column("flow_ml_h", width=110, anchor="e")
        self.tree.column("vol_ml",    width=100, anchor="e")

        sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    @staticmethod
    def _fmt(v, decimals: int = 6) -> str:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return "-"
        return f"{v:.{decimals}f}"

    def refresh(self, records: List[CombinedRecord]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        n = min(TABLE_ROWS, len(records))
        for i in range(1, n + 1):
            r = records[-i]
            # %f gives 6-digit microseconds; full format: YYYY-MM-DD HH:MM:SS.ffffff
            t = r.wall_time.strftime("%Y-%m-%d %H:%M:%S.%f")
            self.tree.insert("", "end", values=(
                t,
                r.source,
                self._fmt(r.weight_g, 6),
                self._fmt(r.flow_ml_h, 2),
                self._fmt(r.vol_ml, 2),
            ))
