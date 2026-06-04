"""Wikipedia WC2026 parser for official public schedule mirrors.

This parser is designed for the current 2026 FIFA World Cup Wikipedia page structure:
- A standings table for each group.
- Six match tables immediately after each group standings table.

It produces:
- data/matches_official.csv
- data/teams_official.csv

Important:
Wikipedia is not FIFA. Treat this as a public schedule mirror to be verified against FIFA.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
LOGS = DATA / "source_logs"

DEFAULT_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup"
GROUPS = list("ABCDEFGHIJKL")
HEADERS = {
    "User-Agent": "Mozilla/5.0 WC26-Intelligence-Lab/1.0 (educational data project)",
    "Accept-Language": "en-US,en;q=0.9",
}

TEAM_ALIASES = {
    "South Korea": "Korea Republic",
    "Korea Republic": "Korea Republic",
    "Czech Republic": "Czechia",
    "Czechia": "Czechia",
    "Turkey": "Türkiye",
    "Türkiye": "Türkiye",
    "Curaçao": "Curaçao",
    "CuraÃ§ao": "Curaçao",
    "DR Congo": "DR Congo",
    "Congo DR": "DR Congo",
    "United States": "United States",
    "USA": "United States",
    "Ivory Coast": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Cape Verde": "Cape Verde",
    "Cabo Verde": "Cape Verde",
}

CONFEDERATIONS = {
    "Australia": "AFC", "Iran": "AFC", "Iraq": "AFC", "Japan": "AFC", "Jordan": "AFC", "Qatar": "AFC", "Saudi Arabia": "AFC", "Korea Republic": "AFC", "Uzbekistan": "AFC",
    "Algeria": "CAF", "Cape Verde": "CAF", "DR Congo": "CAF", "Egypt": "CAF", "Ghana": "CAF", "Ivory Coast": "CAF", "Morocco": "CAF", "Senegal": "CAF", "South Africa": "CAF", "Tunisia": "CAF",
    "Canada": "CONCACAF", "Curaçao": "CONCACAF", "Haiti": "CONCACAF", "Mexico": "CONCACAF", "Panama": "CONCACAF", "United States": "CONCACAF",
    "Argentina": "CONMEBOL", "Brazil": "CONMEBOL", "Colombia": "CONMEBOL", "Ecuador": "CONMEBOL", "Paraguay": "CONMEBOL", "Uruguay": "CONMEBOL",
    "New Zealand": "OFC",
    "Austria": "UEFA", "Belgium": "UEFA", "Bosnia and Herzegovina": "UEFA", "Croatia": "UEFA", "Czechia": "UEFA", "England": "UEFA", "France": "UEFA", "Germany": "UEFA", "Netherlands": "UEFA", "Norway": "UEFA", "Portugal": "UEFA", "Scotland": "UEFA", "Serbia": "UEFA", "Spain": "UEFA", "Sweden": "UEFA", "Switzerland": "UEFA", "Türkiye": "UEFA",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value)
    replacements = {"\xa0": " ", "â€“": "-", "â€”": "-", "Â": "", "Ã§": "ç", "Ã©": "é", "Ã¼": "ü", "Ã­": "í", "Ã£": "ã", "Ã´": "ô"}
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    text = re.sub(r"\[[^\]]+\]", "", text)
    text = text.replace("(H)", "").replace("(co-host)", "").replace("(debut)", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def canonical_team(value: Any) -> str:
    text = clean_text(value)
    text = re.sub(r"\s*\(\d+\)\s*$", "", text).strip()
    return TEAM_ALIASES.get(text, text)


def flatten_columns(df: pd.DataFrame) -> list[str]:
    cols = []
    for col in df.columns:
        if isinstance(col, tuple):
            cols.append(" ".join(clean_text(x) for x in col if clean_text(x)))
        else:
            cols.append(clean_text(col))
    return cols


def fetch_tables(url: str = DEFAULT_URL) -> list[pd.DataFrame]:
    response = requests.get(url, headers=HEADERS, timeout=45)
    response.raise_for_status()
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "wikipedia_wc2026_page.html").write_text(response.text, encoding="utf-8")
    tables = pd.read_html(StringIO(response.text))
    for i, table in enumerate(tables):
        table.to_csv(RAW / f"wiki_table_{i}.csv", index=False, encoding="utf-8-sig")
    return tables


def load_cached_tables() -> list[pd.DataFrame]:
    folder = RAW / "wiki_tables"
    if not folder.exists():
        folder = RAW
    files = sorted(folder.glob("table_*.csv")) or sorted(folder.glob("wiki_table_*.csv"))
    def key(path: Path) -> int:
        m = re.search(r"(\d+)", path.stem)
        return int(m.group(1)) if m else 9999
    files = sorted(files, key=key)
    if not files:
        raise FileNotFoundError("No cached Wikipedia tables found. Run without --from-cache first.")
    return [pd.read_csv(p) for p in files]


def is_group_standings_table(df: pd.DataFrame) -> bool:
    cols = [c.lower() for c in flatten_columns(df)]
    return len(df) == 4 and any(c.startswith("pos") or c == "pos" for c in cols) and any("team" in c for c in cols) and any("pld" in c for c in cols) and any("pts" in c for c in cols)


def extract_group_teams(df: pd.DataFrame) -> list[str]:
    cols = flatten_columns(df)
    tmp = df.copy()
    tmp.columns = cols
    team_col = next((c for c in cols if "team" in c.lower()), cols[1] if len(cols) > 1 else cols[0])
    teams = []
    for value in tmp[team_col].tolist():
        team = canonical_team(value)
        if team and team.lower() not in {"team", "teamvte"}:
            teams.append(team)
    return teams[:4]


def is_match_table(df: pd.DataFrame) -> bool:
    if df.shape[1] < 3 or df.empty:
        return False
    text = " ".join(flatten_columns(df)) + " " + df.astype(str).to_string()
    return bool(re.search(r"\bMatch\s+\d+\b", text, flags=re.I))


def extract_match(df: pd.DataFrame) -> dict[str, Any] | None:
    cols = flatten_columns(df)
    all_values = cols[:]
    if not df.empty:
        all_values.extend([clean_text(x) for x in df.iloc[0].tolist()])
    match_id = ""
    for value in all_values:
        m = re.search(r"\bMatch\s+(\d+)\b", clean_text(value), flags=re.I)
        if m:
            match_id = m.group(1)
            break
    if not match_id or len(cols) < 3:
        return None
    team_a = canonical_team(cols[0])
    team_b = canonical_team(cols[2])
    if not team_a or team_a.isdigit() or team_a.lower().startswith("unnamed"):
        team_a = canonical_team(df.iloc[0, 0])
    if not team_b or team_b.isdigit() or team_b.lower().startswith("unnamed"):
        team_b = canonical_team(df.iloc[0, 2])
    if not team_a or not team_b or team_a == team_b:
        return None
    return {"match_id": int(match_id), "stage": "Group Stage", "group": "", "date": "", "time_local": "", "team_a": team_a, "team_b": team_b, "venue": "", "city": "", "country": "", "status": "scheduled", "score_a": "", "score_b": "", "winner": "", "source_updated_at_utc": now_utc()}


def parse_group_stage(tables: list[pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    matches, teams_rows = [], []
    group_index, i = 0, 0
    diagnostics = {"groups_found": [], "standings_table_indexes": [], "match_table_indexes": [], "warnings": []}
    while i < len(tables) and group_index < len(GROUPS):
        df = tables[i]
        if not is_group_standings_table(df):
            i += 1
            continue
        group = GROUPS[group_index]
        group_teams = extract_group_teams(df)
        diagnostics["standings_table_indexes"].append(i)
        if len(group_teams) != 4:
            diagnostics["warnings"].append(f"Group {group}: expected 4 teams, found {len(group_teams)} at table {i}")
        for team in group_teams:
            teams_rows.append({"team": team, "group": group, "confederation": CONFEDERATIONS.get(team, ""), "is_host": 1 if team in {"Mexico", "Canada", "United States"} else 0, "notes": "Parsed from Wikipedia public schedule mirror; verify against FIFA official source."})
        j, group_matches = i + 1, []
        while j < len(tables) and len(group_matches) < 6:
            if is_match_table(tables[j]):
                rec = extract_match(tables[j])
                if rec:
                    rec["group"] = group
                    group_matches.append(rec)
                    diagnostics["match_table_indexes"].append(j)
            elif is_group_standings_table(tables[j]) and group_matches:
                break
            j += 1
        if len(group_matches) != 6:
            diagnostics["warnings"].append(f"Group {group}: expected 6 matches, found {len(group_matches)} after table {i}")
        matches.extend(group_matches)
        diagnostics["groups_found"].append(group)
        group_index += 1
        i = j
    matches_df = pd.DataFrame(matches)
    teams_df = pd.DataFrame(teams_rows)
    if not matches_df.empty:
        matches_df = matches_df.sort_values("match_id").drop_duplicates("match_id", keep="first").reset_index(drop=True)
    if not teams_df.empty:
        teams_df = teams_df.drop_duplicates("team", keep="first").sort_values(["group", "team"]).reset_index(drop=True)
    diagnostics["matches_found"] = int(len(matches_df))
    diagnostics["teams_found"] = int(len(teams_df))
    diagnostics["success"] = bool(len(matches_df) >= 72 and len(teams_df) >= 48)
    return matches_df, teams_df, diagnostics


def write_outputs(matches: pd.DataFrame, teams: pd.DataFrame, diagnostics: dict[str, Any], allow_partial: bool = False) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    status = {"scraped_at_utc": now_utc(), "source": DEFAULT_URL, **diagnostics}
    (LOGS / "wikipedia_scrape_status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    if not allow_partial and (len(matches) < 72 or len(teams) < 48):
        raise RuntimeError(f"Wikipedia parser extracted insufficient data: {len(matches)} matches, {len(teams)} teams. No official files were overwritten. Inspect data/source_logs/wikipedia_scrape_status.json and data/raw/wiki_table_*.csv.")
    matches.to_csv(DATA / "matches_official.csv", index=False, encoding="utf-8")
    teams.to_csv(DATA / "teams_official.csv", index=False, encoding="utf-8")
    print(f"Wrote {len(matches)} matches to data/matches_official.csv")
    print(f"Wrote {len(teams)} teams to data/teams_official.csv")
    print(json.dumps(status, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-cache", action="store_true", help="Read previously saved data/raw/wiki_tables/*.csv or data/raw/wiki_table_*.csv")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args(argv)
    try:
        tables = load_cached_tables() if args.from_cache else fetch_tables(args.url)
        matches, teams, diagnostics = parse_group_stage(tables)
        write_outputs(matches, teams, diagnostics, allow_partial=args.allow_partial)
        return 0
    except Exception as exc:
        LOGS.mkdir(parents=True, exist_ok=True)
        status = {"scraped_at_utc": now_utc(), "source": args.url, "success": False, "error": str(exc)}
        (LOGS / "wikipedia_scrape_status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wikipedia parser failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
