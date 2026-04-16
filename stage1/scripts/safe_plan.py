\
#!/usr/bin/env python3
import json, os
cpu_count = os.cpu_count() or 1
mem_kb = 0
with open("/proc/meminfo", "r", encoding="utf-8") as f:
    for line in f:
        if line.startswith("MemTotal:"):
            mem_kb = int(line.split()[1]); break
mem_mb = mem_kb // 1024 if mem_kb else 0
maxcore = int(os.environ.get("MAXCORE_PER_JOB_MB", "1500"))
reserve_mb = int(os.environ.get("RESERVE_MB", "1024"))
extra_overhead_mb = int(os.environ.get("PER_JOB_OVERHEAD_MB", "400"))
workers_by_ram = max(1, (mem_mb - reserve_mb) // (maxcore + extra_overhead_mb)) if mem_mb else 1
workers = max(1, min(cpu_count, workers_by_ram))
print(json.dumps({"detected_logical_cpus":cpu_count,"detected_total_ram_mb":mem_mb,"recommended_workers":workers,
                  "maxcore_per_job_mb":maxcore,"reserve_mb":reserve_mb,"per_job_overhead_mb":extra_overhead_mb}, ensure_ascii=False, indent=2))
