"""Safe remote CSV ingestion helpers.

This project does not scrape hidden or undocumented endpoints by default. For
reliable production use, provide official/verified CSV URLs through environment
variables or Streamlit/GitHub secrets.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"


def env_or_secret(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        v = st.secrets.get(name)
        return str(v) if v else None
    except Exception:
        return None


def _is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def fetch_csv_from_url(url: str, *, output_name: str | None = None, timeout: int = 30) -> pd.DataFrame:
    if not _is_safe_url(url):
        raise ValueError(f"Unsafe or invalid URL: {url}")
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if output_name:
        (RAW_DIR / output_name).write_bytes(response.content)
    from io import BytesIO
    return pd.read_csv(BytesIO(response.content))


def load_remote_csv_from_env(env_name: str, *, output_name: str) -> pd.DataFrame | None:
    url = env_or_secret(env_name)
    if not url:
        return None
    return fetch_csv_from_url(url, output_name=output_name)
