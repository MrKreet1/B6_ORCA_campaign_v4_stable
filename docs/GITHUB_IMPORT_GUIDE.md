# GitHub Import Guide

Эта директория уже подготовлена для импорта в новый GitHub-репозиторий.

## Вариант 1. Через веб-интерфейс GitHub

1. Создать пустой репозиторий на GitHub.
2. Загрузить содержимое текущей директории `B6_ORCA_campaign_v4_stable`.
3. Проверить, что на GitHub появились:
   - `README.md`
   - `configs/`
   - `stage1/`
   - `stage2/`
   - `docs/`
   - `.gitignore`
4. Отдельно убедиться, что в `stage2/results/` лежат ключевые публикационные артефакты:
   - `summary.csv`
   - `top10.csv`
   - `best_result.json`
   - `final_report.md`
   - `best_structure.xyz` если экспорт делался из полного локального проекта с raw job-данными

## Вариант 2. Через git из терминала

```bash
cd B6_ORCA_campaign_v4_stable
git init
git add .
git commit -m "Add B6 ORCA campaign report and curated results"
git branch -M main
git remote add origin <YOUR_GITHUB_REPO_URL>
git push -u origin main
```

## Что делать с raw ORCA-данными

Если нужно хранить полные рабочие каталоги с `output.out`, `*.gbw`, `*.tmp` и другими тяжелыми файлами:

- лучше держать их локально
- либо выносить в отдельное архивное хранилище
- либо использовать Git LFS только если это действительно требуется
