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
CFG = json.loads((PROJECT_ROOT / "configs" / "stage2_config.json").read_text(encoding="utf-8"))
RESULTS.mkdir(exist_ok=True)

sys.path.insert(0, str(PROJECT_ROOT))

from reporting_utils import (  # noqa: E402
    HARTREE_TO_KCAL_MOL,
    classify_run,
    detect_error_hint,
    discover_final_xyz_file,
    extract_last_cartesian_coordinates,
    materialize_final_xyz,
    parse_final_energy,
    parse_frequencies,
    read_text,
)

FIELDS = [
    "job_id",
    "source_stage1_job_id",
    "template",
    "distance_angstrom",
    "multiplicity",
    "status",
    "error_class",
    "error_hint",
    "energy_hartree",
    "stage1_energy_hartree",
    "delta_vs_stage1_microhartree",
    "frequency_count",
    "nimag",
    "lowest_freq_cm1",
    "min_frequency_cm-1",
    "hard_imag_count",
    "small_negative_count",
    "accepted_minimum",
    "is_true_minimum",
    "final_xyz_available",
    "geometry_source",
    "final_xyz_path",
    "output_path",
]

BEST_RESULT_PATH = RESULTS / "best_result.json"
LEGACY_BEST_RESULT_PATH = RESULTS / "best_verified_minimum.json"
BEST_STRUCTURE_PATH = RESULTS / "best_structure.xyz"
FINAL_REPORT_PATH = RESULTS / "final_report.md"
TOP10_PATH = RESULTS / "top10.csv"


def as_float(value: object) -> float | None:
    if value in ("", None):
        return None
    return float(value)


def sortable_energy(row: dict[str, object]) -> float:
    energy = as_float(row["energy_hartree"])
    return energy if energy is not None else 1e99


def yes_no(flag: bool) -> str:
    return "yes" if flag else "no"


def format_energy(value: object) -> str:
    number = as_float(value)
    return f"{number:.12f}" if number is not None else "n/a"


def format_frequency(value: object) -> str:
    number = as_float(value)
    return f"{number:.2f}" if number is not None else "n/a"


def delta_kcal(reference: float, value: float) -> float:
    return (value - reference) * HARTREE_TO_KCAL_MOL


