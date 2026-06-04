"""Data loading, validation, and normalization helpers for WC26 Intelligence Lab."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"

REQUIRED_TEAM_COLUMNS = {"group", "team", "confederation", "is_host"}
REQUIRED_MATCH_COLUMNS = {"match_id", "stage", "team_a", "team_b", "status"}


@dataclass(frozen=True)
class DataBundle:
    teams: pd.DataFrame
    matches: pd.DataFrame
    cities: pd.DataFrame
    stadiums: pd.DataFrame


def _first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def read_csv_if_exists(path: Path, default: pd.DataFrame | None = None) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame() if default is None else default.copy()


def clean_team_name(name: object) -> str:
    if pd.isna(name):
        return ""
    return " ".join(str(name).strip().split())


def normalize_bool(value: object) -> int:
    if pd.isna(value):
        return 0
    if isinstance(value, (int, float)):
        return int(value != 0)
    text = str(value).strip().lower()
    return int(text in {"1", "true", "yes", "y", "host", "co-host"})


def normalize_teams(teams: pd.DataFrame) -> pd.DataFrame:
    teams = teams.copy()
    missing = REQUIRED_TEAM_COLUMNS - set(teams.columns)
    if missing:
        raise ValueError(f"teams data is missing required columns: {sorted(missing)}")

    teams["team"] = teams["team"].map(clean_team_name)
    teams["group"] = teams["group"].astype(str).str.strip()
    teams["confederation"] = teams["confederation"].fillna("Unknown").astype(str).str.strip()
    teams["is_host"] = teams["is_host"].map(normalize_bool)

    if "team_id" not in teams.columns:
        teams["team_id"] = teams["team"].str.lower().str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_")

    if "model_rating_seed" not in teams.columns:
        # If no rating is present, start neutral and let optional Elo/FIFA fields improve it.
        teams["model_rating_seed"] = 70.0
    teams["model_rating_seed"] = pd.to_numeric(teams["model_rating_seed"], errors="coerce").fillna(70.0).clip(1, 100)

    optional_numeric_defaults = {
        "fifa_rank": np.nan,
        "elo_rating": np.nan,
        "recent_form": np.nan,
        "goals_for_pg": np.nan,
        "goals_against_pg": np.nan,
        "attack_index": np.nan,
        "defense_index": np.nan,
        "model_rating": np.nan,
    }
    for col, default in optional_numeric_defaults.items():
        if col not in teams.columns:
            teams[col] = default
        teams[col] = pd.to_numeric(teams[col], errors="coerce")

    # A production model can override model_rating with a prepared value. Otherwise use seed.
    teams["base_rating"] = teams["model_rating"].fillna(teams["model_rating_seed"]).clip(1, 100)

    if teams["team"].duplicated().any():
        dupes = teams.loc[teams["team"].duplicated(), "team"].tolist()
        raise ValueError(f"duplicated team names detected: {dupes}")

    group_sizes = teams.groupby("group")["team"].count()
    # Keep warning-like metadata instead of blocking the app when user is updating data.
    teams.attrs["group_size_warnings"] = group_sizes[group_sizes != 4].to_dict()
    return teams.sort_values(["group", "base_rating"], ascending=[True, False]).reset_index(drop=True)


def normalize_matches(matches: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    matches = matches.copy()
    missing = REQUIRED_MATCH_COLUMNS - set(matches.columns)
    if missing:
        raise ValueError(f"matches data is missing required columns: {sorted(missing)}")

    if "group" not in matches.columns:
        group_map = dict(zip(teams["team"], teams["group"]))
        matches["group"] = matches["team_a"].map(group_map)

    for col in ["team_a", "team_b"]:
        matches[col] = matches[col].map(clean_team_name)
    matches["stage"] = matches["stage"].fillna("Group Stage").astype(str)
    matches["status"] = matches["status"].fillna("scheduled").astype(str).str.lower().str.strip()
    matches["match_id"] = matches["match_id"].astype(str)

    for col in ["score_a", "score_b"]:
        if col not in matches.columns:
            matches[col] = np.nan
        matches[col] = pd.to_numeric(matches[col], errors="coerce")

    for col in ["date", "time_local", "venue", "city", "country"]:
        if col not in matches.columns:
            matches[col] = ""
        matches[col] = matches[col].fillna("").astype(str)

    valid_teams = set(teams["team"])
    bad = sorted((set(matches["team_a"]) | set(matches["team_b"])) - valid_teams)
    matches.attrs["unknown_team_warnings"] = bad
    return matches.reset_index(drop=True)


def generate_group_matches(teams: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    match_id = 1
    for group, gdf in teams.groupby("group", sort=True):
        group_teams = gdf["team"].tolist()
        for i in range(len(group_teams)):
            for j in range(i + 1, len(group_teams)):
                rows.append({
                    "match_id": str(match_id),
                    "stage": "Group Stage",
                    "group": group,
                    "team_a": group_teams[i],
                    "team_b": group_teams[j],
                    "status": "scheduled",
                    "score_a": np.nan,
                    "score_b": np.nan,
                    "date": "",
                    "time_local": "",
                    "venue": "",
                    "city": "",
                    "country": "",
                })
                match_id += 1
    return pd.DataFrame(rows)


def load_stadiums(cities: pd.DataFrame) -> pd.DataFrame:
    stadium_path = DATA_DIR / "stadiums.csv"
    if stadium_path.exists():
        stadiums = pd.read_csv(stadium_path)
    else:
        stadiums = cities.copy()
        stadiums["stadium_name"] = stadiums["city"].astype(str) + " Stadium"
        stadiums["stadium_id"] = stadiums["city"].str.lower().str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_")
        if "timezone_region" in stadiums.columns and "timezone" not in stadiums.columns:
            stadiums["timezone"] = stadiums["timezone_region"]
        stadiums["capacity"] = np.nan
    for col in ["lat", "lon"]:
        if col in stadiums.columns:
            stadiums[col] = pd.to_numeric(stadiums[col], errors="coerce")
    return stadiums


def load_all_data() -> DataBundle:
    """Load the safest available data layer.

    Priority:
    1. data/processed/*_current.csv generated by the update pipeline.
    2. data/*_official.csv manually verified by the user.
    3. seed/template files, clearly labelled as fallback.
    """
    teams_path = _first_existing([
        PROCESSED_DIR / "teams_current.csv",
        DATA_DIR / "teams_official.csv",
        DATA_DIR / "teams_seed.csv",
    ])
    if teams_path is None:
        raise FileNotFoundError("No teams data found. Expected data/processed/teams_current.csv, data/teams_official.csv, or data/teams_seed.csv")
    teams = normalize_teams(pd.read_csv(teams_path))

    match_path = _first_existing([
        PROCESSED_DIR / "matches_current.csv",
        DATA_DIR / "matches_official.csv",
        DATA_DIR / "matches_template.csv",
    ])
    if match_path is None:
        matches = generate_group_matches(teams)
    else:
        matches = normalize_matches(pd.read_csv(match_path), teams)

    cities_path = _first_existing([
        PROCESSED_DIR / "host_cities_current.csv",
        DATA_DIR / "host_cities_official.csv",
        DATA_DIR / "host_cities.csv",
    ])
    cities = read_csv_if_exists(cities_path) if cities_path is not None else pd.DataFrame()
    if not cities.empty:
        for col in ["lat", "lon"]:
            if col in cities.columns:
                cities[col] = pd.to_numeric(cities[col], errors="coerce")
    stadiums = load_stadiums(cities) if not cities.empty else pd.DataFrame()
    return DataBundle(teams=teams, matches=matches, cities=cities, stadiums=stadiums)
