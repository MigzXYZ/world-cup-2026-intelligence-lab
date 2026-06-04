"""Fan voting persistence layer with Supabase support and safe local fallback."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st


def _get_secret(name: str) -> str | None:
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    return None


def supabase_client():
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def has_supabase() -> bool:
    return supabase_client() is not None


def submit_vote(vote: dict[str, Any]) -> tuple[bool, str]:
    payload = {
        "favorite_team": vote.get("favorite_team"),
        "surprise_team": vote.get("surprise_team"),
        "top_scorer": vote.get("top_scorer"),
        "group_of_death": vote.get("group_of_death"),
        "confidence": int(vote.get("confidence", 5)),
        "user_country": vote.get("user_country") or None,
        "display_name": vote.get("display_name") or None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    client = supabase_client()
    if client is not None:
        try:
            client.table("fan_votes").insert(payload).execute()
            return True, "Vote saved to Supabase."
        except Exception as exc:
            # Fallback to session so public app never crashes.
            st.session_state.setdefault("fan_votes_local", []).append(payload)
            return False, f"Supabase write failed; vote saved locally for this session. Error: {exc}"
    st.session_state.setdefault("fan_votes_local", []).append(payload)
    return True, "Vote saved locally for this browser session. Add Supabase secrets for persistent public votes."


def load_votes() -> pd.DataFrame:
    client = supabase_client()
    if client is not None:
        try:
            data = client.table("fan_votes").select("*").order("created_at", desc=True).limit(5000).execute().data
            return pd.DataFrame(data)
        except Exception:
            pass
    return pd.DataFrame(st.session_state.get("fan_votes_local", []))


def aggregate_votes(votes: pd.DataFrame) -> dict[str, pd.DataFrame | float | int]:
    if votes is None or votes.empty:
        return {"count": 0, "champions": pd.DataFrame(), "surprises": pd.DataFrame(), "avg_confidence": 0.0}
    champions = votes["favorite_team"].value_counts().rename_axis("team").reset_index(name="votes") if "favorite_team" in votes else pd.DataFrame()
    surprises = votes["surprise_team"].value_counts().rename_axis("team").reset_index(name="votes") if "surprise_team" in votes else pd.DataFrame()
    avg_conf = pd.to_numeric(votes.get("confidence", pd.Series(dtype=float)), errors="coerce").mean()
    return {"count": int(len(votes)), "champions": champions, "surprises": surprises, "avg_confidence": float(avg_conf) if pd.notna(avg_conf) else 0.0}
