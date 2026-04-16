\
#!/usr/bin/env bash
set -uo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCA_BIN="${ORCA_BIN:-/opt/orca/orca}"
if [[ ! -x "$ORCA_BIN" ]]; then echo "ORCA binary not found: $ORCA_BIN" >&2; exit 1; fi
if [[ -z "${WORKERS:-}" ]]; then
  WORKERS="$(python3 "$ROOT_DIR/../stage1/scripts/safe_plan.py" | python3 -c 'import sys,json; print(json.load(sys.stdin)["recommended_workers"])')"
fi
echo "Using ORCA_BIN=$ORCA_BIN"; echo "Using WORKERS=$WORKERS"; echo "Stable mode stage2: nprocs=1 per job"
run_one(){ local jobdir="$1"; ( cd "$jobdir"; if [[ -f output.out ]] && grep -q "ORCA TERMINATED NORMALLY" output.out; then echo "Skipping $(basename "$jobdir"): already finished"; exit 0; fi; echo "=== Running $(basename "$jobdir") ==="; "$ORCA_BIN" input.inp > output.out 2>&1 || true; ); }
active=0
for jobdir in "$ROOT_DIR"/jobs/validate-*; do
  [[ -d "$jobdir" ]] || continue
  run_one "$jobdir" &
  ((active+=1))
  if (( active >= WORKERS )); then wait -n || true; ((active-=1)); fi
done
wait || true
python3 "$ROOT_DIR/scripts/collect_stage2_results.py"
echo "Done. See $ROOT_DIR/results/validated_minima.csv and $ROOT_DIR/results/best_verified_minimum.json"
