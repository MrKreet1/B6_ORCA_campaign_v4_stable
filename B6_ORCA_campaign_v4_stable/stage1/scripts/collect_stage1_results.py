\
#!/usr/bin/env python3
import csv, json, pathlib, re
ROOT = pathlib.Path(__file__).resolve().parents[1]
JOBS = ROOT / "jobs"
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)
re_energy = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
rows = []
for jobdir in sorted(JOBS.glob("job-*")):
    meta = json.loads((jobdir / "metadata.json").read_text(encoding="utf-8"))
    out = jobdir / "output.out"
    status, energy, error_hint = "not_started", None, ""
    if out.exists():
        text = out.read_text(encoding="utf-8", errors="ignore")
        if "****ORCA TERMINATED NORMALLY****" in text: status = "finished"
        elif "ORCA finished by error termination" in text or "aborting the run" in text or "Connection reset by peer" in text: status = "failed"
        else: status = "started"
        if "Connection reset by peer" in text: error_hint = "mpi_connection_reset"
        elif "Bus error" in text: error_hint = "bus_error"
        m = re_energy.findall(text)
        if m: energy = float(m[-1])
    rows.append({"job_id":meta["job_id"],"template":meta["template"],"distance_angstrom":meta["distance_angstrom"],
                 "multiplicity":meta["multiplicity"],"status":status,"energy_hartree":energy if energy is not None else "",
                 "error_hint":error_hint,"output_path":str(out.relative_to(ROOT))})
rows_sorted = sorted(rows, key=lambda r: (r["energy_hartree"]=="", float(r["energy_hartree"]) if r["energy_hartree"]!="" else 1e99))
with open(RESULTS/"summary.csv","w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f, fieldnames=["job_id","template","distance_angstrom","multiplicity","status","energy_hartree","error_hint","output_path"])
    w.writeheader(); [w.writerow(r) for r in rows_sorted]
finished=[r for r in rows_sorted if r["status"]=="finished" and r["energy_hartree"]!=""]
with open(RESULTS/"top_finished.csv","w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f, fieldnames=["job_id","template","distance_angstrom","multiplicity","status","energy_hartree","error_hint","output_path"])
    w.writeheader(); [w.writerow(r) for r in finished[:20]]
(ROOT/"results"/"best_stage1.json").write_text(json.dumps(finished[0] if finished else {"note":"No finished jobs with parsed energy yet."}, ensure_ascii=False, indent=2), encoding="utf-8")
print("Wrote", RESULTS/"summary.csv"); print("Wrote", RESULTS/"top_finished.csv"); print("Wrote", RESULTS/"best_stage1.json")
