# Methodology

## 1. Purpose

The FIFA World Cup 2026 Intelligence Lab estimates football probabilities. It does not guarantee results.

The model separates:

- **Facts:** teams, fixtures, scores, venues, official rankings, Elo snapshots.
- **Estimates:** match probabilities, expected goals, qualification odds, champion odds.

## 2. Data reliability

The app uses a processed data layer whenever available:

```text
data/processed/teams_current.csv
data/processed/matches_current.csv
data/processed/host_cities_current.csv
data/processed/team_features_current.csv
data/processed/data_health_report.csv
```

These files are produced by:

```bash
python -m src.pipelines.update_all
```

If processed files are absent, the app falls back to seed/template data, but the UI labels this as fallback mode.

## 3. Team strength

The model prepares a `model_rating_final` from the available columns.

Available components:

- Seed fallback rating
- Elo rating
- FIFA ranking
- Recent form
- Host status
- Attack index
- Defense index

If a component is missing, it is not invented. The model uses neutral handling or fallback logic, and Data Health warns the user.

## 4. Match prediction

The match predictor blends:

1. Rating/Elo-like win probability.
2. Dynamic draw probability.
3. Poisson expected-goals model.
4. Recent-form/context adjustment when available.

Outputs:

- Team A win probability
- Draw probability
- Team B win probability
- Expected goals
- Top scorelines
- Model layer comparison

## 5. Group simulation

Group simulation uses Monte Carlo iterations:

1. Simulate scheduled matches using model probabilities.
2. Use actual scores for finished matches.
3. Rank groups by points, goal difference, goals scored, wins, and rating tie-break fallback.
4. Aggregate probabilities for 1st place, top 2, and top 3.

## 6. Tournament simulation

The current tournament simulator:

1. Simulates all group-stage outcomes.
2. Selects top two from each group.
3. Selects best eight third-place teams.
4. Uses a model-seeded knockout fallback bracket.
5. Outputs stage and champion probabilities.

Important: exact FIFA knockout route replication requires a structured official bracket mapping file.

## 7. Travel intelligence

Travel scores are calculated only when match city/date data is available.

Metrics:

- Total travel distance
- City changes
- Timezone shifts
- Average rest days
- Travel Burden Score
- Schedule Difficulty Score

If city/date fields are missing, the app shows zeros or missing values and explains the limitation.

## 8. Fan intelligence

Fan votes can be stored in Supabase when secrets are configured. Otherwise, the app uses browser-session fallback only.

## 9. Model performance

A prediction model should not be marketed as reliable until backtesting is run against historical tournaments.

Recommended metrics:

- Accuracy
- Brier score
- Log loss
- Calibration curve

## 10. Public wording

Recommended:

> Transparent probabilistic prediction model.

Avoid:

> 100% accurate predictor.
