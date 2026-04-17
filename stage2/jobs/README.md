# Stage2 Raw Jobs Excluded

Полные рабочие директории `stage2/jobs/validate-*` намеренно не включены в GitHub-экспорт.

Причины:

- это генерируемые ORCA-артефакты
- они не нужны для чтения отчета и понимания pipeline
- итоговые результаты уже сведены в `stage2/results/`

Для анализа и публикации в пакет оставлены:

- `stage2/jobs_index.csv`
- `stage2/results/summary.csv`
- `stage2/results/top10.csv`
- `stage2/results/validated_minima.csv`
- `stage2/results/best_result.json`
- `stage2/results/best_structure.xyz`
- `stage2/results/final_report.md`
- `stage2/results/best_verified_minimum.json`
- `stage2/stage2_run.log`
- `stage2/scripts/`
