"""FIFA official page scraper for WC2026 schedule data.

This module is intentionally defensive:
- It does not bypass access controls.
- It uses a normal browser-like user agent.
- It stores raw HTML/text for audit.
- It refuses to silently invent missing fixtures.
- It can optionally use Playwright rendering for dynamic pages.

Primary target:
https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/match-schedule-fixtures-results-teams-stadiums
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
LOGS = DATA / "source_logs"

FIFA_SCHEDULE_URL = (
    "https://www.fifa.com/en/tournaments/mens/worldcup/"
    "canadamexicousa2026/articles/match-schedule-fixtures-results-teams-stadiums"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36 "
        "WC26-Intelligence-Lab/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

TEAM_ALIASES = {
    "USA": "United States",
    "United States of America": "United States",
    "USMNT": "United States",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde",
    "Korea Republic": "Korea Republic",
    "South Korea": "Korea Republic",
    "IR Iran": "Iran",
    "Congo DR": "DR Congo",
    "Türkiye": "Türkiye",
    "Turkey": "Türkiye",
    "Czech Republic": "Czechia",
}

STADIUM_CITY_MAP = {
    "Mexico City Stadium": ("Mexico City", "Mexico"),
    "Estadio Azteca": ("Mexico City", "Mexico"),
    "Estadio Guadalajara": ("Guadalajara", "Mexico"),
    "Guadalajara Stadium": ("Guadalajara", "Mexico"),
    "Estadio Monterrey": ("Monterrey", "Mexico"),
    "Monterrey Stadium": ("Monterrey", "Mexico"),
    "Toronto Stadium": ("Toronto", "Canada"),
    "BMO Field": ("Toronto", "Canada"),
    "BC Place Vancouver": ("Vancouver", "Canada"),
    "Vancouver Stadium": ("Vancouver", "Canada"),
    "Los Angeles Stadium": ("Los Angeles", "United States"),
    "SoFi Stadium": ("Los Angeles", "United States"),
    "Seattle Stadium": ("Seattle", "United States"),
    "San Francisco Bay Area Stadium": ("San Francisco Bay Area", "United States"),
    "San Francisco Bay Area": ("San Francisco Bay Area", "United States"),
    "Dallas Stadium": ("Dallas", "United States"),
    "AT&T Stadium": ("Dallas", "United States"),
    "Houston Stadium": ("Houston", "United States"),
    "Kansas City Stadium": ("Kansas City", "United States"),
    "Atlanta Stadium": ("Atlanta", "United States"),
    "Miami Stadium": ("Miami", "United States"),
    "Boston Stadium": ("Boston", "United States"),
    "Philadelphia Stadium": ("Philadelphia", "United States"),
    "New York New Jersey Stadium": ("New York/New Jersey", "United States"),
    "New York/New Jersey Stadium": ("New York/New Jersey", "United States"),
    "MetLife Stadium": ("New York/New Jersey", "United States"),
}


@dataclass
class ScrapeOutput:
    matches: pd.DataFrame
    teams: pd.DataFrame
    html_path: Path
    text_path: Path
    status: dict[str, Any]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_team(value: str | None) -> str:
    if value is None:
        return ""
    name = re.sub(r"\s+", " ", str(value)).strip()
    return TEAM_ALIASES.get(name, name)


def fetch_html_requests(url: str = FIFA_SCHEDULE_URL) -> str:
    response = requests.get(url, headers=HEADERS, timeout=45)
    response.raise_for_status()
    return response.text


def fetch_html_playwright(url: str = FIFA_SCHEDULE_URL) -> str:
    """Render FIFA page with Playwright. Requires `playwright install chromium`."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.goto(url, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(3000)
        html = page.content()
        browser.close()
        return html


def save_raw(html: str) -> tuple[Path, Path]:
    RAW.mkdir(parents=True, exist_ok=True)
    soup = BeautifulSoup(html, "html.parser")
    text = "\n".join(
        line.strip()
        for line in soup.get_text("\n").splitlines()
        if line.strip()
    )

    html_path = RAW / "fifa_schedule_page.html"
    text_path = RAW / "fifa_schedule_page_text.txt"
    html_path.write_text(html, encoding="utf-8")
    text_path.write_text(text, encoding="utf-8")
    return html_path, text_path


