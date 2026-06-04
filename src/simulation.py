"""Monte Carlo simulation engine for group stage and full tournament scenarios."""
from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

from .modeling import MatchModelConfig, match_prediction, knockout_win_probability, prepare_team_strength

POINTS_WIN = 3
POINTS_DRAW = 1


def _team_row(strength_teams: pd.DataFrame, team: str) -> pd.Series:
    rows = strength_teams.loc[strength_teams["team"] == team]
    if rows.empty:
        raise KeyError(f"Team not found in strength dataframe: {team}")
    return rows.iloc[0]


def _blank_table(teams: list[str]) -> dict[str, dict[str, float]]:
    return {
        team: {"played": 0, "wins": 0, "draws": 0, "losses": 0, "gf": 0, "ga": 0, "gd": 0, "points": 0}
        for team in teams
    }


def _apply_score(table: dict[str, dict[str, float]], a: str, b: str, ga: int, gb: int) -> None:
    table[a]["played"] += 1
    table[b]["played"] += 1
    table[a]["gf"] += ga
    table[a]["ga"] += gb
    table[b]["gf"] += gb
    table[b]["ga"] += ga
    if ga > gb:
        table[a]["wins"] += 1
        table[b]["losses"] += 1
        table[a]["points"] += POINTS_WIN
    elif gb > ga:
        table[b]["wins"] += 1
        table[a]["losses"] += 1
        table[b]["points"] += POINTS_WIN
    else:
        table[a]["draws"] += 1
        table[b]["draws"] += 1
        table[a]["points"] += POINTS_DRAW
        table[b]["points"] += POINTS_DRAW
    table[a]["gd"] = table[a]["gf"] - table[a]["ga"]
    table[b]["gd"] = table[b]["gf"] - table[b]["ga"]


def _sample_scoreline(prediction: dict[str, Any], rng: np.random.Generator) -> tuple[int, int]:
    lines = prediction["top_scorelines"]
    probs = np.array([line["probability"] for line in lines], dtype=float)
    # Top 5 scorelines do not sum to 1. Normalize for efficient realistic sampling.
    # The W/D/L event is already represented by these scorelines sufficiently for MVP simulation.
    probs = probs / probs.sum()
    idx = int(rng.choice(len(lines), p=probs))
    return int(lines[idx]["score_a"]), int(lines[idx]["score_b"])


def _simulate_match_score(
    a: str,
    b: str,
    strength_teams: pd.DataFrame,
    rng: np.random.Generator,
    config: MatchModelConfig | None = None,
) -> tuple[int, int]:
    pred = match_prediction(_team_row(strength_teams, a), _team_row(strength_teams, b), config)
    return _sample_scoreline(pred, rng)


def _match_is_finished(row: pd.Series) -> bool:
    return str(row.get("status", "")).lower() == "finished" and pd.notna(row.get("score_a")) and pd.notna(row.get("score_b"))


def rank_table(table: dict[str, dict[str, float]], strength_teams: pd.DataFrame | None = None, rng: np.random.Generator | None = None) -> pd.DataFrame:
    rows = []
    rating_map = {}
    if strength_teams is not None and not strength_teams.empty:
        rating_map = dict(zip(strength_teams["team"], strength_teams.get("model_rating_final", strength_teams.get("base_rating", 70))))
    rng = rng or np.random.default_rng(42)
    for team, stats in table.items():
        rows.append({
            "team": team,
            **stats,
            "rating_tiebreak": float(rating_map.get(team, 70.0)),
            "random_tiebreak": float(rng.normal(0, 0.0001)),
        })
    df = pd.DataFrame(rows)
    df = df.sort_values(
        ["points", "gd", "gf", "wins", "rating_tiebreak", "random_tiebreak"],
        ascending=[False, False, False, False, False, False],
    ).reset_index(drop=True)
    df["rank"] = np.arange(1, len(df) + 1)
    return df


def group_matches_for(group_df: pd.DataFrame, matches: pd.DataFrame | None = None) -> pd.DataFrame:
    group = group_df["group"].iloc[0]
    teams = group_df["team"].tolist()
    if matches is not None and not matches.empty:
        m = matches[(matches.get("group") == group) & (matches["team_a"].isin(teams)) & (matches["team_b"].isin(teams))]
        if not m.empty:
            return m.copy()
    rows = []
    for idx, (a, b) in enumerate(combinations(teams, 2), start=1):
        rows.append({"match_id": f"{group}-{idx}", "stage": "Group Stage", "group": group, "team_a": a, "team_b": b, "status": "scheduled"})
    return pd.DataFrame(rows)


def simulate_one_group(
    group_df: pd.DataFrame,
    matches: pd.DataFrame | None,
    strength_teams: pd.DataFrame,
    rng: np.random.Generator,
    config: MatchModelConfig | None = None,
) -> pd.DataFrame:
    teams = group_df["team"].tolist()
    table = _blank_table(teams)
    gm = group_matches_for(group_df, matches)
    for _, match in gm.iterrows():
        a, b = str(match["team_a"]), str(match["team_b"])
        if _match_is_finished(match):
            ga, gb = int(match["score_a"]), int(match["score_b"])
        else:
            ga, gb = _simulate_match_score(a, b, strength_teams, rng, config)
        _apply_score(table, a, b, ga, gb)
    ranked = rank_table(table, strength_teams, rng)
    ranked["group"] = group_df["group"].iloc[0]
    return ranked


