from pathlib import Path

CSV_HEADER = "timestamp_iso,perf_counter_ns,source,weight_g,flow_ml_h,vol_ml"


def save_csv(lines: list, path: str) -> None:
    Path(path).write_text("\n".join(lines), encoding="utf-8")
