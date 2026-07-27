"""
Downloads a sample of daily match CSVs from the s1m0n38/clash-royale-games Kaggle
dataset (481M matches, Sept 2022-Nov 2023, sourced from the official API) into
data/raw_matches/ (gitignored -- these are only intermediate inputs to
build_analytics_data.py, not something we keep or commit).

Pulls the last N days available in the dataset (closest to its Nov 2023 cutoff,
i.e. furthest past the March 2023 evolutions launch and Sept 2022 champions launch).

Requires a Kaggle API token at ~/.kaggle/kaggle.json (already configured).

Usage: python scripts/fetch_match_sample.py [--days 30]
"""
import argparse
import zipfile
from pathlib import Path

from kaggle.api.kaggle_api_extended import KaggleApi

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw_matches"

# The last available season folder in the dataset (Oct 2 - Nov 6, 2023).
SEASON_FOLDER = "20231002-20231106/20231002-20231106"
LAST_DAY = "20231106"  # download backwards from this date


def daterange_ending(end_str: str, n_days: int) -> list[str]:
    from datetime import datetime, timedelta
    end = datetime.strptime(end_str, "%Y%m%d")
    return [(end - timedelta(days=i)).strftime("%Y%m%d") for i in range(n_days - 1, -1, -1)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    api = KaggleApi()
    api.authenticate()

    days = daterange_ending(LAST_DAY, args.days)
    print(f"Fetching {len(days)} days: {days[0]} .. {days[-1]}")

    for day in days:
        csv_path = RAW_DIR / f"{day}.csv"
        if csv_path.exists():
            print(f"  {day}.csv already present, skipping")
            continue

        remote_path = f"{SEASON_FOLDER}/{day}.csv"
        print(f"  downloading {remote_path} ...")
        api.dataset_download_file(
            "s1m0n38/clash-royale-games",
            remote_path,
            path=str(RAW_DIR),
        )

        zip_path = RAW_DIR / f"{day}.csv.zip"
        if zip_path.exists():
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(RAW_DIR)
            zip_path.unlink()

    downloaded = sorted(RAW_DIR.glob("*.csv"))
    print(f"Done. {len(downloaded)} day-files in {RAW_DIR}")


if __name__ == "__main__":
    main()