def simulate_group(group_df: pd.DataFrame, n_sims: int = 5000, seed: int = 42, matches: pd.DataFrame | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    strength = prepare_team_strength(group_df)
    teams = group_df["team"].tolist()
    counters = {team: {"top1": 0, "top2": 0, "top3": 0, "avg_points": 0.0} for team in teams}

    for _ in range(int(n_sims)):
        ranked = simulate_one_group(group_df, matches, strength, rng)
        for _, row in ranked.iterrows():
            counters[row["team"]]["avg_points"] += float(row["points"]) / n_sims
        for team in ranked.head(1)["team"]:
            counters[team]["top1"] += 1
        for team in ranked.head(2)["team"]:
            counters[team]["top2"] += 1
        for team in ranked.head(3)["team"]:
            counters[team]["top3"] += 1

    out = []
    for team in teams:
        out.append({
            "team": team,
            "group": group_df[group_df["team"] == team]["group"].iloc[0],
            "avg_points": counters[team]["avg_points"],
            "finish_1st_prob": counters[team]["top1"] / n_sims,
            "top2_prob": counters[team]["top2"] / n_sims,
            "top3_prob": counters[team]["top3"] / n_sims,
        })
    return pd.DataFrame(out).sort_values(["top2_prob", "avg_points"], ascending=False).reset_index(drop=True)


def group_difficulty(teams_df: pd.DataFrame) -> pd.DataFrame:
    df = prepare_team_strength(teams_df)
    rows = []
    for group, gdf in df.groupby("group"):
        ratings = gdf["model_rating_final"].astype(float)
        rows.append({
            "group": group,
            "avg_rating": ratings.mean(),
            "top_two_avg_rating": ratings.sort_values(ascending=False).head(2).mean(),
            "top_three_avg_rating": ratings.sort_values(ascending=False).head(3).mean(),
            "rating_spread": ratings.max() - ratings.min(),
            "rating_std": ratings.std(ddof=0),
            "group_of_death_score": ratings.mean() * 0.50 + ratings.sort_values(ascending=False).head(3).mean() * 0.40 - ratings.std(ddof=0) * 0.10,
        })
    return pd.DataFrame(rows).sort_values("group_of_death_score", ascending=False).reset_index(drop=True)


def _best_thirds(all_ranked: list[pd.DataFrame], count: int = 8) -> pd.DataFrame:
    thirds = pd.concat([g[g["rank"] == 3] for g in all_ranked], ignore_index=True)
    if thirds.empty:
        return thirds
    return thirds.sort_values(["points", "gd", "gf", "wins", "rating_tiebreak"], ascending=False).head(count).reset_index(drop=True)


def _seed_qualifiers(qualifiers: pd.DataFrame) -> list[str]:
    q = qualifiers.copy()
    q["seed_score"] = q["points"] * 100 + q["gd"] * 10 + q["gf"] + q.get("rating_tiebreak", 70) / 100
    return q.sort_values("seed_score", ascending=False)["team"].tolist()


def _simulate_knockout_round(
    teams_in_round: list[str],
    strength_teams: pd.DataFrame,
    rng: np.random.Generator,
    config: MatchModelConfig | None = None,
) -> list[str]:
    # Model bracket mode: re-seed high vs low. This is a robust fallback when official bracket mapping is absent.
    winners = []
    ordered = teams_in_round[:]
    pairings = list(zip(ordered[: len(ordered)//2], reversed(ordered[len(ordered)//2:])))
    for a, b in pairings:
        pa = knockout_win_probability(_team_row(strength_teams, a), _team_row(strength_teams, b), config)
        winners.append(a if rng.random() < pa else b)
    return winners


def simulate_tournament(
    teams_df: pd.DataFrame,
    matches_df: pd.DataFrame | None = None,
    n_sims: int = 2000,
    seed: int = 42,
    config: MatchModelConfig | None = None,
) -> pd.DataFrame:
    """Simulate a full tournament probability table.

    Uses official/completed group results if they exist in matches_df. Knockout is simulated in
    model-seeded bracket mode unless an official bracket module is added later.
    """
    rng = np.random.default_rng(seed)
    strength = prepare_team_strength(teams_df, config)
    teams = strength["team"].tolist()
    stages = ["round32", "round16", "quarter_final", "semi_final", "final", "champion"]
    counters = {team: {stage: 0 for stage in stages} for team in teams}

    for _ in range(int(n_sims)):
        ranked_groups = []
        for group, gdf in strength.groupby("group"):
            ranked_groups.append(simulate_one_group(gdf, matches_df, strength, rng, config))

        top_two = pd.concat([g[g["rank"].isin([1, 2])] for g in ranked_groups], ignore_index=True)
        best_thirds = _best_thirds(ranked_groups, count=8)
        qualifiers = pd.concat([top_two, best_thirds], ignore_index=True)
        round32 = _seed_qualifiers(qualifiers)
        # Ensure 32 teams. If input data is incomplete, pad/truncate safely.
        round32 = round32[:32]
        for team in round32:
            counters[team]["round32"] += 1

        current = round32
        round_names = ["round16", "quarter_final", "semi_final", "final", "champion"]
        for round_name in round_names:
            if len(current) <= 1:
                break
            winners = _simulate_knockout_round(current, strength, rng, config)
            for team in winners:
                counters[team][round_name] += 1
            current = winners

    rows = []
    for team in teams:
        row = {"team": team, "group": strength.loc[strength["team"] == team, "group"].iloc[0]}
        for stage in stages:
            row[f"{stage}_prob"] = counters[team][stage] / n_sims
        rows.append(row)
    return pd.DataFrame(rows).sort_values("champion_prob", ascending=False).reset_index(drop=True)


def projected_group_tables(teams_df: pd.DataFrame, matches_df: pd.DataFrame | None = None, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    strength = prepare_team_strength(teams_df)
    tables = []
    for _, gdf in strength.groupby("group"):
        tables.append(simulate_one_group(gdf, matches_df, strength, rng))
    return pd.concat(tables, ignore_index=True)
