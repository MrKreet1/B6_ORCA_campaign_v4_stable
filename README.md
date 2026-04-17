# B6 ORCA campaign v4 stable

Подробный отчет по двухэтапной ORCA-кампании для скрининга структур `B6` в стабильном режиме запуска. Главная идея проекта: не распараллеливать отдельный ORCA-расчет по MPI-ранкам, а запускать много независимых job параллельно, при этом каждый job идет с `nprocs=1`. Такой режим снижает риск MPI-падений и делает кампанию воспроизводимой на нестабильных узлах.

## 1. Executive Summary

- Исследована полная сетка из `108` конфигураций:
  - `6` геометрических шаблонов
  - `6` межатомных расстояний
  - `3` мультиплетности
- `stage1` завершил `107/108` расчетов.
- Единственный сбой в `stage1` пришелся на `job-0053` (`octahedral_like`, `2.20 A`, `M = 3`) из-за `SCF NOT CONVERGED AFTER 1421 CYCLES`.
- `stage2` взял `10` лучших завершенных структур из `stage1` и пересчитал их с `NumFreq`.
- `stage2` завершил `10/10` job.
- По критерию частот подтверждены `8/10` кандидатов; еще `2/10` отклонены как седловые точки из-за жестких мнимых частот.
- Лучший подтвержденный минимум всей кампании:
  - шаблон: `ring`
  - расстояние: `1.90 A`
  - мультиплетность: `3`
  - энергия `stage1`: `-148.743338856923 Eh`
  - энергия `stage2`: `-148.743338857395 Eh`
- Следующий подтвержденный минимум выше по энергии на `3.9109 kcal/mol`, так что лидер отделен от остальных весьма уверенно.

## 2. Цель кампании

Целью было найти низкоэнергетические структуры `B6` среди набора геометрических шаблонов и затем отделить настоящие минимумы на поверхности потенциальной энергии от ложных кандидатов, которые после частотного анализа оказываются седловыми точками.

Практическое ограничение проекта: нестабильность многопроцессорных ORCA-job. Поэтому архитектура кампании была специально построена вокруг безопасного режима:

- один ORCA-job = один процесс (`nprocs=1`)
- сервер загружается не MPI внутри одного расчета, а множеством независимых job
- результаты каждого этапа автоматически агрегируются в CSV/JSON

## 3. Состав и параметры кампании

### 3.1 Конфигурация `stage1`

Источник: [configs/stage1_config.json](configs/stage1_config.json)

- Назначение: первичный скрининг полной сетки конфигураций
- Метод: `! r2SCAN-3c Opt TightSCF TightOpt`
- Заряд: `0`
- Мультиплетности: `1`, `3`, `5`
- Сетка расстояний, A: `1.45`, `1.60`, `1.75`, `1.90`, `2.05`, `2.20`
- Геометрические шаблоны:
  - `ring`
  - `trigonal_prism`
  - `octahedral_like`
  - `pentagonal_pyramid`
  - `distorted_prism_1`
  - `distorted_octa_1`
- `nprocs = 1`
- `maxcore = 1500`
- `%geom`:
  - `Calc_Hess true`
  - `Recalc_Hess 5`

Полный размер сетки:

`6 templates x 6 distances x 3 multiplicities = 108 job`

### 3.2 Конфигурация `stage2`

Источник: [configs/stage2_config.json](configs/stage2_config.json)

- Назначение: частотная валидация лучших кандидатов `stage1`
- Метод: `! r2SCAN-3c Opt NumFreq TightSCF TightOpt`
- Источник отбора: `stage1/results/summary.csv`
- Число кандидатов на проверку: `10`
- `nprocs = 1`
- `maxcore = 1500`
- Критерий приемки:
  - служебный флаг `accepted_minimum`: `hard_imag_threshold_cm-1 = -20.0` и `hard_imag_count = 0`
  - строгий научный флаг `is_true_minimum`: `status = finished`, энергия распарсена, `nimag = 0`
  - в `best_result.json` попадает только true minimum, для которого удалось сохранить `best_structure.xyz`

