"""Build current production datasets from verified inputs.

Usage:
    python -m src.pipelines.update_all

Free production strategy:
1. Remote CSV URLs from GitHub Actions secrets/env vars.
2. Local official files in data/.
3. API-Football only if API_FOOTBALL_ENABLED=true.
4. Current seed/template files as clearly labelled fallback.

This avoids burning API quota or printing errors when a free API plan cannot access World Cup 2026.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.data_loader import normalize_matches, normalize_teams
from src.modeling import prepare_team_strength
from src.data_sources.remote_csv import load_remote_csv_from_env
from src.pipelines.validate_data import write_health_report

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
LOGS = DATA / "source_logs"


def _read_local_first(paths: list[Path]) -> tuple[pd.DataFrame | None, str | None]:
    for path in paths:
        if path.exists():
            return pd.read_csv(path), str(path.relative_to(ROOT))
    return None, None


def _save(df: pd.DataFrame, name: str) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED / name, index=False)


def _source_log(source_name: str, source_type: str, source_ref: str, row_count: int) -> dict:
    return {
        "source_name": source_name,
        "source_type": source_type,
        "source_ref": source_ref,
        "row_count": int(row_count),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def api_football_enabled() -> bool:
    return os.getenv("API_FOOTBALL_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def load_teams_source() -> tuple[pd.DataFrame, dict]:
    # Preferred free production source: published verified CSV.
    remote = load_remote_csv_from_env("TEAMS_CSV_URL", output_name="teams_remote.csv")
    if remote is not None:
        return remote, _source_log("teams", "remote_csv_verified", "TEAMS_CSV_URL", len(remote))

    # Optional paid/API mode. Disabled by default because free API-Football cannot access WC 2026 fixtures/teams.
    if api_football_enabled() and os.getenv("API_FOOTBALL_KEY"):
        try:
            from src.data_sources.api_football import (
                fetch_standings_as_teams as fetch_api_football_standings_as_teams,
            )
            api_teams = fetch_api_football_standings_as_teams()
            if api_teams is not None and not api_teams.empty and api_teams.get("team", pd.Series(dtype=str)).nunique() >= 32:
                return api_teams, _source_log(
                    "teams",
                    "api_football_standings",
                    "API-Football standings league=1 season=2026",
                    len(api_teams),
                )
        except Exception as exc:
            print(f"API-Football teams fetch skipped/failed: {exc}")

    df, src = _read_local_first([DATA / "teams_official.csv", DATA / "teams_seed.csv"])
    if df is None:
        raise FileNotFoundError("No teams source found.")
    source_type = "official_local" if src and "official" in src else "seed_fallback"
    return df, _source_log("teams", source_type, src or "unknown", len(df))


def load_matches_source(teams: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    # Preferred free production source: published verified CSV.
    remote = load_remote_csv_from_env("MATCHES_CSV_URL", output_name="matches_remote.csv")
    if remote is not None:
        return remote, _source_log("matches", "remote_csv_verified", "MATCHES_CSV_URL", len(remote))

    # Optional paid/API mode. Disabled by default because free API-Football cannot access WC 2026 fixtures/teams.
    if api_football_enabled() and os.getenv("API_FOOTBALL_KEY"):
        try:
            from src.data_sources.api_football import fetch_fixtures as fetch_api_football_fixtures
            api_matches = fetch_api_football_fixtures()
            if api_matches is not None and not api_matches.empty:
                return api_matches, _source_log(
                    "matches",
                    "api_football_fixtures",
                    "API-Football fixtures league=1 season=2026",
                    len(api_matches),
                )
        except Exception as exc:
            print(f"API-Football fixtures fetch skipped/failed: {exc}")

    df, src = _read_local_first([DATA / "matches_official.csv", DATA / "matches_template.csv"])
    if df is None:
        from src.data_loader import generate_group_matches
        generated = generate_group_matches(teams)
        return generated, _source_log("matches", "generated_from_teams", "no local matches file", len(generated))
    source_type = "official_local" if src and "official" in src else "template_fallback"
    return df, _source_log("matches", source_type, src or "unknown", len(df))


def load_cities_source() -> tuple[pd.DataFrame, dict]:
    remote = load_remote_csv_from_env("HOST_CITIES_CSV_URL", output_name="host_cities_remote.csv")
    if remote is not None:
        return remote, _source_log("host_cities", "remote_csv_verified", "HOST_CITIES_CSV_URL", len(remote))
    df, src = _read_local_first([DATA / "host_cities_official.csv", DATA / "host_cities.csv"])
    if df is None:
        return pd.DataFrame(), _source_log("host_cities", "missing", "none", 0)
    return df, _source_log("host_cities", "local", src or "unknown", len(df))


def optional_rankings() -> tuple[pd.DataFrame, dict | None]:
    remote = load_remote_csv_from_env("RANKINGS_CSV_URL", output_name="rankings_remote.csv")
    if remote is not None:
        return remote, _source_log("rankings", "remote_csv_verified", "RANKINGS_CSV_URL", len(remote))
    df, src = _read_local_first([DATA / "rankings_current.csv", DATA / "fifa_rankings.csv", DATA / "elo_ratings.csv"])
    if df is None:
        return pd.DataFrame(), None
    return df, _source_log("rankings", "local", src or "unknown", len(df))


def merge_rankings_into_teams(teams: pd.DataFrame, rankings: pd.DataFrame) -> pd.DataFrame:
    if rankings is None or rankings.empty:
        return teams

    df = teams.copy()
    r = rankings.copy()

    if "team" not in r.columns:
        return df

    # Accept long format: team,source,rating_value,rank,snapshot_date
    if {"source", "rating_value"}.issubset(r.columns):
        low = r["source"].astype(str).str.lower()

        fifa_points = r[low.str.contains("fifa", na=False)].copy()
        if not fifa_points.empty:
            fifa_points = fifa_points[["team", "rating_value"]].rename(columns={"rating_value": "fifa_points"})
            df = df.drop(columns=["fifa_points"], errors="ignore").merge(fifa_points, on="team", how="left")

        fifa_rank = r[low.str.contains("fifa", na=False)].copy()
        if "rank" in fifa_rank.columns and not fifa_rank.empty:
            fifa_rank = fifa_rank[["team", "rank"]].rename(columns={"rank": "fifa_rank"})
            df = df.drop(columns=["fifa_rank"], errors="ignore").merge(fifa_rank, on="team", how="left")

        elo = r[low.str.contains("elo", na=False)].copy()
        if not elo.empty:
            elo = elo[["team", "rating_value"]].rename(columns={"rating_value": "elo_rating"})
            df = df.drop(columns=["elo_rating"], errors="ignore").merge(elo, on="team", how="left")

    # Accept wide format: team,fifa_rank,fifa_points,elo_rating
    else:
        keep = [c for c in ["team", "fifa_rank", "fifa_points", "elo_rating", "snapshot_date"] if c in r.columns]
        if keep:
            df = df.merge(r[keep].drop_duplicates("team"), on="team", how="left", suffixes=("", "_ranking"))
            for col in ["fifa_rank", "fifa_points", "elo_rating"]:
                alt = f"{col}_ranking"
                if alt in df.columns:
                    df[col] = df[col].combine_first(df[alt]) if col in df.columns else df[alt]
                    df = df.drop(columns=[alt])

    return df


def build_team_features(teams: pd.DataFrame) -> pd.DataFrame:
    strength = prepare_team_strength(teams)
    cols = [
        "team",
        "group",
        "model_rating_final",
        "strength_norm",
        "attack_strength",
        "defense_strength",
        "model_rating_seed",
        "fifa_rank",
        "fifa_points",
        "elo_rating",
        "recent_form",
        "is_host",
    ]
    return strength[[c for c in cols if c in strength.columns]].copy()


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    logs: list[dict] = []

    raw_teams, log = load_teams_source()
    teams = normalize_teams(raw_teams)
    logs.append(log)

    rankings, rlog = optional_rankings()
    if rlog:
        logs.append(rlog)
        teams = merge_rankings_into_teams(teams, rankings)
        teams = normalize_teams(teams)

    raw_matches, log = load_matches_source(teams)
    matches = normalize_matches(raw_matches, teams)
    logs.append(log)

    cities, log = load_cities_source()
    logs.append(log)

    for col in ["lat", "lon"]:
        if col in cities.columns:
            cities[col] = pd.to_numeric(cities[col], errors="coerce")

    features = build_team_features(teams)
    teams_strength = prepare_team_strength(teams)

    now = datetime.now(timezone.utc).isoformat()
    teams_strength["source_updated_at_utc"] = now
    matches["source_updated_at_utc"] = now

    _save(teams_strength, "teams_current.csv")
    _save(matches, "matches_current.csv")
    _save(cities, "host_cities_current.csv")
    _save(features, "team_features_current.csv")

    if rankings is not None and not rankings.empty:
        _save(rankings, "rankings_current.csv")

    log_df = pd.DataFrame(logs)
    log_df.to_csv(LOGS / "latest_source_log.csv", index=False)

    write_health_report(
        teams_strength,
        matches,
        rankings if rankings is not None and not rankings.empty else None,
        strict=False,
    )

    print("Processed data updated successfully.")
    print(log_df.to_string(index=False))


if __name__ == "__main__":
    main()
