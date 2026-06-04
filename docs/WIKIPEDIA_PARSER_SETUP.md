# Wikipedia WC2026 Parser

This parser extracts the current public World Cup 2026 group-stage tables from:

https://en.wikipedia.org/wiki/2026_FIFA_World_Cup

It is not a FIFA API. Use it as a public schedule mirror, then verify against FIFA official pages.

## Local usage

Fetch and parse live page:

```powershell
python -m src.pipelines.update_from_wikipedia
```

If you already saved tables to `data/raw/wiki_tables/`, parse cached files:

```powershell
python -m src.pipelines.update_from_wikipedia --from-cache
```

Then run:

```powershell
python -m src.pipelines.validate_data
python -m pytest -q
```

Outputs:

```text
data/matches_official.csv
data/teams_official.csv
data/processed/matches_current.csv
data/processed/teams_current.csv
data/source_logs/wikipedia_scrape_status.json
```

## Production note

Keep Google Sheets as the control center and manual override. This parser is useful to populate or refresh the official CSVs quickly.