## 4. Как работает пайплайн

### 4.1 Логика `stage1`

Основные скрипты:

- [stage1/scripts/safe_plan.py](stage1/scripts/safe_plan.py)
- [stage1/scripts/run_stage1_parallel_safe.sh](stage1/scripts/run_stage1_parallel_safe.sh)
- [stage1/scripts/collect_stage1_results.py](stage1/scripts/collect_stage1_results.py)

Что делает `stage1`:

1. `safe_plan.py` оценивает число безопасных параллельных job по CPU и RAM.
2. `run_stage1_parallel_safe.sh` запускает все `job-*` из `stage1/jobs/`.
3. Каждый job стартует как отдельный ORCA-процесс с `nprocs=1`.
4. `collect_stage1_results.py` парсит `output.out`, вытаскивает статус и `FINAL SINGLE POINT ENERGY`, затем пишет:
   - `stage1/results/summary.csv`
   - `stage1/results/top_finished.csv`
   - `stage1/results/best_stage1.json`
   - а также добавляет поля `error_class`, `final_xyz_available`, `final_xyz_path`

Статус job определяется по тексту `output.out`:

- `finished` при наличии `****ORCA TERMINATED NORMALLY****`
- `failed` при явном error termination
- `started` или `not_started` в остальных случаях

### 4.2 Логика `stage2`

Основные скрипты:

- [stage2/scripts/generate_stage2_from_stage1.py](stage2/scripts/generate_stage2_from_stage1.py)
- [stage2/scripts/run_stage2_parallel_safe.sh](stage2/scripts/run_stage2_parallel_safe.sh)
- [stage2/scripts/collect_stage2_results.py](stage2/scripts/collect_stage2_results.py)

Что делает `stage2`:

1. Берет `10` лучших завершенных строк из `stage1/results/summary.csv`.
2. Для каждого кандидата создает `validate-*` job в `stage2/jobs/`.
3. Восстанавливает финальную геометрию `stage1` в `stage1_final.xyz` по оптимизированному `.xyz` или по последнему блоку координат из `output.out`.
4. Строит новый `input.inp` уже с `NumFreq`.
5. После выполнения `collect_stage2_results.py` пишет:
   - `stage2/results/summary.csv`
   - `stage2/results/top10.csv`
   - `stage2/results/validated_minima.csv`
   - `stage2/results/best_result.json`
   - `stage2/results/best_structure.xyz`
   - `stage2/results/final_report.md`
   - `stage2/results/best_verified_minimum.json` как legacy-алиас

`stage2/results/summary.csv` теперь содержит не только энергию, но и поля:

- `nimag`
- `lowest_freq_cm1`
- `is_true_minimum`
- `error_class`
- `final_xyz_available`

### 4.3 Как определяется истинный минимум

В этом репозитории оптимизация сама по себе не считается достаточным доказательством минимума. Структура считается true minimum только если одновременно выполняются условия:

- ORCA завершился нормально
- удалось распарсить `FINAL SINGLE POINT ENERGY`
- после `NumFreq` получено `nimag = 0`

Именно поэтому `stage2` является обязательным этапом, а не косметическим дополнением к `stage1`.

## 5. Статистика выполнения

### 5.1 Общий объем данных

- Полный локальный проект: `289.44 MB`
- Сырые каталоги `stage1/jobs`: `272.76 MB`
- Сырые каталоги `stage2/jobs`: `16.63 MB`
- Курируемый экспорт без тяжелых job-каталогов: около `0.05 MB`

Это важный практический вывод: репозиторий в GitHub стоит собирать из скриптов, конфигов, CSV/JSON-сводок и логов, а не из полных ORCA-рабочих директорий.

### 5.2 Итоги `stage1`

