\
#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for jobdir in "$ROOT_DIR"/jobs/job-*; do
  [[ -d "$jobdir" ]] || continue
  if [[ -f "$jobdir/output.out" ]] && grep -q "ORCA TERMINATED NORMALLY" "$jobdir/output.out"; then continue; fi
  find "$jobdir" -maxdepth 1 -type f ! -name "input.inp" ! -name "metadata.json" -delete
done
echo "Cleaned unfinished/failed stage1 jobs"
