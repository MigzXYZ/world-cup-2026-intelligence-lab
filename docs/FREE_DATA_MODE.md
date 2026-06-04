# Free Data Mode for WC26 Intelligence Lab

API-Football Free can show `World Cup` season 2026 in the leagues search, but free accounts may not access 2026 teams/fixtures. When that happens, use this free production setup:

## Free production source of truth

Use published CSV links from Google Sheets:

- `TEAMS_CSV_URL`
- `MATCHES_CSV_URL`
- `HOST_CITIES_CSV_URL`
- `RANKINGS_CSV_URL`

These are read by GitHub Actions and converted into `data/processed/*.csv`.

## Optional API-Football mode

API-Football is now disabled by default. To enable it later, add these GitHub Actions secrets/variables:

- Secret: `API_FOOTBALL_KEY`
- Variable or secret: `API_FOOTBALL_ENABLED=true`

If the API still rejects season 2026, the pipeline falls back safely.

## Why this mode is better for a free public launch

- No hidden paid dependency
- No visitor-triggered API calls
- No quota burn from Streamlit users
- Full control over official corrections
- Works with GitHub Actions automation
