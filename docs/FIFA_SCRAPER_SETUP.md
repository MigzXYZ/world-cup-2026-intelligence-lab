# FIFA Direct Scraper Setup

This scraper tries to extract WC2026 schedule data from the official FIFA schedule page:

https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/match-schedule-fixtures-results-teams-stadiums

## Important reality check

FIFA does not provide a simple free public REST API for all official WC2026 data. The scraper is a best-effort official-page extractor.

It will:
- save the raw FIFA HTML and text for audit;
- try embedded JSON first;
- try rendered HTML if Playwright is enabled;
- parse match cards/text where possible;
- refuse to overwrite official files if fewer than 72 group-stage matches are found, unless `--allow-partial` is passed.

It will not:
- bypass paywalls or access controls;
- spam FIFA;
- invent missing data.

## Local usage

Install scraper dependencies:

```powershell
pip install -r requirements-fifa-scraper.txt
python -m playwright install chromium
```

Try non-rendered mode:

```powershell
python -m src.pipelines.update_from_fifa
```

If it fails because FIFA is dynamic, try rendered mode:

```powershell
python -m src.pipelines.update_from_fifa --rendered
```

If you want to inspect partial extraction:

```powershell
python -m src.data_sources.fifa_official_scraper --rendered --allow-partial
```

Raw files are saved to:

```text
data/raw/fifa_schedule_page.html
data/raw/fifa_schedule_page_text.txt
data/source_logs/fifa_scrape_status.json
```

## GitHub Actions

A workflow is included:

```text
.github/workflows/fifa_scraper.yml
```

Run it from:

```text
GitHub → Actions → Scrape FIFA Official Schedule → Run workflow
```

Use `rendered=true`.

## Production recommendation

Use this scraper as a low-frequency official data check. Keep Google Sheets CSV as your manual override/control layer.
