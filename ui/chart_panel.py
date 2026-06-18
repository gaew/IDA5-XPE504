from typing import List

import tkinter as tk
from tkinter import ttk

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from core.record import WeightRecord, IDA5Record


class ChartPanel(ttk.Frame):
    """Live triple-axis chart: Weight (blue), Flow (orange), Vol (green).

    X-axis is seconds since the first data point across both sources.
    Weight and IDA5 have separate ring buffers, so each axis can have
    different densities (e.g. weight at 10 Hz, IDA5 at 5 Hz).
    """

    def __init__(self, parent) -> None:
        super().__init__(parent)
        ttk.Label(self, text="Graph  (Weight / Flow / Vol — shared time axis)").pack(anchor="w")

        fig = Figure(figsize=(6.2, 4.3), dpi=100)
        self.ax_w = fig.add_subplot(111)
        self.ax_f = self.ax_w.twinx()
        self.ax_v = self.ax_w.twinx()
        self.ax_v.spines["right"].set_position(("axes", 1.12))
        self.ax_v.spines["right"].set_visible(True)

        self.ax_w.set_xlabel("Time (s)")
        self.ax_w.set_ylabel("Weight (g)",  color="tab:blue")
        self.ax_f.set_ylabel("Flow (ml/h)", color="tab:orange")
        self.ax_v.set_ylabel("Vol (ml)",    color="tab:green")
        self.ax_w.grid(True, alpha=0.3)

        self.line_w, = self.ax_w.plot([], [], color="tab:blue",   lw=2, label="Weight (g)")
        self.line_f, = self.ax_f.plot([], [], color="tab:orange", lw=2, label="Flow (ml/h)")
        self.line_v, = self.ax_v.plot([], [], color="tab:green",  lw=2, label="Vol (ml)")

        handles = [self.line_w, self.line_f, self.line_v]
        self.ax_w.legend(handles, [h.get_label() for h in handles], loc="upper left")

        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def refresh(self, weight_buf: List[WeightRecord], ida_buf: List[IDA5Record]) -> None:
        if not weight_buf and not ida_buf:
            return

        # Global time reference = earliest timestamp across both sources
        t_ref = None
        if weight_buf:
            t_ref = weight_buf[0].wall_time
        if ida_buf:
            t0_ida = ida_buf[0].wall_time
            t_ref = t0_ida if t_ref is None else min(t_ref, t0_ida)

        def secs(wall_time):
            return (wall_time - t_ref).total_seconds()

        wx = [secs(r.wall_time) for r in weight_buf]
        wy = [r.weight_g for r in weight_buf]

        fx = [secs(r.wall_time) for r in ida_buf if r.flow_ml_h is not None]
        fy = [r.flow_ml_h       for r in ida_buf if r.flow_ml_h is not None]
        vx = [secs(r.wall_time) for r in ida_buf if r.vol_ml    is not None]
        vy = [r.vol_ml           for r in ida_buf if r.vol_ml    is not None]

        self.line_w.set_data(wx, wy)
        self.line_f.set_data(fx, fy)
        self.line_v.set_data(vx, vy)

        for ax in (self.ax_w, self.ax_f, self.ax_v):
            ax.relim()
            ax.autoscale_view()

        self.canvas.draw_idle()
