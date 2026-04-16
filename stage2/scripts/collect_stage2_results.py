\
#!/usr/bin/env python3
import csv, json, pathlib, re
ROOT = pathlib.Path(__file__).resolve().parents[1]
JOBS, RESULTS = ROOT/"jobs", ROOT/"results"
CFG = json.loads((ROOT.parents[0]/"configs"/"stage2_config.json").read_text(encoding="utf-8"))
RESULTS.mkdir(exist_ok=True)
re_energy = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
re_freq = re.compile(r"(-?\d+\.\d+)\s+cm\*\*-1")
rows=[]
for jobdir in sorted(JOBS.glob("validate-*")):
    meta = json.loads((jobdir/"metadata.json").read_text(encoding="utf-8"))
    out = jobdir/"output.out"; status, energy, freqs = "not_started", None, []
    if out.exists():
        text = out.read_text(encoding="utf-8", errors="ignore")
        if "****ORCA TERMINATED NORMALLY****" in text: status="finished"
        elif "ORCA finished by error termination" in text or "aborting the run" in text or "Connection reset by peer" in text: status="failed"
        else: status="started"
        m = re_energy.findall(text)
        if m: energy=float(m[-1])
        freqs=[float(x) for x in re_freq.findall(text)]
    hard_thresh=float(CFG["acceptance_rule"]["hard_imag_threshold_cm-1"])
    hard_imag=[f for f in freqs if f < hard_thresh]; small_neg=[f for f in freqs if hard_thresh <= f < 0.0]
    rows.append({"job_id":meta["job_id"],"source_stage1_job_id":meta["source_stage1_job_id"],"template":meta["template"],"distance_angstrom":meta["distance_angstrom"],
                 "multiplicity":meta["multiplicity"],"status":status,"energy_hartree":energy if energy is not None else "","min_frequency_cm-1":min(freqs) if freqs else "",
                 "hard_imag_count":len(hard_imag),"small_negative_count":len(small_neg),
                 "accepted_minimum":"yes" if status=="finished" and len(hard_imag)==0 else "no","output_path":str(out.relative_to(ROOT))})
rows_sorted=sorted(rows, key=lambda r: (r["accepted_minimum"]!="yes", r["energy_hartree"]=="", float(r["energy_hartree"]) if r["energy_hartree"]!="" else 1e99))
fields=["job_id","source_stage1_job_id","template","distance_angstrom","multiplicity","status","energy_hartree","min_frequency_cm-1","hard_imag_count","small_negative_count","accepted_minimum","output_path"]
with open(RESULTS/"summary.csv","w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); [w.writerow(r) for r in rows_sorted]
accepted=[r for r in rows_sorted if r["accepted_minimum"]=="yes" and r["energy_hartree"]!=""]
with open(RESULTS/"validated_minima.csv","w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); [w.writerow(r) for r in accepted]
(RESULTS/"best_verified_minimum.json").write_text(json.dumps(accepted[0] if accepted else {"note":"No verified minima without hard imaginary frequencies yet."}, ensure_ascii=False, indent=2), encoding="utf-8")
print("Wrote", RESULTS/"summary.csv"); print("Wrote", RESULTS/"validated_minima.csv"); print("Wrote", RESULTS/"best_verified_minimum.json")
