import tkinter as tk
from tkinter import ttk
from typing import Callable

from config import (
    DEFAULT_METTLER_PORT, DEFAULT_METTLER_BAUD,
    DEFAULT_IDA_PORT, DEFAULT_IDA_BAUD,
    DEFAULT_IDA_CH, DEFAULT_PARAM_A, DEFAULT_PARAM_B, DEFAULT_PARAM_C,
)


class SettingsPanel(ttk.LabelFrame):
    """Connection settings + action buttons panel."""

    def __init__(
        self,
        parent,
        on_connect: Callable,
        on_disconnect: Callable,
        on_prime: Callable,
        on_after_prime: Callable,
        on_stop: Callable,
    ) -> None:
        super().__init__(parent, text="Connection & Control", padding=10)

        self.var_m_port = tk.StringVar(value=DEFAULT_METTLER_PORT)
        self.var_m_baud = tk.IntVar(value=DEFAULT_METTLER_BAUD)
        self.var_i_port = tk.StringVar(value=DEFAULT_IDA_PORT)
        self.var_i_baud = tk.IntVar(value=DEFAULT_IDA_BAUD)
        self.var_ch = tk.IntVar(value=DEFAULT_IDA_CH)
        self.var_a  = tk.StringVar(value=DEFAULT_PARAM_A)
        self.var_b  = tk.StringVar(value=DEFAULT_PARAM_B)
        self.var_c  = tk.StringVar(value=DEFAULT_PARAM_C)

        # Row 0 — port settings
        ttk.Label(self, text="Mettler COM").grid(row=0, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.var_m_port, width=8).grid(row=0, column=1, padx=4)
        ttk.Label(self, text="Baud").grid(row=0, column=2, sticky="w")
        ttk.Entry(self, textvariable=self.var_m_baud, width=8).grid(row=0, column=3, padx=4)
        ttk.Label(self, text="IDA COM").grid(row=0, column=4, sticky="w")
        ttk.Entry(self, textvariable=self.var_i_port, width=8).grid(row=0, column=5, padx=4)
        ttk.Label(self, text="Baud").grid(row=0, column=6, sticky="w")
        ttk.Entry(self, textvariable=self.var_i_baud, width=8).grid(row=0, column=7, padx=4)

        # Row 1 — IDA5 session parameters
        ttk.Label(self, text="CH").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(self, textvariable=self.var_ch, width=6).grid(row=1, column=1, padx=4, pady=(6, 0))
        ttk.Label(self, text="a").grid(row=1, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(self, textvariable=self.var_a, width=10).grid(row=1, column=3, padx=4, pady=(6, 0))
        ttk.Label(self, text="b").grid(row=1, column=4, sticky="w", pady=(6, 0))
        ttk.Entry(self, textvariable=self.var_b, width=12).grid(row=1, column=5, padx=4, pady=(6, 0))
        ttk.Label(self, text="c").grid(row=1, column=6, sticky="w", pady=(6, 0))
        ttk.Entry(self, textvariable=self.var_c, width=10).grid(row=1, column=7, padx=4, pady=(6, 0))

        # Connection buttons
        conn = ttk.Frame(self)
        conn.grid(row=0, column=8, rowspan=2, padx=10, sticky="ns")
        ttk.Button(conn, text="CONNECT",    command=on_connect).pack(fill=tk.X, pady=2)
        ttk.Button(conn, text="DISCONNECT", command=on_disconnect).pack(fill=tk.X, pady=2)

        # IDA5 workflow buttons
        ida = ttk.Frame(self)
        ida.grid(row=0, column=9, rowspan=2, padx=4, sticky="ns")
        ttk.Button(ida, text="CONNECT & PRIME", command=on_prime).pack(fill=tk.X, pady=2)
        ttk.Button(ida, text="AFTER PRIME",     command=on_after_prime).pack(fill=tk.X, pady=2)
        ttk.Button(ida, text="STOP IDA5",       command=on_stop).pack(fill=tk.X, pady=2)

    def get_config(self) -> dict:
        return {
            "m_port": self.var_m_port.get().strip(),
            "m_baud": int(self.var_m_baud.get()),
            "i_port": self.var_i_port.get().strip(),
            "i_baud": int(self.var_i_baud.get()),
            "ch": int(self.var_ch.get()),
            "a":  self.var_a.get().strip(),
            "b":  self.var_b.get().strip(),
            "c":  self.var_c.get().strip(),
        }
