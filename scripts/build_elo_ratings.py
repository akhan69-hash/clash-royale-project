"""
Computes a real Elo rating per player from the 30-day raw match sample -- the
"Elo Rating System" roadmap item.

Elo is inherently sequential (each match's rating update depends on the
players' ratings going into it), so this does one pass over all matches in
chronological order with a plain Python dict -- not vectorizable, but a single
pass over ~18M rows is a one-time offline cost in the same ballpark as the
other pipeline scripts.

IMPORTANT finding from building this -- the original plan was to compare Elo
against raw trophies ("does Elo predict winners better than trophies?"), but
the "trophies" field in this dataset is NOT usable for that:
  - Verified gamemode 72000323 (Ranked1v1/Path of Legends): ~100% of rows show
    exactly 0 or 30, i.e. the match's medal *reward*, not a pre-match value.
  - Verified gamemode 72000006 (classic Ladder), which looked plausible at
    first (realistic 8000-9000 range, slowly varying) -- but checking whether
    the higher-trophy side actually won shows 99.6% agreement, and the trophy
    *gap* between the two sides matches a single match's known swing size
    (mean ~54, max 159), not the spread you'd see between two independently
    matchmade players. That means this field is ALSO post-match, for both
    gamemodes, contradicting the dataset's own documented "before starting the
    game" description.
So there's no legitimate pre-match trophy signal anywhere in this dataset to
benchmark Elo against -- a "trophy accuracy" number would just be measuring
how deterministically post-match trophies encode who already won, not a real
prediction. This script reports Elo's own predictive accuracy on held-out
matches instead, which is a fair, standalone measure of whether the Elo
ratings are picking up a real skill signal (answer: yes, ~57%, in the same
range as the deck-only win predictor -- see win_predictor_meta.json).

Output:
- data/models/elo_eval_metrics.json -- Elo's own held-out accuracy + the data
  limitation above (methodology_note), so the app can display it honestly.
- data/models/elo_sample.csv -- players with >=20 matches in the window
  (tag, final_elo, last observed *post-match* trophies, matches played), for
  a descriptive correlation plot -- not every player: millions of one-off
  tags would bloat the repo for no analytical benefit.

Usage: python scripts/build_elo_ratings.py
"""
import csv
import json
from datetime import datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw_matches"
MODELS_DIR = ROOT / "data" / "models"
OUT_METRICS = MODELS_DIR / "elo_eval_metrics.json"
OUT_SAMPLE = MODELS_DIR / "elo_sample.csv"

KEPT_GAMEMODES = (72000323, 72000006)
LADDER_GAMEMODE = 72000006  # the only mode with genuine pre-match trophy values -- see module docstring
TEST_DAYS = {"20231105", "20231106"}  # last 2 days held out for evaluation

K_FACTOR = 32
INITIAL_ELO = 1200
SAMPLE_SIZE = 5000  # top-N most-active players kept in elo_sample.csv

RAW_COLUMNS = [
    "datetime", "gamemode",
    "p1_tag", "p1_trophies", "p1_crowns",
    *[f"p1_c{i}" for i in range(1, 9)],
    "p2_tag", "p2_trophies", "p2_crowns",
    *[f"p2_c{i}" for i in range(1, 9)],
]


