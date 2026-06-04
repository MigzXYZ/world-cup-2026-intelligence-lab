"""Transparent match modeling layer.

This module is intentionally deterministic and explainable. It supports three layers:
1. Rating/Elo probability model.
2. Poisson goal model.
3. Ensemble blend.

It can run with the current seed data, and automatically becomes stronger when the
user adds FIFA ranking, Elo, recent-form, attack, or defense columns.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, factorial
from typing import Any

import numpy as np
import pandas as pd

EPS = 1e-12


@dataclass(frozen=True)
class MatchModelConfig:
    draw_min: float = 0.14
    draw_max: float = 0.32
    base_expected_goals: float = 1.35
    max_goals: int = 8
    host_rating_bonus: float = 2.0
    elo_weight: float = 0.40
    poisson_weight: float = 0.40
    form_weight: float = 0.10
    context_weight: float = 0.10


def clamp(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def rating_to_elo(rating: float) -> float:
    """Convert a 0-100 public-facing rating to an Elo-like scale."""
    return 1200.0 + float(rating) * 10.0


def safe_numeric(value: Any, default: float = np.nan) -> float:
    try:
        out = float(value)
        if np.isnan(out):
            return default
        return out
    except Exception:
        return default


def minmax_score(series: pd.Series, higher_is_better: bool = True, default: float = 0.50) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.notna().sum() == 0:
        return pd.Series(default, index=series.index, dtype=float)
    vmin, vmax = values.min(), values.max()
    if abs(vmax - vmin) < EPS:
        return pd.Series(default, index=series.index, dtype=float)
    score = (values - vmin) / (vmax - vmin)
    if not higher_is_better:
        score = 1 - score
    return score.fillna(default).clip(0, 1)


def prepare_team_strength(teams: pd.DataFrame, config: MatchModelConfig | None = None) -> pd.DataFrame:
    """Create production-ready strength columns from whatever data exists.

    Required input: team, group, is_host, model_rating_seed/base_rating.
    Optional input: fifa_rank, elo_rating, recent_form, goals_for_pg, goals_against_pg,
    attack_index, defense_index, model_rating.
    """
    config = config or MatchModelConfig()
    df = teams.copy()
    if "base_rating" not in df.columns:
        df["base_rating"] = pd.to_numeric(df.get("model_rating", df.get("model_rating_seed", 70)), errors="coerce").fillna(70)

    df["seed_strength_norm"] = pd.to_numeric(df["base_rating"], errors="coerce").fillna(70).clip(1, 100) / 100.0
    df["elo_norm"] = minmax_score(df.get("elo_rating", pd.Series(np.nan, index=df.index)), higher_is_better=True)
    df["fifa_norm"] = minmax_score(df.get("fifa_rank", pd.Series(np.nan, index=df.index)), higher_is_better=False)
    df["form_norm"] = minmax_score(df.get("recent_form", pd.Series(np.nan, index=df.index)), higher_is_better=True)

    host_bonus_norm = pd.to_numeric(df.get("is_host", 0), errors="coerce").fillna(0).clip(0, 1) * (config.host_rating_bonus / 100.0)
    # If Elo or FIFA fields are missing, their minmax columns default to neutral 0.5.
    df["strength_norm"] = (
        df["seed_strength_norm"] * 0.45
        + df["elo_norm"] * 0.25
        + df["fifa_norm"] * 0.15
        + df["form_norm"] * 0.10
        + host_bonus_norm * 0.05
    ).clip(0.01, 0.99)
    df["model_rating_final"] = (df["strength_norm"] * 100).clip(1, 100)

    if "attack_index" in df.columns and df["attack_index"].notna().any():
        df["attack_strength"] = minmax_score(df["attack_index"], higher_is_better=True, default=0.50) * 1.2 + 0.4
    elif "goals_for_pg" in df.columns and df["goals_for_pg"].notna().any():
        df["attack_strength"] = minmax_score(df["goals_for_pg"], higher_is_better=True, default=0.50) * 1.2 + 0.4
    else:
        df["attack_strength"] = (df["model_rating_final"] / df["model_rating_final"].mean()).clip(0.55, 1.65)

    if "defense_index" in df.columns and df["defense_index"].notna().any():
        df["defense_strength"] = minmax_score(df["defense_index"], higher_is_better=True, default=0.50) * 1.2 + 0.4
    elif "goals_against_pg" in df.columns and df["goals_against_pg"].notna().any():
        # Lower conceded rate means better defense.
        df["defense_strength"] = minmax_score(df["goals_against_pg"], higher_is_better=False, default=0.50) * 1.2 + 0.4
    else:
        df["defense_strength"] = (df["model_rating_final"] / df["model_rating_final"].mean()).clip(0.55, 1.65)

    return df


def elo_expected_score(rating_a: float, rating_b: float) -> float:
    elo_a = rating_to_elo(rating_a)
    elo_b = rating_to_elo(rating_b)
    return float(1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0)))


def dynamic_draw_probability(rating_a: float, rating_b: float, config: MatchModelConfig | None = None) -> float:
    config = config or MatchModelConfig()
    gap = abs(float(rating_a) - float(rating_b))
    draw = 0.30 - gap * 0.006
    return clamp(draw, config.draw_min, config.draw_max)


def rating_model_probabilities(rating_a: float, rating_b: float, config: MatchModelConfig | None = None) -> dict[str, float]:
    config = config or MatchModelConfig()
    expected_a = elo_expected_score(rating_a, rating_b)
    draw = dynamic_draw_probability(rating_a, rating_b, config)
    p_a = expected_a * (1.0 - draw)
    p_b = (1.0 - expected_a) * (1.0 - draw)
    total = p_a + draw + p_b
    return {"team_a_win": p_a / total, "draw": draw / total, "team_b_win": p_b / total}


def poisson_pmf(k: int, lam: float) -> float:
    lam = max(float(lam), 0.01)
    return float((lam**k) * exp(-lam) / factorial(k))


def expected_goals_from_profiles(team_a: pd.Series, team_b: pd.Series, config: MatchModelConfig | None = None) -> tuple[float, float]:
    config = config or MatchModelConfig()
    attack_a = safe_numeric(team_a.get("attack_strength", 1.0), 1.0)
    attack_b = safe_numeric(team_b.get("attack_strength", 1.0), 1.0)
    defense_a = safe_numeric(team_a.get("defense_strength", 1.0), 1.0)
    defense_b = safe_numeric(team_b.get("defense_strength", 1.0), 1.0)
    host_a = config.host_rating_bonus / 100.0 if safe_numeric(team_a.get("is_host", 0), 0) else 0.0
    host_b = config.host_rating_bonus / 100.0 if safe_numeric(team_b.get("is_host", 0), 0) else 0.0

    # Better opponent defense reduces expected goals. Host bonus is intentionally small.
    xg_a = config.base_expected_goals * attack_a / max(defense_b, 0.35) * (1 + host_a)
    xg_b = config.base_expected_goals * attack_b / max(defense_a, 0.35) * (1 + host_b)
    return clamp(xg_a, 0.15, 4.50), clamp(xg_b, 0.15, 4.50)


def poisson_score_matrix(xg_a: float, xg_b: float, max_goals: int = 8) -> np.ndarray:
    probs_a = np.array([poisson_pmf(i, xg_a) for i in range(max_goals + 1)], dtype=float)
    probs_b = np.array([poisson_pmf(j, xg_b) for j in range(max_goals + 1)], dtype=float)
    matrix = np.outer(probs_a, probs_b)
    # Normalize because the tail above max_goals is truncated.
    return matrix / matrix.sum()


def poisson_wdl_probabilities(xg_a: float, xg_b: float, max_goals: int = 8) -> dict[str, float]:
    matrix = poisson_score_matrix(xg_a, xg_b, max_goals=max_goals)
    p_a = float(np.tril(matrix, k=-1).sum())  # i > j sits below diagonal for rows=i cols=j
    draw = float(np.trace(matrix))
    p_b = float(np.triu(matrix, k=1).sum())
    total = p_a + draw + p_b
    return {"team_a_win": p_a / total, "draw": draw / total, "team_b_win": p_b / total}


def top_scorelines(xg_a: float, xg_b: float, max_goals: int = 8, top_n: int = 5) -> list[dict[str, float | int]]:
    matrix = poisson_score_matrix(xg_a, xg_b, max_goals=max_goals)
    rows = []
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            rows.append({"score_a": i, "score_b": j, "probability": float(matrix[i, j])})
    return sorted(rows, key=lambda r: r["probability"], reverse=True)[:top_n]


def blend_probabilities(parts: list[tuple[dict[str, float], float]]) -> dict[str, float]:
    out = {"team_a_win": 0.0, "draw": 0.0, "team_b_win": 0.0}
    weight_sum = 0.0
    for probs, weight in parts:
        if weight <= 0:
            continue
        weight_sum += weight
        for key in out:
            out[key] += probs[key] * weight
    if weight_sum <= EPS:
        return {"team_a_win": 1/3, "draw": 1/3, "team_b_win": 1/3}
    for key in out:
        out[key] /= weight_sum
    total = sum(out.values())
    for key in out:
        out[key] /= total
    return out


def match_prediction(team_a: pd.Series, team_b: pd.Series, config: MatchModelConfig | None = None) -> dict[str, Any]:
    """Return a complete transparent prediction package for two team rows."""
    config = config or MatchModelConfig()
    rating_a = safe_numeric(team_a.get("model_rating_final", team_a.get("base_rating", 70)), 70)
    rating_b = safe_numeric(team_b.get("model_rating_final", team_b.get("base_rating", 70)), 70)

    rating_probs = rating_model_probabilities(rating_a, rating_b, config)
    xg_a, xg_b = expected_goals_from_profiles(team_a, team_b, config)
    poisson_probs = poisson_wdl_probabilities(xg_a, xg_b, max_goals=config.max_goals)

    form_a = safe_numeric(team_a.get("form_norm", 0.5), 0.5)
    form_b = safe_numeric(team_b.get("form_norm", 0.5), 0.5)
    form_expected = form_a / max(form_a + form_b, EPS)
    form_draw = dynamic_draw_probability(rating_a, rating_b, config)
    form_probs = {
        "team_a_win": form_expected * (1 - form_draw),
        "draw": form_draw,
        "team_b_win": (1 - form_expected) * (1 - form_draw),
    }

    # Context is currently host advantage + rating gap sanity layer. Travel can be added by caller later.
    context_probs = rating_probs.copy()

    final_probs = blend_probabilities([
        (rating_probs, config.elo_weight),
        (poisson_probs, config.poisson_weight),
        (form_probs, config.form_weight),
        (context_probs, config.context_weight),
    ])

    scorelines = top_scorelines(xg_a, xg_b, max_goals=config.max_goals, top_n=5)
    return {
        "team_a": team_a.get("team"),
        "team_b": team_b.get("team"),
        "rating_a": rating_a,
        "rating_b": rating_b,
        "xg_a": xg_a,
        "xg_b": xg_b,
        "rating_model": rating_probs,
        "poisson_model": poisson_probs,
        "final": final_probs,
        "top_scorelines": scorelines,
        "explanation": {
            "rating_gap": rating_a - rating_b,
            "team_a_attack_strength": safe_numeric(team_a.get("attack_strength", 1.0), 1.0),
            "team_b_attack_strength": safe_numeric(team_b.get("attack_strength", 1.0), 1.0),
            "team_a_defense_strength": safe_numeric(team_a.get("defense_strength", 1.0), 1.0),
            "team_b_defense_strength": safe_numeric(team_b.get("defense_strength", 1.0), 1.0),
        },
    }


def match_probabilities(rating_a: float, rating_b: float) -> dict[str, float]:
    """Backward-compatible helper used by older app versions/tests."""
    return rating_model_probabilities(rating_a, rating_b)


def knockout_win_probability(team_a: pd.Series, team_b: pd.Series, config: MatchModelConfig | None = None) -> float:
    pred = match_prediction(team_a, team_b, config)
    probs = pred["final"]
    rating_a = safe_numeric(team_a.get("model_rating_final", team_a.get("base_rating", 70)), 70)
    rating_b = safe_numeric(team_b.get("model_rating_final", team_b.get("base_rating", 70)), 70)
    strength_share_a = rating_a / max(rating_a + rating_b, EPS)
    return clamp(probs["team_a_win"] + probs["draw"] * strength_share_a, 0.01, 0.99)


def upset_probability(favorite_rating: float, underdog_rating: float) -> float:
    probs = rating_model_probabilities(underdog_rating, favorite_rating)
    return probs["team_a_win"]
