"""Backtesting utilities for historical validation.

These functions are optional. They run when you provide a historical dataset with:
date, home_team, away_team, home_score, away_score.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .modeling import match_prediction, prepare_team_strength


def actual_outcome(row: pd.Series) -> str:
    if row["home_score"] > row["away_score"]:
        return "team_a_win"
    if row["home_score"] < row["away_score"]:
        return "team_b_win"
    return "draw"


def brier_score(probs: dict[str, float], outcome: str) -> float:
    return float(sum((probs[k] - (1.0 if k == outcome else 0.0)) ** 2 for k in ["team_a_win", "draw", "team_b_win"]))


def log_loss(probs: dict[str, float], outcome: str) -> float:
    p = max(float(probs.get(outcome, 1e-12)), 1e-12)
    return float(-math.log(p))


def backtest_matches(teams: pd.DataFrame, historical_results: pd.DataFrame) -> pd.DataFrame:
    strength = prepare_team_strength(teams)
    rows = []
    for _, match in historical_results.iterrows():
        a = match.get("home_team")
        b = match.get("away_team")
        if a not in set(strength["team"]) or b not in set(strength["team"]):
            continue
        row_a = strength[strength["team"] == a].iloc[0]
        row_b = strength[strength["team"] == b].iloc[0]
        pred = match_prediction(row_a, row_b)
        outcome = actual_outcome(match)
        rows.append({
            "date": match.get("date"),
            "team_a": a,
            "team_b": b,
            "actual_outcome": outcome,
            "predicted_outcome": max(pred["final"], key=pred["final"].get),
            "p_team_a_win": pred["final"]["team_a_win"],
            "p_draw": pred["final"]["draw"],
            "p_team_b_win": pred["final"]["team_b_win"],
            "brier_score": brier_score(pred["final"], outcome),
            "log_loss": log_loss(pred["final"], outcome),
        })
    return pd.DataFrame(rows)


def backtest_summary(backtest_df: pd.DataFrame) -> dict[str, float]:
    if backtest_df.empty:
        return {"matches": 0, "accuracy": np.nan, "avg_brier_score": np.nan, "avg_log_loss": np.nan}
    return {
        "matches": int(len(backtest_df)),
        "accuracy": float((backtest_df["actual_outcome"] == backtest_df["predicted_outcome"]).mean()),
        "avg_brier_score": float(backtest_df["brier_score"].mean()),
        "avg_log_loss": float(backtest_df["log_loss"].mean()),
    }
