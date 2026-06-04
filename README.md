
# FIFA World Cup 2026 Intelligence Lab

A public-facing sports analytics project for the FIFA World Cup 2026 combining:

- Group difficulty analysis
- Match prediction
- Monte Carlo group simulation
- Host-city and travel-context layer
- Fan interaction layer
- GitHub-ready project structure
- Streamlit website for public sharing

## Why this project?

The 2026 FIFA World Cup is structurally different from previous editions: 48 teams, 12 groups of four, 104 matches, three host countries, and an extra knockout round. This project treats the tournament as an intelligence product, not just a prediction notebook.

## Current MVP

This repository currently includes a **working Streamlit MVP**:

- `Home`: overview and group difficulty chart
- `Groups Explorer`: group composition and seed ratings
- `Match Predictor`: transparent W/D/L prediction
- `Simulation Lab`: Monte Carlo group-stage simulator
- `Host Cities Map`: map layer for travel-fatigue analysis
- `Fan Zone`: session-based public voting prototype
- `Methodology`: model assumptions and upgrade path

> Important: the current `model_rating_seed` values are starter demo ratings, not official predictions. Replace them with official FIFA rankings, Elo ratings, or a calibrated model before publishing formal claims.

## Project structure

```text
world-cup-2026-intelligence-lab/
├── dashboard/
│   └── app.py
├── data/
│   ├── teams_seed.csv
│   ├── matches_template.csv
│   └── host_cities.csv
├── src/
│   ├── modeling.py
│   └── simulation.py
├── reports/
│   └── report_outline.md
├── requirements.txt
├── README.md
└── .streamlit/config.toml
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run dashboard/app.py
```

## Deploy to Streamlit Community Cloud

1. Push this repository to GitHub.
2. Open Streamlit Community Cloud.
3. Choose the GitHub repository.
4. Set the main file path to:

```text
dashboard/app.py
```

5. Deploy.

## Mobile + laptop workflow

- Use GitHub as the single source of truth.
- Edit documentation and CSV files from mobile.
- Use Google Colab for notebooks and experiments.
- Use laptop or GitHub Codespaces for app and repository structure.
- Every working session ends with `git add`, `git commit`, and `git push`.

## Next roadmap

### v0.2 Data upgrade
- Add official FIFA ranking snapshots.
- Add World Football Elo ratings.
- Add historical international results.
- Standardize team names.

### v0.3 Prediction model
- Calibrated match outcome model.
- Expected goals module.
- Recent-form features.
- Team strength profiles.

### v0.4 Tournament engine
- Full 104-match tournament simulation.
- Round of 32 bracket logic.
- Champion probabilities.
- Upset probability ranking.

### v0.5 Public interaction
- Supabase-backed fan votes.
- User prediction leaderboard.
- Shareable team cards.
- Arabic interface.

## Suggested data sources

- FIFA official World Cup 2026 pages for format, groups, fixtures, and host-city details.
- Public international results datasets for historical matches.
- FIFA rankings or World Football Elo for team-strength modeling.
- Streamlit Community Cloud for free public deployment.

## License

MIT License. Add attribution and data-source notes before public release.
