\
#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
STAGE1 = ROOT / "stage1"
STAGE2 = ROOT / "stage2"
CFG = json.loads((ROOT / "configs" / "stage2_config.json").read_text(encoding="utf-8"))
SUMMARY = STAGE1 / "results" / "summary.csv"
JOBS_ROOT = STAGE2 / "jobs"

sys.path.insert(0, str(ROOT))

from reporting_utils import (  # noqa: E402
    extract_last_cartesian_coordinates,
    materialize_final_xyz,
    read_text,
)


def build_input(mult: str) -> str:
    return "\n".join(
        [
            CFG["method_line"],
            "",
            "%pal",
            f"  nprocs {CFG['nprocs']}",
            "end",
            "",
            f"%maxcore {CFG['maxcore']}",
            "",
            "%geom",
            "  Calc_Hess true",
            f"  Recalc_Hess {CFG['geom_block'].get('Recalc_Hess', 5)}",
            "end",
            "",
            f"* xyzfile 0 {mult} stage1_final.xyz",
            "",
        ]
    )


def materialize_stage1_geometry(
    stage1_jobdir: pathlib.Path,
    destination: pathlib.Path,
    *,
    summary_row: dict[str, str],
) -> tuple[bool, str]:
    declared_path = summary_row.get("final_xyz_path", "").strip()
    if declared_path:
        declared_xyz = STAGE1 / declared_path
        if declared_xyz.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(declared_xyz, destination)
            return True, declared_path

    output_text = read_text(stage1_jobdir / "output.out")
    success, source = materialize_final_xyz(
        stage1_jobdir,
        destination,
        output_text=output_text,
        comment=f"Recovered stage1 geometry for {summary_row['job_id']}",
        excluded_names={"input.xyz"},
    )
    if success:
        return True, source

    input_xyz = stage1_jobdir / "input.xyz"
    if input_xyz.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_xyz, destination)
        return True, "input.xyz_fallback"

    if extract_last_cartesian_coordinates(output_text):
        return False, "output_geometry_detected_but_not_written"

    return False, "missing_geometry"


if not SUMMARY.exists():
    raise SystemExit("stage1/results/summary.csv not found. Run stage1 first.")
if JOBS_ROOT.exists():
    shutil.rmtree(JOBS_ROOT)
JOBS_ROOT.mkdir(parents=True)

finished: list[dict[str, str]] = []
with open(SUMMARY, newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
        if row["status"] == "finished" and row["energy_hartree"]:
            finished.append(row)

finished = finished[: CFG["take_top_n_finished"]]
if not finished:
    raise SystemExit("No finished stage1 jobs found.")

manifest: list[dict[str, object]] = []
for idx, row in enumerate(finished, start=1):
    source_jobdir = STAGE1 / "jobs" / row["job_id"]
    if not source_jobdir.exists():
        continue

    job_id = f"validate-{idx:03d}-{row['job_id']}"
    jobdir = JOBS_ROOT / job_id
    jobdir.mkdir()

    geometry_ok, geometry_source = materialize_stage1_geometry(
        source_jobdir,
        jobdir / "stage1_final.xyz",
        summary_row=row,
    )
    if not geometry_ok:
        shutil.rmtree(jobdir)
        continue

    metadata = {
        "job_id": job_id,
        "source_stage1_job_id": row["job_id"],
        "template": row["template"],
        "distance_angstrom": row["distance_angstrom"],
        "multiplicity": row["multiplicity"],
        "stage1_energy_hartree": row["energy_hartree"],
        "stage": 2,
        "input_file": "input.inp",
        "output_file": "output.out",
        "source_geometry_origin": geometry_source,
        "source_geometry_file": "stage1_final.xyz",
    }
    (jobdir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (jobdir / "input.inp").write_text(build_input(row["multiplicity"]), encoding="utf-8")
    manifest.append(metadata)

with open(STAGE2 / "jobs_index.csv", "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "job_id",
            "source_stage1_job_id",
            "template",
            "distance_angstrom",
            "multiplicity",
            "stage1_energy_hartree",
            "stage",
            "input_file",
            "output_file",
            "source_geometry_origin",
            "source_geometry_file",
        ],
    )
    writer.writeheader()
    writer.writerows(manifest)

print(f"Generated {len(manifest)} stage2 validation jobs in {JOBS_ROOT}")