| Метрика | Значение |
| --- | --- |
| Всего job | 108 |
| Успешно завершено | 107 |
| Failed | 1 |
| Completion rate | 99.07% |
| Лучший job | `job-0011` |
| Лучшая структура | `ring`, `1.90 A`, `M = 3` |
| Лучшая энергия | `-148.743338856923 Eh` |
| Отрыв от 2-го места | `0.005552199406 Eh` |
| Отрыв от 2-го места | `3.4841 kcal/mol` |

### 5.3 Итоги `stage2`

| Метрика | Значение |
| --- | --- |
| Кандидатов на валидацию | 10 |
| Успешно завершено | 10 |
| Accepted minima | 8 |
| Rejected by frequencies | 2 |
| Лучший подтвержденный минимум | `validate-001-job-0011` |
| Лучшая подтвержденная энергия | `-148.743338857395 Eh` |
| Отрыв до следующего подтвержденного минимума | `0.006232479690 Eh` |
| Отрыв до следующего подтвержденного минимума | `3.9109 kcal/mol` |

## 6. Детальный разбор `stage1`

### 6.1 Единственный неуспешный job

Проблемная точка:

- `job-0053`
- шаблон: `octahedral_like`
- расстояние: `2.20 A`
- мультиплетность: `3`

Причина сбоя по `output.out`:

- `SCF NOT CONVERGED AFTER 1421 CYCLES`
- `ORCA finished by error termination in LEANSCF`

То есть отказ был не из-за MPI, а из-за неустойчивой SCF-сходимости в конкретной конфигурации.

### 6.2 Лучшие структуры по шаблонам

| Шаблон | Лучший job | Distance, A | M | Energy, Eh | Delta to global best, kcal/mol |
| --- | --- | --- | --- | --- | --- |
| `ring` | `job-0011` | `1.90` | `3` | `-148.743338856923` | `0.0000` |
| `trigonal_prism` | `job-0019` | `1.45` | `1` | `-148.737106377803` | `3.9109` |
| `distorted_prism_1` | `job-0073` | `1.45` | `1` | `-148.737094288566` | `3.9185` |
| `pentagonal_pyramid` | `job-0064` | `1.90` | `1` | `-148.737091827503` | `3.9201` |
| `octahedral_like` | `job-0047` | `1.90` | `3` | `-148.696303343708` | `29.5152` |
| `distorted_octa_1` | `job-0092` | `1.45` | `3` | `-148.696286498766` | `29.5258` |

Ключевой вывод:

- конкурентный энергетический кластер формируют `ring`, `trigonal_prism`, `distorted_prism_1` и `pentagonal_pyramid`
- `octahedral_like` и `distorted_octa_1` заметно хуже, примерно на `29.5 kcal/mol`

### 6.3 Лучшие структуры по мультиплетностям

| M | Лучший job | Шаблон | Distance, A | Energy, Eh | Delta to global best, kcal/mol |
| --- | --- | --- | --- | --- | --- |
| `1` | `job-0019` | `trigonal_prism` | `1.45` | `-148.737106377803` | `3.9109` |
| `3` | `job-0011` | `ring` | `1.90` | `-148.743338856923` | `0.0000` |
| `5` | `job-0069` | `pentagonal_pyramid` | `2.05` | `-148.669785790046` | `46.1552` |

Вывод по спину:

- глобальный минимум найден в триплетном состоянии
- лучшие синглетные кандидаты проигрывают примерно `3.9 kcal/mol`
- квинтетные решения существенно выше по энергии и не выглядят конкурентными

### 6.4 Лучшие структуры по расстояниям

| Distance, A | Лучший job | Шаблон | M | Energy, Eh | Delta to global best, kcal/mol |
| --- | --- | --- | --- | --- | --- |
| `1.45` | `job-0019` | `trigonal_prism` | `1` | `-148.737106377803` | `3.9109` |
| `1.60` | `job-0058` | `pentagonal_pyramid` | `1` | `-148.737091826163` | `3.9201` |
| `1.75` | `job-0061` | `pentagonal_pyramid` | `1` | `-148.737091823269` | `3.9201` |
| `1.90` | `job-0011` | `ring` | `3` | `-148.743338856923` | `0.0000` |
| `2.05` | `job-0014` | `ring` | `3` | `-148.737786657517` | `3.4841` |
| `2.20` | `job-0017` | `ring` | `3` | `-148.737786657090` | `3.4841` |

