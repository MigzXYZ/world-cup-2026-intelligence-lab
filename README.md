# FIFA World Cup 2026 Intelligence Lab

A public-facing sports analytics and prediction platform for FIFA World Cup 2026.

It combines:

- Verified data ingestion layer
- Data health validation
- Match prediction
- Expected goals and scoreline probabilities
- Monte Carlo group simulation
- Full tournament simulation fallback
- Host-city and travel-context analysis
- Supabase-ready public fan voting
- Streamlit public website
- GitHub Actions automated data update workflow

## Live demo

Add your Streamlit link here:

```text
https://wc2026-intelligence-lab.streamlit.app/
```

## Important positioning

This is a probabilistic analytics product, not a guaranteed predictor.

The app can run with seed fallback data so the product remains usable while official files are being prepared. However, formal public prediction claims should only be made after:

1. Adding official teams and fixtures.
2. Adding FIFA ranking and/or Elo snapshots.
3. Running the data pipeline.
4. Checking the Data Health page.
5. Backtesting model performance.

## Current app pages

- Home
- Teams Explorer
- Groups Explorer
- Match Predictor
- Group Simulation
- Tournament Simulator
- Travel Intelligence
- Fan Zone
- Results & Tables
- Data Health
- Methodology

## Project structure

```text
world-cup-2026-intelligence-lab/
├── dashboard/
│   └── app.py
├── data/
│   ├── raw/
│   ├── processed/
│   ├── snapshots/
│   ├── source_logs/
│   ├── teams_seed.csv
│   ├── matches_template.csv
│   ├── host_cities.csv
│   └── source_registry.yml
├── docs/
│   └── PRODUCTION_NOTES.md
├── src/
│   ├── data_loader.py
│   ├── modeling.py
│   ├── simulation.py
│   ├── travel.py
│   ├── fan_votes.py
│   ├── backtesting.py
│   ├── data_sources/
│   │   └── remote_csv.py
│   └── pipelines/
│       ├── update_all.py
│       └── validate_data.py
├── sql/
│   └── supabase_schema.sql
├── tests/
├── .github/workflows/
│   ├── python-check.yml
│   └── update_data.yml
├── PUBLIC_LAUNCH_SETUP.md
├── METHODOLOGY.md
├── DATA_DICTIONARY.md
├── ROADMAP.md
├── requirements.txt
└── README.md
```

## Run locally

```bash
pip install -r requirements.txt
python -m src.pipelines.update_all
python -m pytest -q
streamlit run dashboard/app.py
```

## Deploy to Streamlit Community Cloud

Main file path:

```text
dashboard/app.py
```

## Production data flow

```text
Verified CSV files or verified remote CSV URLs
↓
python -m src.pipelines.update_all
↓
data/processed/*_current.csv
↓
data/processed/data_health_report.csv
↓
Streamlit app
```

## Optional automatic update secrets

Add these in GitHub Actions repository secrets if you have verified published CSV URLs:

```text
TEAMS_CSV_URL
MATCHES_CSV_URL
HOST_CITIES_CSV_URL
RANKINGS_CSV_URL
```

## Optional Supabase voting secrets

Add these in Streamlit Cloud secrets:

```toml
SUPABASE_URL = "..."
SUPABASE_KEY = "..."
```

## Built by

Ahmed Magdy | Migz the Analyst
