#!/usr/bin/env python3
from __future__ import annotations

import csv
import pathlib
from collections import Counter

import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[2]
STAGE1_RESULTS = ROOT / "stage1" / "results"
STAGE2_RESULTS = ROOT / "stage2" / "results"
REPORTS_DIR = ROOT / "reports"

HARTREE_TO_KCAL_MOL = 627.509474

STAGE1_SUMMARY = STAGE1_RESULTS / "summary.csv"
STAGE2_SUMMARY = STAGE2_RESULTS / "summary.csv"
REPORT_PATH = REPORTS_DIR / "calculation_results_report.md"
FIG_TEMPLATE_PATH = REPORTS_DIR / "fig_stage1_best_by_template.png"
FIG_VALIDATION_PATH = REPORTS_DIR / "fig_stage2_validation_rank.png"


def read_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def as_float(value: str | None) -> float | None:
    if value in ("", None):
        return None
    return float(value)


def is_finished(row: dict[str, str]) -> bool:
    return row.get("status", "").strip().lower() == "finished" and as_float(row.get("energy_hartree")) is not None


def stage2_is_true_minimum(row: dict[str, str]) -> bool:
    if row.get("is_true_minimum", "").strip():
        return row["is_true_minimum"].strip().lower() == "yes"
    if not is_finished(row):
        return False
    nimag = row.get("nimag", "").strip()
    if nimag:
        return int(float(nimag)) == 0
    lowest_freq = as_float(row.get("lowest_freq_cm1") or row.get("min_frequency_cm-1"))
    return row.get("accepted_minimum", "").strip().lower() == "yes" and (lowest_freq is None or lowest_freq >= 0.0)


def rel_kcal(reference: float, value: float) -> float:
    return (value - reference) * HARTREE_TO_KCAL_MOL


def best_rows_by_key(rows: list[dict[str, str]], key: str) -> list[dict[str, str]]:
    best: dict[str, dict[str, str]] = {}
    for row in rows:
        current = best.get(row[key])
        if current is None or as_float(row["energy_hartree"]) < as_float(current["energy_hartree"]):
            best[row[key]] = row
    return sorted(best.values(), key=lambda row: as_float(row["energy_hartree"]))


def make_template_figure(stage1_finished: list[dict[str, str]]) -> None:
    best_by_template = best_rows_by_key(stage1_finished, "template")
    reference = as_float(best_by_template[0]["energy_hartree"])
    labels = [row["template"] for row in best_by_template]
    values = [rel_kcal(reference, as_float(row["energy_hartree"])) for row in best_by_template]

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=180)
    colors = ["#1d3557", "#457b9d", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51"]
    bars = ax.bar(labels, values, color=colors[: len(labels)], edgecolor="#1f2937", linewidth=0.8)
    ax.set_title("Best Stage1 Structure For Each Template", fontsize=14, weight="bold")
    ax.set_ylabel("Relative energy, kcal/mol")
    ax.set_xlabel("Template")
    ax.tick_params(axis="x", rotation=18)
    ax.set_ylim(0, max(values) * 1.15 if values else 1)
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.3,
            f"{value:.2f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    fig.tight_layout()
    fig.savefig(FIG_TEMPLATE_PATH, bbox_inches="tight")
    plt.close(fig)


def make_validation_figure(stage2_finished: list[dict[str, str]]) -> None:
    ranked = sorted(stage2_finished, key=lambda row: as_float(row["energy_hartree"]))
    reference = as_float(ranked[0]["energy_hartree"])
    rel_values = [rel_kcal(reference, as_float(row["energy_hartree"])) for row in ranked]
    colors = ["#2a9d8f" if stage2_is_true_minimum(row) else "#d62828" for row in ranked]
    labels = [f"{idx + 1}" for idx in range(len(ranked))]

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=180)
    bars = ax.bar(labels, rel_values, color=colors, edgecolor="#1f2937", linewidth=0.8)
    ax.set_title("Stage2 Validation Ranking", fontsize=14, weight="bold")
    ax.set_xlabel("Rank by stage2 energy")
    ax.set_ylabel("Relative energy, kcal/mol")
    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, color="#2a9d8f"),
        plt.Rectangle((0, 0), 1, 1, color="#d62828"),
    ]
    ax.legend(legend_handles, ["true minimum", "rejected by frequencies"], frameon=False)
    ax.set_ylim(0, max(rel_values) * 1.15 if rel_values else 1)

    for bar, row, value in zip(bars, ranked, rel_values):
        note = row["template"]
        if not stage2_is_true_minimum(row):
            note = f"{row['template']} rejected"
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.12,
            note,
            ha="center",
            va="bottom",
            rotation=45,
            fontsize=8,
        )
        if value > 0.01:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() / 2,
                f"{value:.2f}",
                ha="center",
                va="center",
                rotation=90,
                fontsize=8,
                color="white",
                weight="bold",
            )

    fig.tight_layout()
    fig.savefig(FIG_VALIDATION_PATH, bbox_inches="tight")
    plt.close(fig)