Вывод по дистанциям:

- локально лучшая точка всего скрининга находится при `1.90 A`
- область `2.05-2.20 A` тоже выглядит очень низкоэнергетичной на `stage1`, но именно там `stage2` показывает, что часть таких решений не являются настоящими минимумами

### 6.5 Топ-10 `stage1`, ушедших на валидацию

| Rank | Stage1 job | Шаблон | Distance, A | M | Energy, Eh |
| --- | --- | --- | --- | --- | --- |
| 1 | `job-0011` | `ring` | `1.90` | `3` | `-148.743338856923` |
| 2 | `job-0014` | `ring` | `2.05` | `3` | `-148.737786657517` |
| 3 | `job-0017` | `ring` | `2.20` | `3` | `-148.737786657090` |
| 4 | `job-0019` | `trigonal_prism` | `1.45` | `1` | `-148.737106377803` |
| 5 | `job-0073` | `distorted_prism_1` | `1.45` | `1` | `-148.737094288566` |
| 6 | `job-0064` | `pentagonal_pyramid` | `1.90` | `1` | `-148.737091827503` |
| 7 | `job-0055` | `pentagonal_pyramid` | `1.45` | `1` | `-148.737091827467` |
| 8 | `job-0067` | `pentagonal_pyramid` | `2.05` | `1` | `-148.737091826342` |
| 9 | `job-0058` | `pentagonal_pyramid` | `1.60` | `1` | `-148.737091826163` |
| 10 | `job-0061` | `pentagonal_pyramid` | `1.75` | `1` | `-148.737091823269` |

Состав top-10:

- `pentagonal_pyramid`: `5`
- `ring`: `3`
- `trigonal_prism`: `1`
- `distorted_prism_1`: `1`

По мультиплетности:

- `M = 1`: `7` кандидатов
- `M = 3`: `3` кандидата

## 7. Детальный разбор `stage2`

### 7.1 Связка `stage1 -> stage2`

| Stage1 job | Stage2 job | Template | Distance, A | M | Stage1 energy, Eh | Stage2 energy, Eh | Accepted |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `job-0011` | `validate-001-job-0011` | `ring` | `1.90` | `3` | `-148.743338856923` | `-148.743338857395` | `yes` |
| `job-0014` | `validate-002-job-0014` | `ring` | `2.05` | `3` | `-148.737786657517` | `-148.737786657125` | `no` |
| `job-0017` | `validate-003-job-0017` | `ring` | `2.20` | `3` | `-148.737786657090` | `-148.737786658046` | `no` |
| `job-0019` | `validate-004-job-0019` | `trigonal_prism` | `1.45` | `1` | `-148.737106377803` | `-148.737106377705` | `yes` |
| `job-0073` | `validate-005-job-0073` | `distorted_prism_1` | `1.45` | `1` | `-148.737094288566` | `-148.737094291299` | `yes` |
| `job-0064` | `validate-006-job-0064` | `pentagonal_pyramid` | `1.90` | `1` | `-148.737091827503` | `-148.737091824339` | `yes` |
| `job-0055` | `validate-007-job-0055` | `pentagonal_pyramid` | `1.45` | `1` | `-148.737091827467` | `-148.737091824857` | `yes` |
| `job-0067` | `validate-008-job-0067` | `pentagonal_pyramid` | `2.05` | `1` | `-148.737091826342` | `-148.737091823436` | `yes` |
| `job-0058` | `validate-009-job-0058` | `pentagonal_pyramid` | `1.60` | `1` | `-148.737091826163` | `-148.737091824060` | `yes` |
| `job-0061` | `validate-010-job-0061` | `pentagonal_pyramid` | `1.75` | `1` | `-148.737091823269` | `-148.737091825588` | `yes` |

### 7.2 Численная согласованность `stage1` и `stage2`