def best_by_multiplicity(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    best: dict[str, dict[str, object]] = {}
    for row in rows:
        key = str(row["multiplicity"])
        current = best.get(key)
        if current is None or sortable_energy(row) < sortable_energy(current):
            best[key] = row
    return sorted(best.values(), key=lambda row: int(str(row["multiplicity"])))


def load_stage1_summary() -> list[dict[str, str]]:
    summary_path = PROJECT_ROOT / "stage1" / "results" / "summary.csv"
    if not summary_path.exists():
        return []
    with open(summary_path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def render_top10_table(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return [
            "| Rank | Job | Template | M | Energy, Eh | Lowest freq, cm^-1 | True minimum |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]

    table = [
        "| Rank | Job | Template | M | Energy, Eh | Lowest freq, cm^-1 | True minimum |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for idx, row in enumerate(rows[:10], start=1):
        table.append(
            "| {rank} | `{job}` | `{template}` | `{mult}` | `{energy}` | `{freq}` | `{true_min}` |".format(
                rank=idx,
                job=row["job_id"],
                template=row["template"],
                mult=row["multiplicity"],
                energy=format_energy(row["energy_hartree"]),
                freq=format_frequency(row["lowest_freq_cm1"]),
                true_min=row["is_true_minimum"],
            )
        )
    return table


def render_multiplicity_table(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return ["- В текущем наборе `stage2` не оказалось подтвержденных минимумов."]

    lines = [
        "| Multiplicity | Job | Template | Energy, Eh | Delta to best, kcal/mol |",
        "| --- | --- | --- | --- | --- |",
    ]
    reference = min(sortable_energy(row) for row in rows)
    for row in rows:
        lines.append(
            "| `{mult}` | `{job}` | `{template}` | `{energy}` | `{delta:.4f}` |".format(
                mult=row["multiplicity"],
                job=row["job_id"],
                template=row["template"],
                energy=format_energy(row["energy_hartree"]),
                delta=delta_kcal(reference, sortable_energy(row)),
            )
        )
    return lines


rows: list[dict[str, object]] = []
hard_threshold = float(CFG["acceptance_rule"]["hard_imag_threshold_cm-1"])

for jobdir in sorted(JOBS.glob("validate-*")):
    metadata = json.loads((jobdir / "metadata.json").read_text(encoding="utf-8"))
    output_path = jobdir / "output.out"
    output_text = read_text(output_path)
    status, error_class = classify_run(output_text)
    energy = parse_final_energy(output_text)
    frequencies = parse_frequencies(output_text)

    hard_imag = [freq for freq in frequencies if freq < hard_threshold]
    small_negative = [freq for freq in frequencies if hard_threshold <= freq < 0.0]
    nimag = len([freq for freq in frequencies if freq < 0.0])
    lowest_freq = min(frequencies) if frequencies else None
    accepted_minimum = status == "finished" and energy is not None and len(hard_imag) == 0
    is_true_minimum = status == "finished" and energy is not None and nimag == 0

    final_xyz = discover_final_xyz_file(jobdir, excluded_names={"stage1_final.xyz"})
    if final_xyz is not None:
        geometry_source = "optimized_xyz_file"
        final_xyz_available = "yes"
        final_xyz_path = str(final_xyz.relative_to(ROOT))
    elif extract_last_cartesian_coordinates(output_text):
        geometry_source = "parsed_from_output"
        final_xyz_available = "yes"
        final_xyz_path = ""
    else:
        geometry_source = "missing"
        final_xyz_available = "no"
        final_xyz_path = ""

    if status == "finished":
        if energy is None:
            error_class = "energy_not_parsed"
        elif nimag > 0:
            error_class = "imaginary_freq"
        else:
            error_class = "normal_termination"

    stage1_energy = as_float(metadata.get("stage1_energy_hartree"))
    delta_vs_stage1_microhartree = ""
    if stage1_energy is not None and energy is not None:
        delta_vs_stage1_microhartree = (energy - stage1_energy) * 1_000_000

    rows.append(
        {
            "job_id": metadata["job_id"],
            "source_stage1_job_id": metadata["source_stage1_job_id"],
            "template": metadata["template"],
            "distance_angstrom": metadata["distance_angstrom"],
            "multiplicity": metadata["multiplicity"],
            "status": status,
            "error_class": error_class,
            "error_hint": detect_error_hint(output_text),
            "energy_hartree": energy if energy is not None else "",
            "stage1_energy_hartree": metadata.get("stage1_energy_hartree", ""),
            "delta_vs_stage1_microhartree": delta_vs_stage1_microhartree,
            "frequency_count": len(frequencies),
            "nimag": nimag,
            "lowest_freq_cm1": lowest_freq if lowest_freq is not None else "",
            "min_frequency_cm-1": lowest_freq if lowest_freq is not None else "",
            "hard_imag_count": len(hard_imag),
            "small_negative_count": len(small_negative),
            "accepted_minimum": yes_no(accepted_minimum),
            "is_true_minimum": yes_no(is_true_minimum),
            "final_xyz_available": final_xyz_available,
            "geometry_source": geometry_source,
            "final_xyz_path": final_xyz_path,
            "output_path": str(output_path.relative_to(ROOT)),
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

finished_by_energy = [
    row for row in rows_sorted if row["status"] == "finished" and row["energy_hartree"] != ""
]
with open(TOP10_PATH, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(finished_by_energy[:10])

validated = [
    row
    for row in rows_sorted
    if row["is_true_minimum"] == "yes" and row["energy_hartree"] != ""
]
with open(RESULTS / "validated_minima.csv", "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(validated)

best_result: dict[str, object] = {
    "note": "No true minimum with parsed energy and saved final geometry was found yet."
}
if BEST_STRUCTURE_PATH.exists():
    BEST_STRUCTURE_PATH.unlink()

for row in validated:
    jobdir = JOBS / str(row["job_id"])
    output_text = read_text(jobdir / "output.out")
    success, geometry_origin = materialize_final_xyz(
        jobdir,
        BEST_STRUCTURE_PATH,
        output_text=output_text,
        comment=f"Best verified B6 minimum from {row['job_id']}",
        excluded_names={"stage1_final.xyz"},
    )
    if not success:
        continue
    best_result = dict(row)
    best_result["best_structure_path"] = "best_structure.xyz"
    best_result["best_structure_origin"] = geometry_origin
    break

BEST_RESULT_PATH.write_text(
    json.dumps(best_result, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
LEGACY_BEST_RESULT_PATH.write_text(
    json.dumps(best_result, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

stage1_rows = load_stage1_summary()
stage1_total = len(stage1_rows)
stage1_finished = sum(1 for row in stage1_rows if row.get("status") == "finished")
stage2_total = len(rows_sorted)
stage2_finished = len(finished_by_energy)
rejected_imag = sum(1 for row in rows_sorted if row["error_class"] == "imaginary_freq")
error_breakdown: dict[str, int] = {}
for row in rows_sorted:
    key = str(row["error_class"])
    error_breakdown[key] = error_breakdown.get(key, 0) + 1

report_lines = ["# Final Report", ""]
report_lines.extend(
    [
        "## Executive Summary",
        "",
        f"- Всего задач `stage1`: `{stage1_total}`",
        f"- Успешно завершено на `stage1`: `{stage1_finished}`",
        f"- Кандидатов на валидацию `stage2`: `{stage2_total}`",
        f"- Успешно завершено на `stage2`: `{stage2_finished}`",
        f"- Отброшено из-за мнимых частот: `{rejected_imag}`",
        f"- Подтвержденных true minima: `{len(validated)}`",
        "",
        "## True-Minimum Criterion",
        "",
        "- `status = finished`",
        "- энергия успешно распарсена из `FINAL SINGLE POINT ENERGY`",
        "- `nimag = 0`",
        "- в `best_result.json` попадает только структура, для которой удалось сохранить `best_structure.xyz`",
        "",
        "## Error Classification",
        "",
    ]
)
for key in sorted(error_breakdown):
    report_lines.append(f"- `{key}`: `{error_breakdown[key]}`")

report_lines.extend(["", "## Top-10 By Energy", ""])
report_lines.extend(render_top10_table(finished_by_energy))

report_lines.extend(["", "## Best By Multiplicity", ""])
report_lines.extend(render_multiplicity_table(best_by_multiplicity(validated)))

report_lines.extend(["", "## Best Overall Result", ""])
if "job_id" in best_result:
    report_lines.extend(
        [
            f"- Job: `{best_result['job_id']}`",
            f"- Template: `{best_result['template']}`",
            f"- Distance, A: `{best_result['distance_angstrom']}`",
            f"- Multiplicity: `{best_result['multiplicity']}`",
            f"- Energy, Eh: `{format_energy(best_result['energy_hartree'])}`",
            f"- Lowest frequency, cm^-1: `{format_frequency(best_result['lowest_freq_cm1'])}`",
            f"- Structure file: `{best_result['best_structure_path']}`",
        ]
    )
else:
    report_lines.append("- True minimum с сохраненной геометрией пока не найден.")

report_lines.extend(
    [
        "",
        "## Diploma-Ready Conclusion",
        "",
    ]
)
if validated:
    best_energy = sortable_energy(validated[0])
    report_lines.extend(
        [
            "В рамках двухэтапной ORCA-кампании для кластера B6 сначала был выполнен массовый геометрический скрининг,",
            "а затем лучшие кандидаты были повторно оптимизированы и проверены расчетом частот.",
            "Такой подход позволяет отделять истинные минимумы поверхности потенциальной энергии от ложных минимумов,",
            "которые после `NumFreq` оказываются седловыми точками и должны исключаться из финального анализа.",
            f"По строгому критерию `nimag = 0` подтверждено `{len(validated)}` устойчивых минимумов из `{stage2_total}` проверенных кандидатов `stage2`.",
            f"Абсолютный минимум в текущем наборе соответствует структуре `{validated[0]['template']}` при мультиплетности `{validated[0]['multiplicity']}`",
            f"с энергией `{best_energy:.12f} Eh`.",
            "Следовательно, в дипломной интерпретации корректно опираться не на голую оптимизационную энергию,",
            "а только на результаты, прошедшие частотную валидацию без мнимых частот.",
        ]
    )
else:
    report_lines.append(
        "По текущим данным true minima без мнимых частот не подтверждены, поэтому итог кампании нельзя считать методически завершенным."
    )

FINAL_REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

print("Wrote", RESULTS / "summary.csv")
print("Wrote", TOP10_PATH)
print("Wrote", RESULTS / "validated_minima.csv")
print("Wrote", BEST_RESULT_PATH)
print("Wrote", LEGACY_BEST_RESULT_PATH)
print("Wrote", FINAL_REPORT_PATH)
if BEST_STRUCTURE_PATH.exists():
    print("Wrote", BEST_STRUCTURE_PATH)
