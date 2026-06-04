"""API-Football connector for FIFA World Cup 2026.

This connector is intentionally conservative:
- It reads API_FOOTBALL_KEY from environment variables.
- It never invents missing values.
- It returns empty DataFrames if the API has no current coverage.
- The pipeline can then fall back to Google Sheets/local official CSV/seed data.

API-Football league id for men's World Cup: 1
Default season: 2026
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://v3.football.api-sports.io"
DEFAULT_LEAGUE_ID = int(os.getenv("API_FOOTBALL_LEAGUE_ID", "1"))
DEFAULT_SEASON = int(os.getenv("API_FOOTBALL_SEASON", "2026"))


class APIFootballError(RuntimeError):
    """Raised when API-Football cannot be queried successfully."""


def has_api_football_key() -> bool:
    return bool(os.getenv("API_FOOTBALL_KEY") or os.getenv("API_SPORTS_KEY"))


def _headers() -> dict[str, str]:
    key = os.getenv("API_FOOTBALL_KEY") or os.getenv("API_SPORTS_KEY")
    if not key:
        raise APIFootballError("API_FOOTBALL_KEY is not set.")
    return {"x-apisports-key": key}


def _get(endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    response = requests.get(url, headers=_headers(), params=params or {}, timeout=30)

    try:
        data = response.json()
    except ValueError as exc:
        raise APIFootballError(f"API-Football returned non-JSON response: {response.text[:300]}") from exc

    if response.status_code >= 400:
        raise APIFootballError(
            f"API-Football HTTP {response.status_code}: {str(data)[:500]}"
        )

    errors = data.get("errors")
    if errors:
        raise APIFootballError(f"API-Football error: {errors}")

    return data


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_status(short_status: str | None, long_status: str | None = None) -> str:
    value = (short_status or long_status or "").upper()
    if value in {"NS", "TBD", "PST"}:
        return "scheduled" if value != "PST" else "postponed"
    if value in {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"}:
        return "live"
    if value in {"FT", "AET", "PEN"}:
        return "finished"
    if value in {"CANC", "ABD", "AWD", "WO"}:
        return "cancelled"
    if value in {"PST", "SUSP"}:
        return "postponed"
    return "scheduled"


def _stage_from_round(round_name: str) -> str:
    text = (round_name or "").lower()
    if "group" in text:
        return "Group Stage"
    if "round of 32" in text:
        return "Round of 32"
    if "round of 16" in text or "1/8" in text:
        return "Round of 16"
    if "quarter" in text:
        return "Quarter-finals"
    if "semi" in text:
        return "Semi-finals"
    if "final" in text:
        return "Final"
    return round_name or "Unknown"


def _extract_date_time(date_value: str | None) -> tuple[str, str]:
    if not date_value:
        return "", ""
    try:
        dt = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
        return dt.date().isoformat(), dt.strftime("%H:%M")
    except ValueError:
        return str(date_value)[:10], str(date_value)[11:16] if len(str(date_value)) >= 16 else ""


def fetch_fixtures(league_id: int = DEFAULT_LEAGUE_ID, season: int = DEFAULT_SEASON) -> pd.DataFrame:
    """Fetch World Cup fixtures/results and convert them to matches_current schema."""
    data = _get("fixtures", params={"league": league_id, "season": season})
    rows: list[dict[str, Any]] = []

    for item in data.get("response", []) or []:
        fixture = item.get("fixture") or {}
        league = item.get("league") or {}
        teams = item.get("teams") or {}
        goals = item.get("goals") or {}
        score = item.get("score") or {}
        fulltime = score.get("fulltime") or {}
        venue = fixture.get("venue") or {}
        status = fixture.get("status") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}

        date_part, time_part = _extract_date_time(fixture.get("date"))
        score_a = fulltime.get("home")
        score_b = fulltime.get("away")
        if score_a is None:
            score_a = goals.get("home")
        if score_b is None:
            score_b = goals.get("away")

        winner = ""
        if home.get("winner") is True:
            winner = home.get("name") or ""
        elif away.get("winner") is True:
            winner = away.get("name") or ""
        elif score_a is not None and score_b is not None and score_a == score_b:
            winner = "Draw"

        rows.append({
            "match_id": fixture.get("id"),
            "stage": _stage_from_round(league.get("round") or ""),
            "group": "",  # Will be filled later from team-group mapping when available.
            "date": date_part,
            "time_local": time_part,
            "team_a": home.get("name") or "",
            "team_b": away.get("name") or "",
            "venue": venue.get("name") or "",
            "city": venue.get("city") or "",
            "country": "",
            "status": _normalize_status(status.get("short"), status.get("long")),
            "score_a": score_a,
            "score_b": score_b,
            "winner": winner,
            "source_updated_at_utc": _now(),
            "api_round": league.get("round") or "",
        })

    columns = [
        "match_id", "stage", "group", "date", "time_local", "team_a", "team_b",
        "venue", "city", "country", "status", "score_a", "score_b", "winner",
        "source_updated_at_utc", "api_round",
    ]
    df = pd.DataFrame(rows)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns]


def fetch_standings_as_teams(league_id: int = DEFAULT_LEAGUE_ID, season: int = DEFAULT_SEASON) -> pd.DataFrame:
    """Fetch standings and convert team/group records to teams_current-compatible schema.

    This becomes useful once API-Football exposes World Cup 2026 groups/standings.
    If standings are not available yet, the returned DataFrame will be empty.
    """
    data = _get("standings", params={"league": league_id, "season": season})
    rows: list[dict[str, Any]] = []

    for comp in data.get("response", []) or []:
        league = comp.get("league") or {}
        standings = league.get("standings") or []
        for table in standings:
            for record in table:
                team = record.get("team") or {}
                all_stats = record.get("all") or {}
                goals = all_stats.get("goals") or {}
                rows.append({
                    "team": team.get("name") or "",
                    "group": record.get("group") or "",
                    "confederation": "",
                    "is_host": 1 if (team.get("name") or "") in {"Mexico", "Canada", "United States"} else 0,
                    "recent_form": record.get("form") or "",
                    "played": all_stats.get("played"),
                    "wins": all_stats.get("win"),
                    "draws": all_stats.get("draw"),
                    "losses": all_stats.get("lose"),
                    "goals_for": goals.get("for"),
                    "goals_against": goals.get("against"),
                    "points": record.get("points"),
                    "goals_diff": record.get("goalsDiff"),
                    "source_updated_at_utc": _now(),
                })

    return pd.DataFrame(rows)


def fetch_teams_from_fixtures(league_id: int = DEFAULT_LEAGUE_ID, season: int = DEFAULT_SEASON) -> pd.DataFrame:
    """Derive a team list from fixtures if standings are not available."""
    fixtures = fetch_fixtures(league_id=league_id, season=season)
    if fixtures.empty:
        return pd.DataFrame()

    teams = sorted(set(fixtures["team_a"].dropna()) | set(fixtures["team_b"].dropna()))
    rows = []
    for team in teams:
        if not team:
            continue
        rows.append({
            "team": team,
            "group": "",
            "confederation": "",
            "is_host": 1 if team in {"Mexico", "Canada", "United States"} else 0,
            "source_updated_at_utc": _now(),
        })
    return pd.DataFrame(rows)