def iter_json_objects(obj: Any) -> Iterable[dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_json_objects(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_json_objects(item)


def extract_json_blobs(html: str) -> list[Any]:
    soup = BeautifulSoup(html, "html.parser")
    blobs: list[Any] = []

    for script in soup.find_all("script"):
        content = script.string or script.get_text() or ""
        content = content.strip()
        if not content:
            continue

        # Direct JSON scripts, including __NEXT_DATA__ and JSON-LD.
        if script.get("type") in {"application/json", "application/ld+json"} or script.get("id") == "__NEXT_DATA__":
            try:
                blobs.append(json.loads(content))
                continue
            except Exception:
                pass

        # Some Next/React pages embed escaped JSON chunks.
        # Keep this conservative: only try if it contains obvious schedule tokens.
        lowered = content.lower()
        if "mexico" in lowered and ("south africa" in lowered or "match" in lowered):
            # Try extracting balanced JSON-looking objects. This is best-effort.
            for match in re.finditer(r"\{.{100,50000}?\}", content, flags=re.DOTALL):
                candidate = match.group(0)
                if "Mexico" not in candidate and "mexico" not in candidate:
                    continue
                try:
                    blobs.append(json.loads(candidate))
                except Exception:
                    continue

    return blobs


def get_nested_string(obj: dict[str, Any], candidate_keys: list[str]) -> str:
    for key in candidate_keys:
        if key in obj and obj[key] not in (None, ""):
            value = obj[key]
            if isinstance(value, str):
                return value
            if isinstance(value, (int, float)):
                return str(value)
            if isinstance(value, dict):
                for subkey in ["name", "Name", "displayName", "DisplayName", "description"]:
                    if subkey in value and value[subkey]:
                        return str(value[subkey])
    return ""


def dict_to_match(obj: dict[str, Any]) -> dict[str, Any] | None:
    # Multiple possible naming conventions used by sports APIs / page state.
    home = (
        get_nested_string(obj, ["homeTeam", "HomeTeam", "home", "teamA", "TeamA", "contestantHome"])
        or get_nested_string(obj, ["homeTeamName", "HomeTeamName", "homeTeamShortName"])
    )
    away = (
        get_nested_string(obj, ["awayTeam", "AwayTeam", "away", "teamB", "TeamB", "contestantAway"])
        or get_nested_string(obj, ["awayTeamName", "AwayTeamName", "awayTeamShortName"])
    )

    # Some objects use competitors/participants arrays.
    if not home or not away:
        for arr_key in ["teams", "Teams", "competitors", "Competitors", "participants", "Participants"]:
            arr = obj.get(arr_key)
            if isinstance(arr, list) and len(arr) >= 2:
                names = []
                for item in arr[:2]:
                    if isinstance(item, dict):
                        names.append(get_nested_string(item, ["name", "Name", "displayName", "DisplayName", "teamName"]))
                    else:
                        names.append(str(item))
                if names[0] and names[1]:
                    home, away = names[0], names[1]
                    break

    home = canonical_team(home)
    away = canonical_team(away)

    if not home or not away or home == away:
        return None

    # Avoid non-match metadata objects.
    if len(home) > 60 or len(away) > 60:
        return None

    stage = get_nested_string(obj, ["stage", "Stage", "round", "Round", "phase", "Phase"]) or "Group Stage"
    group = get_nested_string(obj, ["group", "Group", "groupName", "GroupName"])

    date_raw = get_nested_string(obj, ["date", "Date", "utcDate", "UtcDate", "kickoff", "Kickoff", "startDate", "StartDate", "matchDate"])
    date, time_local = split_date_time(date_raw)

    venue = get_nested_string(obj, ["venue", "Venue", "stadium", "Stadium", "stadiumName", "StadiumName", "location", "Location"])
    city, country = city_country_from_venue(venue)

    score_a = get_nested_string(obj, ["score_a", "homeScore", "HomeScore", "homeGoals"])
    score_b = get_nested_string(obj, ["score_b", "awayScore", "AwayScore", "awayGoals"])

    status_raw = get_nested_string(obj, ["status", "Status", "matchStatus", "MatchStatus"]) or "scheduled"
    status = map_status(status_raw)

    match_id = get_nested_string(obj, ["match_id", "matchId", "MatchId", "matchNumber", "MatchNumber", "id", "Id"])

    return {
        "match_id": match_id,
        "stage": stage,
        "group": normalize_group(group),
        "date": date,
        "time_local": time_local,
        "team_a": home,
        "team_b": away,
        "venue": venue,
        "city": city,
        "country": country,
        "status": status,
        "score_a": score_a,
        "score_b": score_b,
        "winner": "",
        "source_updated_at_utc": now_utc(),
    }


def split_date_time(value: str) -> tuple[str, str]:
    if not value:
        return "", ""
    value = str(value).strip()

    # ISO date.
    iso = re.search(r"(20\d{2}-\d{2}-\d{2})", value)
    time = re.search(r"(\d{2}:\d{2})", value)
    if iso:
        return iso.group(1), time.group(1) if time else ""

    # e.g. 11 June 2026
    date_words = re.search(
        r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})",
        value,
        flags=re.I,
    )
    if date_words:
        from datetime import datetime
        dt = datetime.strptime(date_words.group(0), "%d %B %Y")
        return dt.date().isoformat(), time.group(1) if time else ""

    return "", time.group(1) if time else ""