Для топ-10 кандидатов различия между энергиями `stage1` и `stage2` практически нулевые:

- максимальное абсолютное расхождение: `0.003 microhartree`
- среднее абсолютное расхождение: `0.002 microhartree`

Это означает, что `stage2` меняет интерпретацию кандидатов не через заметный пересчет энергии, а через проверку частот и топологии поверхности.

### 7.3 Подтвержденные минимумы

| Rank | Stage2 job | Source job | Template | Distance, A | M | Energy, Eh | Delta to best, kcal/mol |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `validate-001-job-0011` | `job-0011` | `ring` | `1.90` | `3` | `-148.743338857395` | `0.0000` |
| 2 | `validate-004-job-0019` | `job-0019` | `trigonal_prism` | `1.45` | `1` | `-148.737106377705` | `3.9109` |
| 3 | `validate-005-job-0073` | `job-0073` | `distorted_prism_1` | `1.45` | `1` | `-148.737094291299` | `3.9185` |
| 4 | `validate-010-job-0061` | `job-0061` | `pentagonal_pyramid` | `1.75` | `1` | `-148.737091825588` | `3.9201` |
| 5 | `validate-007-job-0055` | `job-0055` | `pentagonal_pyramid` | `1.45` | `1` | `-148.737091824857` | `3.9201` |
| 6 | `validate-006-job-0064` | `job-0064` | `pentagonal_pyramid` | `1.90` | `1` | `-148.737091824339` | `3.9201` |
| 7 | `validate-009-job-0058` | `job-0058` | `pentagonal_pyramid` | `1.60` | `1` | `-148.737091824060` | `3.9201` |
| 8 | `validate-008-job-0067` | `job-0067` | `pentagonal_pyramid` | `2.05` | `1` | `-148.737091823436` | `3.9201` |

Вывод по подтвержденным минимумам:

- глобальный минимум остается `ring (1.90 A, M = 3)`
- `trigonal_prism`, `distorted_prism_1` и кластер `pentagonal_pyramid` образуют плотную группу примерно на `3.91-3.92 kcal/mol` выше
- среди подтвержденных минимумов не осталось ни одного `octahedral_like` или `distorted_octa_1`, потому что они даже не вошли в top-10 `stage1`

### 7.4 Отклоненные кандидаты

| Stage2 job | Source job | Template | Distance, A | M | Energy, Eh | Min freq, cm^-1 | Hard imag count | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `validate-002-job-0014` | `job-0014` | `ring` | `2.05` | `3` | `-148.737786657125` | `-231.71` | `2` | rejected |
| `validate-003-job-0017` | `job-0017` | `ring` | `2.20` | `3` | `-148.737786658046` | `-232.24` | `2` | rejected |

Ключевой вывод:

- обе отклоненные структуры принадлежат к шаблону `ring`
- на одном только энергетическом ранжировании они выглядели очень сильными
- после `NumFreq` выяснилось, что это не минимумы, а седловые точки

Именно ради такого отсечения и нужен `stage2`.

## 8. Научно-практическая интерпретация

По итогам кампании можно аккуратно сформулировать следующее:

1. В рассматриваемой сетке параметров самым устойчивым решением оказался `ring`-мотив при `1.90 A` и `M = 3`.
2. Разница между глобальным минимумом и лучшими синглетными минимумами составляет около `3.9 kcal/mol`, что делает триплетный `ring` явным фаворитом в пределах обследованного пространства.
3. Некоторые энергетически привлекательные `ring`-структуры на больших расстояниях (`2.05 A` и `2.20 A`) после частотной проверки оказываются ложными минимумами.
4. `pentagonal_pyramid` дает очень плотный кластер подтвержденных минимумов, но все они лежат заметно выше глобального минимума.
5. `octahedral_like` и `distorted_octa_1` существенно менее конкурентны уже на уровне `stage1` и не проходят в пул сильнейших кандидатов.

## 9. Где лежат результаты

Основные итоговые артефакты:

- [stage1/results/summary.csv](stage1/results/summary.csv) — полный ранжированный список `stage1`
- [stage1/results/top_finished.csv](stage1/results/top_finished.csv) — верхняя часть успешных `stage1` job
- [stage1/results/best_stage1.json](stage1/results/best_stage1.json) — лучший результат `stage1`
- [stage2/results/summary.csv](stage2/results/summary.csv) — полная сводка `stage2` с `nimag`, `lowest_freq_cm1`, `is_true_minimum` и `error_class`
- [stage2/results/top10.csv](stage2/results/top10.csv) — топ-10 кандидатов `stage2` по энергии
- [stage2/results/validated_minima.csv](stage2/results/validated_minima.csv) — только true minima без мнимых частот
- [stage2/results/best_result.json](stage2/results/best_result.json) — лучший true minimum, попавший в финал
- [stage2/results/best_structure.xyz](stage2/results/best_structure.xyz) — финальная геометрия лучшего минимума
- [stage2/results/final_report.md](stage2/results/final_report.md) — GitHub-ready итоговый отчет
- [stage2/results/best_verified_minimum.json](stage2/results/best_verified_minimum.json) — legacy-алиас для обратной совместимости
- [reports/calculation_results_report.md](reports/calculation_results_report.md) — отдельный отчет только по результатам расчетов
- `reports/fig_stage1_best_by_template.png` и `reports/fig_stage2_validation_rank.png` — графики к результатному отчету
- [stage1/jobs_index.csv](stage1/jobs_index.csv) — манифест полной сетки `stage1`
- [stage2/jobs_index.csv](stage2/jobs_index.csv) — манифест `10` job для валидации

Логи запусков:

- [stage1/stage1_run.log](stage1/stage1_run.log)
- [stage2/stage2_run.log](stage2/stage2_run.log)

## 10. GitHub-ready пакет

Текущая директория и есть подготовленный пакет для импорта в GitHub.

В нее должны входить только публикационно-полезные и легкие файлы:

- `README.md`
- `configs/`
- `stage1/scripts/`
- `stage1/results/`
- `stage1/jobs_index.csv`
- `stage1/stage1_run.log`
- `stage2/scripts/`
- `stage2/results/`
- `stage2/jobs_index.csv`
- `stage2/stage2_run.log`
- `docs/` с пояснениями по экспорту
- `.gitignore`

Сырые ORCA-каталоги `stage1/jobs/` и `stage2/jobs/` в GitHub-пакет включать не стоит: они занимают почти весь объем проекта, содержат бинарные и временные файлы и плохо подходят для обычного Git-репозитория.

## 11. Как запускать

### 11.1 Запуск `stage1`

```bash
cd stage1
python3 scripts/safe_plan.py
ORCA_BIN=/opt/orca/orca bash scripts/run_stage1_parallel_safe.sh
```

Запуск с фиксированным числом параллельных job:

```bash
cd stage1
WORKERS=4 ORCA_BIN=/opt/orca/orca bash scripts/run_stage1_parallel_safe.sh
```

### 11.2 Перезапуск после обрыва

```bash
cd stage1
bash scripts/clean_unfinished.sh
ORCA_BIN=/opt/orca/orca bash scripts/run_stage1_parallel_safe.sh
```

### 11.3 Генерация и запуск `stage2`

```bash
python3 stage2/scripts/generate_stage2_from_stage1.py
cd stage2
ORCA_BIN=/opt/orca/orca bash scripts/run_stage2_parallel_safe.sh
```

## 12. Финальный вывод

Если кратко, то эта кампания уже дала осмысленный и достаточно чистый результат:

- безопасный режим `nprocs=1` практически полностью устранил инфраструктурные сбои
- полный скрининг из `108` точек прошел с одной локальной SCF-ошибкой
- частотная валидация показала, что не все низкоэнергетические кандидаты являются истинными минимумами
- лучший подтвержденный минимум в исследованном пространстве — это `ring`, `1.90 A`, `M = 3`

Именно этот кандидат стоит считать текущим главным результатом проекта.
