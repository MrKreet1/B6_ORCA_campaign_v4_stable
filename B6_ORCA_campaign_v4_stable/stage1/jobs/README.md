# Stage1 Raw Jobs Excluded

Полные рабочие директории `stage1/jobs/job-*` намеренно не включены в GitHub-экспорт.

Причины:

- они занимают основной объем проекта
- содержат бинарные и временные ORCA-файлы
- плохо подходят для обычного Git-репозитория

Для анализа и публикации в пакет оставлены:

- `stage1/jobs_index.csv`
- `stage1/results/summary.csv`
- `stage1/results/top_finished.csv`
- `stage1/results/best_stage1.json`
- `stage1/stage1_run.log`
- `stage1/scripts/`