def normalize_group(value: str) -> str:
    if not value:
        return ""
    m = re.search(r"Group\s+([A-L])", value, flags=re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b([A-L])\b", value.strip(), flags=re.I)
    return m.group(1).upper() if m else value.strip()


def map_status(value: str) -> str:
    v = str(value or "").lower()
    if any(x in v for x in ["finished", "full", "ft", "played"]):
        return "finished"
    if any(x in v for x in ["live", "in_play", "in play", "paused"]):
        return "live"
    if "postpon" in v or "suspend" in v:
        return "postponed"
    if "cancel" in v:
        return "cancelled"
    return "scheduled"


def city_country_from_venue(venue: str) -> tuple[str, str]:
    if not venue:
        return "", ""
    for key, val in STADIUM_CITY_MAP.items():
        if key.lower() in venue.lower():
            return val
    return "", ""


def parse_matches_from_json(html: str) -> pd.DataFrame:
    blobs = extract_json_blobs(html)
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "fifa_json_blob_count.txt").write_text(str(len(blobs)), encoding="utf-8")

    records: list[dict[str, Any]] = []
    seen = set()

    for blob in blobs:
        for obj in iter_json_objects(blob):
            rec = dict_to_match(obj)
            if not rec:
                continue
            key = (rec["team_a"], rec["team_b"], rec.get("date", ""), rec.get("group", ""))
            if key in seen:
                continue
            seen.add(key)
            records.append(rec)

    return pd.DataFrame(records)


def parse_matches_from_text(html: str) -> pd.DataFrame:
    """Best-effort parser for official page text.

    This catches lines like:
    Mexico v South Africa - Group A - Mexico City Stadium
    """
    soup = BeautifulSoup(html, "html.parser")
    text = "\n".join(
        line.strip()
        for line in soup.get_text("\n").splitlines()
        if line.strip()
    )

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    records: list[dict[str, Any]] = []
    current_date = ""

    date_pattern = re.compile(
        r"(?:(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?"
        r"(\d{1,2})\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(20\d{2})",
        flags=re.I,
    )

    # Broad enough for "v", "vs", "versus".
    fixture_pattern = re.compile(
        r"^(?P<a>[\w\s\.\'’\-\u00C0-\u024F]+?)\s+"
        r"(?:v|vs\.?|versus)\s+"
        r"(?P<b>[\w\s\.\'’\-\u00C0-\u024F]+?)"
        r"(?:\s+[-–]\s+Group\s+(?P<group>[A-L]))?"
        r"(?:\s+[-–]\s+(?P<venue>.+?))?$",
        flags=re.I,
    )

    for line in lines:
        date_match = date_pattern.search(line)
        if date_match:
            current_date, _ = split_date_time(date_match.group(0))

        m = fixture_pattern.search(line)
        if not m:
            continue

        team_a = canonical_team(m.group("a"))
        team_b = canonical_team(m.group("b"))

        if len(team_a) < 2 or len(team_b) < 2:
            continue
        if any(x.lower() in team_a.lower() for x in ["match schedule", "group stage"]):
            continue

        venue = (m.group("venue") or "").strip()
        city, country = city_country_from_venue(venue)

        records.append(
            {
                "match_id": "",
                "stage": "Group Stage",
                "group": normalize_group(m.group("group") or ""),
                "date": current_date,
                "time_local": "",
                "team_a": team_a,
                "team_b": team_b,
                "venue": venue,
                "city": city,
                "country": country,
                "status": "scheduled",
                "score_a": "",
                "score_b": "",
                "winner": "",
                "source_updated_at_utc": now_utc(),
            }
        )

    return pd.DataFrame(records)


