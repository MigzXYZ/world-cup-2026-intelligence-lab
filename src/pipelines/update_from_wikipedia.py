"""Parse Wikipedia WC2026 tables, then rebuild processed data."""
from __future__ import annotations

import argparse
import subprocess
import sys

from src.data_sources.wikipedia_wc2026_parser import main as wiki_main


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-cache", action="store_true")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    wiki_args = []
    if args.from_cache:
        wiki_args.append("--from-cache")
    if args.allow_partial:
        wiki_args.append("--allow-partial")
    code = wiki_main(wiki_args)
    if code != 0:
        return code
    subprocess.check_call([sys.executable, "-m", "src.pipelines.update_all"])
    subprocess.check_call([sys.executable, "-m", "src.pipelines.validate_data"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
