# API-Football Automation Setup

This project can use API-Football as the primary automated data source for World Cup 2026 fixtures and results.

## Required GitHub Secret

Add this under:

`GitHub Repo > Settings > Secrets and variables > Actions > New repository secret`

```text
API_FOOTBALL_KEY=your_api_football_key
```

## Optional GitHub Variables

Under:

`Settings > Secrets and variables > Actions > Variables`

```text
API_FOOTBALL_LEAGUE_ID=1
API_FOOTBALL_SEASON=2026
```

The defaults are already `1` and `2026`, so these variables are optional.

## Local Test

PowerShell:

```powershell
$env:API_FOOTBALL_KEY="PASTE_YOUR_REAL_KEY_HERE"
python -m src.pipelines.update_all
python -m src.pipelines.validate_data
python -m pytest -q
```

Then run:

```powershell
streamlit run dashboard/app.py
```

Open the Data Health page and check the source log.

## Fallback Logic

The pipeline uses this order:

1. API-Football fixtures/standings if `API_FOOTBALL_KEY` is available and the API returns data.
2. Google Sheets/remote CSV if CSV URL secrets are available.
3. Local official CSV files if present.
4. Local seed/template fallback.

The app should never invent missing data. Missing or unavailable API data falls back to a clearly labeled source.
