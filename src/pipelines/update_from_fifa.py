"""Run FIFA direct scraper, then rebuild processed data."""
from __future__ import annotations

import argparse
import subprocess
import sys

from src.data_sources.fifa_official_scraper import main as fifa_scraper_main


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rendered", action="store_true")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    code = fifa_scraper_main(
        ["--allow-partial"] * bool(args.allow_partial)
        + ["--rendered"] * bool(args.rendered)
    )
    if code != 0:
        return code

    subprocess.check_call([sys.executable, "-m", "src.pipelines.update_all"])
    subprocess.check_call([sys.executable, "-m", "src.pipelines.validate_data"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
