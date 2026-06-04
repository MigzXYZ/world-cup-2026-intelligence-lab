# Public Launch Setup - FIFA World Cup 2026 Intelligence Lab

This guide is designed for a non-technical mobile-first workflow.

## 1. Upload the upgraded project

### Option A - GitHub Codespaces from mobile
1. Open your repository on GitHub.
2. Open **Code > Codespaces > Create codespace on main**.
3. Upload the final ZIP file.
4. In the terminal, run:

```bash
unzip -o wc2026-intelligence-lab-production-upgrade.zip
cp -R wc2026-intelligence-lab-production-upgrade/* .
cp -R wc2026-intelligence-lab-production-upgrade/.[!.]* . 2>/dev/null || true
python -m pip install -r requirements.txt
python -m src.pipelines.update_all
python -m pytest -q
git add .
git commit -m "Upgrade WC26 Intelligence Lab to production data layer"
git push
```

### Option B - Laptop
```bash
git clone https://github.com/MigzXYZ/world-cup-2026-intelligence-lab.git
cd world-cup-2026-intelligence-lab
# copy the new files over the repo
pip install -r requirements.txt
python -m src.pipelines.update_all
python -m pytest -q
git add .
git commit -m "Upgrade WC26 Intelligence Lab to production data layer"
git push
```

## 2. Streamlit deployment

Your app main file remains:

```text
dashboard/app.py
```

After GitHub push, Streamlit Cloud should redeploy automatically.

## 3. Required user inputs for real production reliability

The app works immediately with fallback data, but formal public claims require verified files.

### Required file 1: teams_official.csv
Place it in:

```text
data/teams_official.csv
```

Required columns:

```text
team,group,confederation,is_host
```

Recommended columns:

```text
fifa_rank,fifa_points,elo_rating,recent_form,goals_for_pg,goals_against_pg,attack_index,defense_index,model_rating,notes
```

### Required file 2: matches_official.csv
Place it in:

```text
data/matches_official.csv
```

Required columns:

```text
match_id,stage,group,team_a,team_b,status
```

Recommended columns:

```text
date,time_local,venue,city,country,score_a,score_b,winner,source_updated_at_utc
```

### Required file 3: rankings_current.csv or remote CSV URL
Place it in:

```text
data/rankings_current.csv
```

Supported wide columns:

```text
team,fifa_rank,fifa_points,elo_rating,snapshot_date
```

Supported long columns:

```text
team,source,rating_value,snapshot_date
```

Examples for source:

```text
fifa_rank
elo
```

## 4. Automatic updates with GitHub Actions

The workflow is already added:

```text
.github/workflows/update_data.yml
```

It can update processed files automatically from verified CSV URLs.

Add these GitHub repository secrets only if you have published verified CSV links:

```text
TEAMS_CSV_URL
MATCHES_CSV_URL
HOST_CITIES_CSV_URL
RANKINGS_CSV_URL
```

Where to add:

1. GitHub repo
2. Settings
3. Secrets and variables
4. Actions
5. New repository secret

Then run:

1. Actions
2. Update WC26 Data
3. Run workflow

## 5. Supabase persistent public voting

### Create project
1. Go to Supabase.
2. Create a new project.
3. Open SQL Editor.
4. Run the SQL inside:

```text
sql/supabase_schema.sql
```

### Add Streamlit secrets
In Streamlit Cloud:

1. Open your app.
2. Settings.
3. Secrets.
4. Add:

```toml
SUPABASE_URL = "your_supabase_project_url"
SUPABASE_KEY = "your_supabase_anon_key"
```

5. Save and reboot the app.

## 6. Publication readiness checklist

Before presenting the site as a serious prediction model:

- [ ] `python -m src.pipelines.update_all` runs successfully.
- [ ] `python -m pytest -q` passes.
- [ ] Data Health page has no errors.
- [ ] Source log shows official or verified data sources.
- [ ] Seed fallback is not used for formal claims.
- [ ] Supabase voting is connected if public fan votes are enabled.
- [ ] README includes live demo link.
- [ ] Methodology clearly says predictions are probabilities, not guarantees.

## 7. Strong public wording

Use this:

> This project uses verified tournament data where available, public rating systems, and transparent probabilistic modeling. Predictions are probability estimates, not guarantees.

Do not use this:

> 100% accurate World Cup predictor.
