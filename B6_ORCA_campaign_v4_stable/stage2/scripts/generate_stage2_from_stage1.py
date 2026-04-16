\
#!/usr/bin/env python3
import csv, json, pathlib, shutil
ROOT = pathlib.Path(__file__).resolve().parents[2]
STAGE1, STAGE2 = ROOT/"stage1", ROOT/"stage2"
CFG = json.loads((ROOT/"configs"/"stage2_config.json").read_text(encoding="utf-8"))
summary = STAGE1/"results"/"summary.csv"; jobs_root = STAGE2/"jobs"
if not summary.exists(): raise SystemExit("stage1/results/summary.csv not found. Run stage1 first.")
if jobs_root.exists(): shutil.rmtree(jobs_root)
jobs_root.mkdir(parents=True)
def build_input(mult):
    return "\n".join([CFG["method_line"],"", "%pal",f"  nprocs {CFG['nprocs']}","end","",f"%maxcore {CFG['maxcore']}","",
                      "%geom","  Calc_Hess true",f"  Recalc_Hess {CFG['geom_block'].get('Recalc_Hess', 5)}","end","",f"* xyzfile 0 {mult} stage1_final.xyz",""])
finished=[]
with open(summary,newline="",encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row["status"]=="finished" and row["energy_hartree"]: finished.append(row)
finished = finished[:CFG["take_top_n_finished"]]
if not finished: raise SystemExit("No finished stage1 jobs found.")
manifest=[]
for idx,row in enumerate(finished, start=1):
    src=STAGE1/"jobs"/row["job_id"]; xyz=src/"input.xyz"
    if not xyz.exists(): continue
    jid=f"validate-{idx:03d}-{row['job_id']}"; jdir=jobs_root/jid; jdir.mkdir()
    shutil.copy2(xyz, jdir/"stage1_final.xyz")
    meta={"job_id":jid,"source_stage1_job_id":row["job_id"],"template":row["template"],"distance_angstrom":row["distance_angstrom"],
          "multiplicity":row["multiplicity"],"stage1_energy_hartree":row["energy_hartree"],"stage":2,"input_file":"input.inp","output_file":"output.out"}
    (jdir/"metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (jdir/"input.inp").write_text(build_input(row["multiplicity"]), encoding="utf-8")
    manifest.append(meta)
with open(STAGE2/"jobs_index.csv","w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f, fieldnames=["job_id","source_stage1_job_id","template","distance_angstrom","multiplicity","stage1_energy_hartree","stage","input_file","output_file"]); w.writeheader(); [w.writerow(r) for r in manifest]
print(f"Generated {len(manifest)} stage2 validation jobs in {jobs_root}")
