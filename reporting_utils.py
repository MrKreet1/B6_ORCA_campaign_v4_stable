#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import re
import shutil
from typing import Iterable

HARTREE_TO_KCAL_MOL = 627.509474

RE_FINAL_ENERGY = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
RE_FREQUENCY = re.compile(
    r"^\s*(?:\d+:\s+)?(-?\d+(?:\.\d+)?)\s+cm\*\*-1\b",
    re.MULTILINE,
)
RE_COORD_LINE = re.compile(
    r"^\s*([A-Za-z]{1,3})\s+"
    r"(-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)\s*$"
)


def read_text(path: pathlib.Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def parse_final_energy(text: str) -> float | None:
    matches = RE_FINAL_ENERGY.findall(text)
    return float(matches[-1]) if matches else None


def parse_frequencies(text: str) -> list[float]:
    return [float(match) for match in RE_FREQUENCY.findall(text)]


def classify_run(text: str) -> tuple[str, str]:
    if not text:
        return "not_started", "not_started"

    upper = text.upper()
    if "****ORCA TERMINATED NORMALLY****" in upper:
        return "finished", "normal_termination"

    has_error = any(
        marker in upper
        for marker in (
            "ORCA FINISHED BY ERROR TERMINATION",
            "ABORTING THE RUN",
            "ERROR TERMINATION",
            "EXITING THE PROGRAM",
        )
    )
    if not has_error:
        return "started", "started"

    if any(
        marker in upper
        for marker in (
            "CONNECTION RESET BY PEER",
            "BUS ERROR",
            "SEGMENTATION FAULT",
            "MPI_ABORT",
            "KILLED",
        )
    ):
        return "failed", "runtime_failed"

    if any(
        marker in upper
        for marker in (
            "SCF NOT CONVERGED",
            "SCF FAILED",
            "CONVERGENCE NOT ACHIEVED",
            "CONVERGENCE FAILED",
        )
    ):
        return "failed", "scf_failed"

    if "VIBRATIONAL FREQUENCIES" in upper or "NUMFREQ" in upper:
        return "failed", "freq_failed"

    return "failed", "opt_failed"


def detect_error_hint(text: str) -> str:
    upper = text.upper()
    if "CONNECTION RESET BY PEER" in upper:
        return "mpi_connection_reset"
    if "BUS ERROR" in upper:
        return "bus_error"
    if "SCF NOT CONVERGED" in upper:
        return "scf_not_converged"
    if "VIBRATIONAL FREQUENCIES" in upper and "ERROR TERMINATION" in upper:
        return "freq_incomplete"
    if "OPTIMIZATION DID NOT CONVERGE" in upper:
        return "opt_not_converged"
    return ""


def discover_final_xyz_file(
    jobdir: pathlib.Path,
    *,
    preferred_names: Iterable[str] | None = None,
    excluded_names: Iterable[str] | None = None,
) -> pathlib.Path | None:
    excluded = {name.lower() for name in (excluded_names or [])}
    preferred = [name.lower() for name in (preferred_names or ())]
    xyz_files = [path for path in sorted(jobdir.glob("*.xyz")) if path.name.lower() not in excluded]

    for preferred_name in preferred:
        for path in xyz_files:
            if path.name.lower() == preferred_name:
                return path

    return xyz_files[0] if xyz_files else None


def extract_last_cartesian_coordinates(
    text: str,
) -> list[tuple[str, float, float, float]]:
    lines = text.splitlines()
    last_block: list[tuple[str, float, float, float]] = []
    idx = 0

    while idx < len(lines):
        if "CARTESIAN COORDINATES (ANGSTROEM)" not in lines[idx].upper():
            idx += 1
            continue

        idx += 1
        while idx < len(lines):
            stripped = lines[idx].strip()
            if not stripped or set(stripped) <= {"-"}:
                idx += 1
                continue
            break

        block: list[tuple[str, float, float, float]] = []
        while idx < len(lines):
            match = RE_COORD_LINE.match(lines[idx])
            if not match:
                if block:
                    break
                idx += 1
                continue
            block.append(
                (
                    match.group(1),
                    float(match.group(2)),
                    float(match.group(3)),
                    float(match.group(4)),
                )
            )
            idx += 1

        if block:
            last_block = block

    return last_block


def write_xyz(
    destination: pathlib.Path,
    atoms: list[tuple[str, float, float, float]],
    *,
    comment: str,
) -> None:
    lines = [str(len(atoms)), comment]
    lines.extend(
        f"{symbol} {x:.10f} {y:.10f} {z:.10f}" for symbol, x, y, z in atoms
    )
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def materialize_final_xyz(
    jobdir: pathlib.Path,
    destination: pathlib.Path,
    *,
    output_text: str,
    comment: str,
    preferred_names: Iterable[str] | None = None,
    excluded_names: Iterable[str] | None = None,
) -> tuple[bool, str]:
    xyz_path = discover_final_xyz_file(
        jobdir,
        preferred_names=preferred_names,
        excluded_names=excluded_names,
    )
    if xyz_path is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(xyz_path, destination)
        return True, xyz_path.name

    atoms = extract_last_cartesian_coordinates(output_text)
    if atoms:
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_xyz(destination, atoms, comment=comment)
        return True, "output.out:last_cartesian_coordinates"

    return False, ""