def build_report(stage1_rows: list[dict[str, str]], stage2_rows: list[dict[str, str]]) -> str:
    stage1_finished = [row for row in stage1_rows if is_finished(row)]
    stage2_finished = [row for row in stage2_rows if is_finished(row)]
    stage2_true = [row for row in stage2_finished if stage2_is_true_minimum(row)]
    stage2_rejected = [row for row in stage2_finished if not stage2_is_true_minimum(row)]

    stage1_best = stage1_finished[0]
    stage2_best = sorted(stage2_true, key=lambda row: as_float(row["energy_hartree"]))[0]
    stage2_reference = as_float(stage2_best["energy_hartree"])

    stage1_by_mult = best_rows_by_key(stage1_finished, "multiplicity")
    stage2_by_template = best_rows_by_key(stage2_true, "template")
    rejected_counter = Counter(row["template"] for row in stage2_rejected)

    lines = [
        "# Results Report",
        "",
        "Отчет ниже содержит только итоговые результаты расчетов без описания workflow и организационной части.",
        "",
        "## 1. Краткий итог",
        "",
        f"- Всего расчетов `stage1`: `{len(stage1_rows)}`",
        f"- Успешно завершено на `stage1`: `{len(stage1_finished)}`",
        f"- Проверено кандидатов на `stage2`: `{len(stage2_rows)}`",
        f"- Подтверждено минимумов после частотной проверки: `{len(stage2_true)}`",
        f"- Отклонено из-за мнимых частот: `{len(stage2_rejected)}`",
        "",
        "## 2. Лучший результат всей кампании",
        "",
        f"- Лучшая подтвержденная структура: `{stage2_best['template']}`",
        f"- Расстояние: `{stage2_best['distance_angstrom']} A`",
        f"- Мультиплетность: `{stage2_best['multiplicity']}`",
        f"- Энергия `stage2`: `{as_float(stage2_best['energy_hartree']):.12f} Eh`",
        f"- Минимальная частота: `{as_float(stage2_best.get('lowest_freq_cm1') or stage2_best.get('min_frequency_cm-1')) or 0.0:.2f} cm^-1`",
        "",
        "## 3. Графики",
        "",
        "### 3.1 Лучший результат по каждому стартовому шаблону (`stage1`)",
        "",
        "![Best stage1 structure for each template](fig_stage1_best_by_template.png)",
        "",
        "### 3.2 Ранжирование кандидатов `stage2` с учетом частотной проверки",
        "",
        "![Stage2 validation ranking](fig_stage2_validation_rank.png)",
        "",
        "## 4. Лучшие структуры по мультиплетностям (`stage1`)",
        "",
        "| Multiplicity | Template | Distance, A | Energy, Eh | Delta to global best, kcal/mol |",
        "| --- | --- | --- | --- | --- |",
    ]

    stage1_reference = as_float(stage1_best["energy_hartree"])
    for row in stage1_by_mult:
        lines.append(
            "| `{mult}` | `{template}` | `{distance}` | `{energy:.12f}` | `{delta:.4f}` |".format(
                mult=row["multiplicity"],
                template=row["template"],
                distance=row["distance_angstrom"],
                energy=as_float(row["energy_hartree"]),
                delta=rel_kcal(stage1_reference, as_float(row["energy_hartree"])),
            )
        )

    lines.extend(
        [
            "",
            "## 5. Подтвержденные минимумы после `stage2`",
            "",
            "| Rank | Template | Distance, A | M | Energy, Eh | Delta to best, kcal/mol |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for idx, row in enumerate(sorted(stage2_true, key=lambda item: as_float(item["energy_hartree"])), start=1):
        lines.append(
            "| {rank} | `{template}` | `{distance}` | `{mult}` | `{energy:.12f}` | `{delta:.4f}` |".format(
                rank=idx,
                template=row["template"],
                distance=row["distance_angstrom"],
                mult=row["multiplicity"],
                energy=as_float(row["energy_hartree"]),
                delta=rel_kcal(stage2_reference, as_float(row["energy_hartree"])),
            )
        )

    lines.extend(
        [
            "",
            "## 6. Лучшие подтвержденные шаблоны (`stage2`)",
            "",
            "| Template | Best energy, Eh | Delta to best, kcal/mol |",
            "| --- | --- | --- |",
        ]
    )
    for row in stage2_by_template:
        lines.append(
            "| `{template}` | `{energy:.12f}` | `{delta:.4f}` |".format(
                template=row["template"],
                energy=as_float(row["energy_hartree"]),
                delta=rel_kcal(stage2_reference, as_float(row["energy_hartree"])),
            )
        )

    lines.extend(
        [
            "",
            "## 7. Что было отброшено на частотной проверке",
            "",
        ]
    )
    if stage2_rejected:
        for template, count in sorted(rejected_counter.items()):
            lines.append(f"- `{template}`: `{count}`")
    else:
        lines.append("- На текущем наборе отклоненных кандидатов нет.")

    lines.extend(
        [
            "",
            "## 8. Краткий вывод по результатам",
            "",
            "В текущем обследованном наборе конфигураций глобальный минимум соответствует триплетной структуре `ring` при `1.90 A`.",
            "Частотная проверка показала, что два энергетически сильных `ring`-кандидата на больших расстояниях (`2.05 A` и `2.20 A`) не являются истинными минимумами.",
            "После отбраковки по частотам в финале остаются `trigonal_prism`, `distorted_prism_1` и кластер `pentagonal_pyramid`, но все они лежат примерно на `3.91-3.92 kcal/mol` выше глобального минимума.",
        ]
    )

    return "\n".join(lines) + "\n"


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stage1_rows = read_csv(STAGE1_SUMMARY)
    stage2_rows = read_csv(STAGE2_SUMMARY)
    stage1_finished = [row for row in stage1_rows if is_finished(row)]
    stage2_finished = [row for row in stage2_rows if is_finished(row)]

    make_template_figure(stage1_finished)
    make_validation_figure(stage2_finished)
    REPORT_PATH.write_text(build_report(stage1_rows, stage2_rows), encoding="utf-8")

    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote {FIG_TEMPLATE_PATH}")
    print(f"Wrote {FIG_VALIDATION_PATH}")


if __name__ == "__main__":
    main()
