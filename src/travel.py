"""Travel and schedule difficulty utilities."""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

import numpy as np
import pandas as pd

TZ_OFFSETS = {
    "Pacific": -8,
    "Mountain": -7,
    "Central": -6,
    "Eastern": -5,
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    if any(pd.isna(x) for x in [lat1, lon1, lat2, lon2]):
        return 0.0
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return float(r * c)


def _city_lookup(cities: pd.DataFrame) -> dict[str, dict]:
    if cities is None or cities.empty or "city" not in cities.columns:
        return {}
    return {str(row["city"]): row.to_dict() for _, row in cities.iterrows()}


def add_city_coordinates(matches: pd.DataFrame, cities: pd.DataFrame) -> pd.DataFrame:
    df = matches.copy()
    lookup = _city_lookup(cities)
    for col in ["lat", "lon", "timezone_region"]:
        if col not in df.columns:
            df[col] = np.nan if col in ["lat", "lon"] else ""
    for idx, row in df.iterrows():
        city = str(row.get("city", ""))
        meta = lookup.get(city)
        if meta:
            df.at[idx, "lat"] = meta.get("lat", np.nan)
            df.at[idx, "lon"] = meta.get("lon", np.nan)
            df.at[idx, "timezone_region"] = meta.get("timezone_region", meta.get("timezone", ""))
    return df


def team_schedule(team: str, matches: pd.DataFrame, cities: pd.DataFrame | None = None) -> pd.DataFrame:
    if matches is None or matches.empty:
        return pd.DataFrame()
    df = matches[(matches["team_a"] == team) | (matches["team_b"] == team)].copy()
    if df.empty:
        return df
    if cities is not None and not cities.empty:
        df = add_city_coordinates(df, cities)
    if "date" in df.columns:
        df["date_parsed"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values(["date_parsed", "match_id"], na_position="last")
    return df.reset_index(drop=True)


def calculate_team_travel(team: str, matches: pd.DataFrame, cities: pd.DataFrame) -> dict:
    sched = team_schedule(team, matches, cities)
    if sched.empty or "city" not in sched.columns:
        return {
            "team": team,
            "matches_with_city": 0,
            "total_distance_km": 0.0,
            "city_changes": 0,
            "timezone_shift_hours": 0.0,
            "avg_rest_days": np.nan,
            "travel_burden_score": 0.0,
        }
    sched = sched[sched["city"].astype(str).str.len() > 0].copy()
    if sched.empty:
        return {
            "team": team,
            "matches_with_city": 0,
            "total_distance_km": 0.0,
            "city_changes": 0,
            "timezone_shift_hours": 0.0,
            "avg_rest_days": np.nan,
            "travel_burden_score": 0.0,
        }

    total_dist = 0.0
    city_changes = 0
    tz_shift = 0.0
    rest_days = []
    prev = None
    for _, row in sched.iterrows():
        if prev is not None:
            if row.get("city") != prev.get("city"):
                city_changes += 1
            total_dist += haversine_km(float(prev.get("lat", np.nan)), float(prev.get("lon", np.nan)), float(row.get("lat", np.nan)), float(row.get("lon", np.nan)))
            tz1 = TZ_OFFSETS.get(str(prev.get("timezone_region", "")), 0)
            tz2 = TZ_OFFSETS.get(str(row.get("timezone_region", "")), 0)
            tz_shift += abs(tz2 - tz1)
            if pd.notna(prev.get("date_parsed")) and pd.notna(row.get("date_parsed")):
                rest_days.append((row["date_parsed"] - prev["date_parsed"]).days)
        prev = row
    avg_rest = float(np.mean(rest_days)) if rest_days else np.nan
    # Normalization anchors designed for North America tournament distances.
    score = min(total_dist / 7000, 1.0) * 40 + min(city_changes / 5, 1.0) * 25 + min(tz_shift / 6, 1.0) * 20
    if not np.isnan(avg_rest):
        score -= min(avg_rest / 7, 1.0) * 15
    return {
        "team": team,
        "matches_with_city": int(len(sched)),
        "total_distance_km": round(total_dist, 1),
        "city_changes": int(city_changes),
        "timezone_shift_hours": round(tz_shift, 1),
        "avg_rest_days": round(avg_rest, 2) if not np.isnan(avg_rest) else np.nan,
        "travel_burden_score": round(max(score, 0.0), 2),
    }


def travel_table(teams: pd.DataFrame, matches: pd.DataFrame, cities: pd.DataFrame) -> pd.DataFrame:
    rows = [calculate_team_travel(team, matches, cities) for team in teams["team"].tolist()]
    return pd.DataFrame(rows).sort_values("travel_burden_score", ascending=False).reset_index(drop=True)


def schedule_difficulty(teams: pd.DataFrame, matches: pd.DataFrame, cities: pd.DataFrame) -> pd.DataFrame:
    travel = travel_table(teams, matches, cities)
    rating_map = dict(zip(teams["team"], teams.get("model_rating_final", teams.get("base_rating", teams.get("model_rating_seed", 70)))))
    rows = []
    for team in teams["team"]:
        tm = team_schedule(team, matches, cities)
        opponents = []
        for _, row in tm.iterrows():
            opp = row["team_b"] if row["team_a"] == team else row["team_a"]
            opponents.append(rating_map.get(opp, 70.0))
        opponent_strength = float(np.mean(opponents)) if opponents else 0.0
        trow = travel[travel["team"] == team].iloc[0].to_dict()
        score = opponent_strength * 0.55 + trow["travel_burden_score"] * 0.45
        rows.append({"team": team, "avg_opponent_strength": opponent_strength, **trow, "schedule_difficulty_score": round(score, 2)})
    return pd.DataFrame(rows).sort_values("schedule_difficulty_score", ascending=False).reset_index(drop=True)
