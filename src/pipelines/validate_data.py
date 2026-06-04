"""Data validation layer for the WC26 Intelligence Lab.

The app must never silently publish incorrect or fabricated data. This module
validates the minimum structural rules and creates a machine-readable health
report for the public dashboard and CI pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"


class DataValidationError(Exception):
    """Raised when a dataset violates a hard production rule."""


@dataclass
class ValidationIssue:
    severity: str
    dataset: str
    check: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "dataset": self.dataset,
            "check": self.check,
            "message": self.message,
        }


def require_columns(df: pd.DataFrame, required: Iterable[str], dataset_name: str, issues: list[ValidationIssue]) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        issues.append(ValidationIssue("error", dataset_name, "required_columns", f"Missing columns: {missing}"))


def validate_teams(teams: pd.DataFrame, *, strict: bool = False) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    require_columns(teams, ["team", "group", "confederation", "is_host"], "teams", issues)
    if issues:
        return issues

    if teams["team"].isna().any() or (teams["team"].astype(str).str.strip() == "").any():
        issues.append(ValidationIssue("error", "teams", "team_names", "Missing or blank team names found."))

    dupes = teams.loc[teams["team"].duplicated(), "team"].tolist()
    if dupes:
        issues.append(ValidationIssue("error", "teams", "duplicates", f"Duplicate team names: {dupes}"))

    if len(teams) != 48:
        severity = "error" if strict else "warning"
        issues.append(ValidationIssue(severity, "teams", "team_count", f"Expected 48 teams, found {len(teams)}."))

    group_sizes = teams.groupby("group")["team"].count().to_dict()
    bad_groups = {g: n for g, n in group_sizes.items() if n != 4}
    if bad_groups:
        severity = "error" if strict else "warning"
        issues.append(ValidationIssue(severity, "teams", "group_size", f"Each group should have 4 teams. Bad groups: {bad_groups}"))

    if "model_rating_seed" in teams.columns and "strength_source" not in teams.columns:
        issues.append(ValidationIssue("warning", "teams", "seed_rating", "Seed ratings exist. Do not treat them as official predictions."))

    return issues


def validate_matches(matches: pd.DataFrame, teams: pd.DataFrame | None = None, *, strict: bool = False) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    require_columns(matches, ["match_id", "stage", "team_a", "team_b", "status"], "matches", issues)
    if issues:
        return issues

    if matches["match_id"].duplicated().any():
        issues.append(ValidationIssue("error", "matches", "match_id", "Duplicate match_id values found."))

    allowed = {"scheduled", "live", "finished", "postponed", "cancelled", "delayed"}
    invalid = sorted(set(matches["status"].dropna().astype(str).str.lower()) - allowed)
    if invalid:
        issues.append(ValidationIssue("error", "matches", "status", f"Invalid statuses: {invalid}"))

    for col in ["score_a", "score_b"]:
        if col not in matches.columns:
            issues.append(ValidationIssue("warning", "matches", col, f"{col} is missing. Finished match validation will be limited."))

    if {"score_a", "score_b"}.issubset(matches.columns):
        finished = matches[matches["status"].astype(str).str.lower() == "finished"]
        missing_scores = finished[["score_a", "score_b"]].isna().any(axis=1) if not finished.empty else pd.Series(dtype=bool)
        if missing_scores.any():
            issues.append(ValidationIssue("error", "matches", "finished_scores", "Finished matches must have both score_a and score_b."))

    if teams is not None and not teams.empty:
        known = set(teams["team"].astype(str))
        used = set(matches["team_a"].astype(str)) | set(matches["team_b"].astype(str))
        unknown = sorted([t for t in used - known if t and t.lower() != "nan"])
        if unknown:
            severity = "error" if strict else "warning"
            issues.append(ValidationIssue(severity, "matches", "unknown_teams", f"Unknown teams in matches: {unknown[:25]}"))

    return issues


def validate_rankings(rankings: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    require_columns(rankings, ["team", "source", "rating_value", "snapshot_date"], "rankings", issues)
    if issues:
        return issues
    if rankings["team"].isna().any():
        issues.append(ValidationIssue("error", "rankings", "team", "Missing team values."))
    if pd.to_numeric(rankings["rating_value"], errors="coerce").isna().any():
        issues.append(ValidationIssue("error", "rankings", "rating_value", "Missing or non-numeric rating values."))
    return issues


def build_health_report(teams: pd.DataFrame, matches: pd.DataFrame, rankings: pd.DataFrame | None = None, *, strict: bool = False) -> pd.DataFrame:
    issues: list[ValidationIssue] = []
    issues.extend(validate_teams(teams, strict=strict))
    issues.extend(validate_matches(matches, teams, strict=strict))
    if rankings is not None and not rankings.empty:
        issues.extend(validate_rankings(rankings))

    if not issues:
        issues.append(ValidationIssue("ok", "all", "health", "All required validation checks passed."))

    report = pd.DataFrame([i.to_dict() for i in issues])
    report.insert(0, "checked_at_utc", datetime.now(timezone.utc).isoformat())
    return report


def write_health_report(teams: pd.DataFrame, matches: pd.DataFrame, rankings: pd.DataFrame | None = None, *, strict: bool = False) -> pd.DataFrame:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    report = build_health_report(teams, matches, rankings, strict=strict)
    report.to_csv(PROCESSED_DIR / "data_health_report.csv", index=False)
    hard_errors = report[report["severity"] == "error"]
    if strict and not hard_errors.empty:
        raise DataValidationError("Data validation failed: " + "; ".join(hard_errors["message"].tolist()))
    return report


if __name__ == "__main__":
    teams_path = PROCESSED_DIR / "teams_current.csv"
    matches_path = PROCESSED_DIR / "matches_current.csv"
    rankings_path = PROCESSED_DIR / "rankings_current.csv"
    if not teams_path.exists() or not matches_path.exists():
        raise SystemExit("Processed teams/matches files not found. Run python -m src.pipelines.update_all first.")
    teams_df = pd.read_csv(teams_path)
    matches_df = pd.read_csv(matches_path)
    rankings_df = pd.read_csv(rankings_path) if rankings_path.exists() else None
    rep = write_health_report(teams_df, matches_df, rankings_df, strict=True)
    print(rep.to_string(index=False))
