import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Stats:
    generation_elapsed_time: float = 0.0
    err_check_sat_elapsed_time: float = 0.0
    lof_check_sat_elapsed_time: float = 0.0
    oom_check_sat_elapsed_time: float = 0.0
    smt2_err_scripts_dumping_elpased_time: float = 0.0
    smt2_lof_scripts_dumping_elpased_time: float = 0.0
    smt2_oom_scripts_dumping_elpased_time: float = 0.0
    largest_label_length: int = 0
    labels_count: int = 0


stats = Stats()


def dump_stats_to_csv(file_path: str | Path, stats: Stats):
    with open(file_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Metric", "Value"])
        for field in stats.__dataclass_fields__:
            value = getattr(stats, field)
            writer.writerow([field, value])