def main():
    con = duckdb.connect()
    raw = con.read_csv(str(RAW_DIR / "*.csv"), header=False, names=RAW_COLUMNS, ignore_errors=True)
    con.register("raw", raw)

    gamemode_list = ",".join(str(g) for g in KEPT_GAMEMODES)
    print("Querying matches sorted by time (this scans all 30 raw files)...")
    df = con.execute(f"""
        SELECT datetime, substr(datetime, 1, 8) AS day, gamemode,
               p1_tag, p1_trophies, p2_tag, p2_trophies,
               CASE WHEN p1_crowns > p2_crowns THEN 1 ELSE 0 END AS p1_won
        FROM raw
        WHERE gamemode IN ({gamemode_list}) AND p1_crowns <> p2_crowns
        ORDER BY datetime
    """).fetchdf()
    print(f"{len(df):,} matches, {df['day'].nunique()} days")

    elo: dict[str, float] = {}
    matches_played: dict[str, int] = {}
    last_trophies: dict[str, int] = {}

    elo_correct = 0
    n_eval = 0

    is_test_col = df["day"].isin(TEST_DAYS).to_numpy()
    is_ladder_col = (df["gamemode"] == LADDER_GAMEMODE).to_numpy()
    p1_tags = df["p1_tag"].to_numpy()
    p2_tags = df["p2_tag"].to_numpy()
    p1_trophies = df["p1_trophies"].to_numpy()
    p2_trophies = df["p2_trophies"].to_numpy()
    p1_won = df["p1_won"].to_numpy()

    for i in range(len(df)):
        t1, t2 = p1_tags[i], p2_tags[i]
        r1 = elo.get(t1, INITIAL_ELO)
        r2 = elo.get(t2, INITIAL_ELO)
        won = p1_won[i]

        if is_test_col[i]:
            n_eval += 1
            elo_pred_p1 = r1 > r2
            if elo_pred_p1 == bool(won):
                elo_correct += 1

        expected_1 = 1.0 / (1.0 + 10 ** ((r2 - r1) / 400.0))
        delta = K_FACTOR * (won - expected_1)
        elo[t1] = r1 + delta
        elo[t2] = r2 - delta
        matches_played[t1] = matches_played.get(t1, 0) + 1
        matches_played[t2] = matches_played.get(t2, 0) + 1
        if is_ladder_col[i]:
            # Only Ladder even loosely resembles a usable trophy value for
            # descriptive purposes -- Ranked1v1's is a meaningless 0/30 flag.
            # These are still post-match (see docstring), kept for a
            # descriptive scatter only, not any kind of prediction claim.
            last_trophies[t1] = int(p1_trophies[i])
            last_trophies[t2] = int(p2_trophies[i])

    elo_accuracy = elo_correct / n_eval
    print(f"Held-out matches (both gamemodes): {n_eval:,}")
    print(f"Elo standalone accuracy: {elo_accuracy:.4f} (baseline coin flip: 0.5000)")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Only players with a (Ladder-mode) trophy observation, for the descriptive
    # scatter -- these are post-match values (see docstring), not a skill
    # baseline, so they're labeled "last_observed_trophies" rather than
    # anything implying a prediction comparison.
    sample_rows = [
        {
            "player_tag": tag,
            "final_elo": round(rating, 1),
            "last_observed_trophies": last_trophies[tag],
            "matches_played": matches_played[tag],
        }
        for tag, rating in elo.items()
        if matches_played[tag] >= 20 and tag in last_trophies
    ]
    # Cap to a predictable, small size (top N most-active) rather than every
    # qualifying player -- keeps the committed file small regardless of how
    # large the raw sample is, same convention as deck_archetypes.csv.
    sample_rows.sort(key=lambda r: -r["matches_played"])
    sample_rows = sample_rows[:SAMPLE_SIZE]
    with open(OUT_SAMPLE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["player_tag", "final_elo", "last_observed_trophies", "matches_played"])
        writer.writeheader()
        writer.writerows(sample_rows)
    print(f"Wrote {len(sample_rows)} players (top {SAMPLE_SIZE} by matches played, min 20) to {OUT_SAMPLE}")

    metrics = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_players_total": len(elo),
        "n_players_sampled": len(sample_rows),
        "n_matches_total": int(len(df)),
        "test_days": sorted(TEST_DAYS),
        "n_eval_matches": int(n_eval),
        "elo_accuracy": round(elo_accuracy, 4),
        "baseline_accuracy": 0.5,
        "k_factor": K_FACTOR,
        "initial_elo": INITIAL_ELO,
        "source": "s1m0n38/clash-royale-games (Kaggle)",
        "trophy_comparison_dropped_reason": (
            "Originally planned to compare Elo's predictive accuracy against raw trophies, but "
            "this dataset's 'trophies' field turned out to be POST-match for both kept gamemodes "
            "(contradicting its own 'before starting the game' documentation): Ranked1v1 shows "
            "exactly 0 or 30 (the match reward) in ~100% of rows, and classic Ladder's trophy "
            "difference agrees with the actual winner 99.6% of the time with a gap matching a "
            "single match's known swing size -- both are outcome leakage, not a real pre-match "
            "skill estimate. So there's no legitimate trophy baseline to compare against here; "
            "elo_accuracy above is Elo's own standalone predictive accuracy on held-out matches."
        ),
    }
    with open(OUT_METRICS, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(f"Wrote metrics to {OUT_METRICS}")


if __name__ == "__main__":
    main()