def clean_matches(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "match_id",
        "stage",
        "group",
        "date",
        "time_local",
        "team_a",
        "team_b",
        "venue",
        "city",
        "country",
        "status",
        "score_a",
        "score_b",
        "winner",
        "source_updated_at_utc",
    ]

    if df is None or df.empty:
        return pd.DataFrame(columns=columns)

    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = ""

    out["team_a"] = out["team_a"].map(canonical_team)
    out["team_b"] = out["team_b"].map(canonical_team)
    out = out[(out["team_a"] != "") & (out["team_b"] != "") & (out["team_a"] != out["team_b"])].copy()

    out["group"] = out["group"].map(normalize_group)
    out["status"] = out["status"].map(map_status)

    # Deduplicate robustly.
    out["_key"] = (
        out["team_a"].astype(str)
        + "|"
        + out["team_b"].astype(str)
        + "|"
        + out["date"].astype(str)
        + "|"
        + out["group"].astype(str)
    )
    out = out.drop_duplicates("_key").drop(columns=["_key"])

    # Fill match_id where missing.
    out = out.reset_index(drop=True)
    if out["match_id"].astype(str).str.strip().eq("").any():
        out["match_id"] = range(1, len(out) + 1)

    return out[columns]


def teams_from_matches(matches: pd.DataFrame) -> pd.DataFrame:
    if matches.empty:
        return pd.DataFrame(columns=["team", "group", "confederation", "is_host", "notes"])

    rows: dict[str, dict[str, Any]] = {}
    for _, row in matches.iterrows():
        for side in ["team_a", "team_b"]:
            team = canonical_team(row.get(side, ""))
            if not team:
                continue
            group = row.get("group", "")
            rows.setdefault(
                team,
                {
                    "team": team,
                    "group": group,
                    "confederation": "",
                    "is_host": 1 if team in {"Mexico", "Canada", "United States"} else 0,
                    "notes": "Extracted from FIFA official schedule page scraper.",
                },
            )
            if group and not rows[team].get("group"):
                rows[team]["group"] = group

    return pd.DataFrame(rows.values()).sort_values(["group", "team"])


def scrape_fifa_schedule(render: bool = False, url: str = FIFA_SCHEDULE_URL) -> ScrapeOutput:
    html = fetch_html_playwright(url) if render else fetch_html_requests(url)
    html_path, text_path = save_raw(html)

    json_matches = clean_matches(parse_matches_from_json(html))
    text_matches = clean_matches(parse_matches_from_text(html))

    if len(json_matches) >= len(text_matches):
        matches = json_matches
        method = "json_or_embedded_state"
    else:
        matches = text_matches
        method = "html_text"

    teams = teams_from_matches(matches)

    status = {
        "scraped_at_utc": now_utc(),
        "url": url,
        "rendered": render,
        "html_path": str(html_path),
        "text_path": str(text_path),
        "method": method,
        "matches_found": int(len(matches)),
        "teams_found": int(len(teams)),
        "minimum_expected_group_matches": 72,
        "success": bool(len(matches) >= 72),
    }

    return ScrapeOutput(matches=matches, teams=teams, html_path=html_path, text_path=text_path, status=status)


def write_outputs(output: ScrapeOutput, allow_partial: bool = False) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    status_path = LOGS / "fifa_scrape_status.json"
    status_path.write_text(json.dumps(output.status, indent=2, ensure_ascii=False), encoding="utf-8")

    if len(output.matches) < 72 and not allow_partial:
        raise RuntimeError(
            "FIFA scraper did not extract enough group-stage matches. "
            f"Found {len(output.matches)}. Raw page saved at {output.html_path} and text at {output.text_path}. "
            "Inspect the raw text or run with --rendered. No official CSV was overwritten."
        )

    output.matches.to_csv(DATA / "matches_official.csv", index=False)
    output.teams.to_csv(DATA / "teams_official.csv", index=False)

    print(f"Wrote {len(output.matches)} matches to data/matches_official.csv")
    print(f"Wrote {len(output.teams)} teams to data/teams_official.csv")
    print(f"Scrape status: {status_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rendered", action="store_true", help="Use Playwright browser rendering.")
    parser.add_argument("--allow-partial", action="store_true", help="Write partial results even if fewer than 72 matches.")
    parser.add_argument("--url", default=FIFA_SCHEDULE_URL)
    args = parser.parse_args(argv)

    try:
        output = scrape_fifa_schedule(render=args.rendered, url=args.url)
        write_outputs(output, allow_partial=args.allow_partial)
        print(json.dumps(output.status, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        LOGS.mkdir(parents=True, exist_ok=True)
        failure = {
            "scraped_at_utc": now_utc(),
            "url": args.url,
            "rendered": args.rendered,
            "success": False,
            "error": str(exc),
        }
        (LOGS / "fifa_scrape_status.json").write_text(
            json.dumps(failure, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"FIFA scraper failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
