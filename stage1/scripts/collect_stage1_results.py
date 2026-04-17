\
#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
JOBS = ROOT / "jobs"
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

sys.path.insert(0, str(PROJECT_ROOT))

from reporting_utils import (  # noqa: E402
    classify_run,
    detect_error_hint,
    discover_final_xyz_file,
    extract_last_cartesian_coordinates,
    parse_final_energy,
    read_text,
)

FIELDS = [
    "job_id",
    "template",
    "distance_angstrom",
    "multiplicity",
    "status",
    "error_class",
    "energy_hartree",
    "error_hint",
    "geometry_source",
    "final_xyz_available",
    "final_xyz_path",
    "output_path",
]


def sortable_energy(row: dict[str, object]) -> float:
    value = row["energy_hartree"]
    return float(value) if value != "" else 1e99


rows: list[dict[str, object]] = []
for jobdir in sorted(JOBS.glob("job-*")):
    meta = json.loads((jobdir / "metadata.json").read_text(encoding="utf-8"))
    out = jobdir / "output.out"
    text = read_text(out)
    status, error_class = classify_run(text)
    energy = parse_final_energy(text)
    error_hint = detect_error_hint(text)

    final_xyz = discover_final_xyz_file(jobdir, excluded_names={"input.xyz"})
    if final_xyz is not None:
        geometry_source = "optimized_xyz_file"
        final_xyz_available = "yes"
        final_xyz_path = str(final_xyz.relative_to(ROOT))
    elif extract_last_cartesian_coordinates(text):
        geometry_source = "parsed_from_output"
        final_xyz_available = "yes"
        final_xyz_path = ""
    else:
        geometry_source = "missing"
        final_xyz_available = "no"
        final_xyz_path = ""

    rows.append(
        {
            "job_id": meta["job_id"],
            "template": meta["template"],
            "distance_angstrom": meta["distance_angstrom"],
            "multiplicity": meta["multiplicity"],
            "status": status,
            "error_class": error_class,
            "energy_hartree": energy if energy is not None else "",
            "error_hint": error_hint,
            "geometry_source": geometry_source,
            "final_xyz_available": final_xyz_available,
            "final_xyz_path": final_xyz_path,
            "output_path": str(out.relative_to(ROOT)),
        }
    )

rows_sorted = sorted(
    rows,
    key=lambda row: (
        row["status"] != "finished",
        row["energy_hartree"] == "",
        sortable_energy(row),
    ),
)

with open(RESULTS / "summary.csv", "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows_sorted)

finished = [
    row
    for row in rows_sorted
    if row["status"] == "finished" and row["energy_hartree"] != ""
]
with open(RESULTS / "top_finished.csv", "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(finished[:20])

(RESULTS / "best_stage1.json").write_text(
    json.dumps(
        finished[0]
        if finished
        else {"note": "No finished jobs with parsed energy yet."},
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print("Wrote", RESULTS / "summary.csv")
print("Wrote", RESULTS / "top_finished.csv")
print("Wrote", RESULTS / "best_stage1.json")
