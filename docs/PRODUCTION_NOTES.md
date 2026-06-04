# Production Notes

## What is now production-ready?

- Streamlit multi-page app
- Processed data layer
- Source logs
- Data validation report
- GitHub Actions update workflow
- Supabase-ready public votes
- Group simulation
- Tournament simulation fallback
- Travel burden engine
- Match predictor with rating, Poisson, form, and context layers

## What still depends on the user?

The model cannot create official facts. The user must provide or verify:

1. Official teams and groups.
2. Official fixtures and match venues.
3. Finished match scores during tournament.
4. FIFA ranking snapshots or verified ranking CSV.
5. Elo rating snapshots or verified ranking CSV.
6. Supabase credentials if persistent public votes are required.

## Why this is necessary

A reliable prediction product separates facts from estimates:

- Facts: teams, fixtures, scores, venues, rankings snapshot date.
- Estimates: probabilities, expected goals, qualification odds.

The app validates facts and clearly labels estimates.
