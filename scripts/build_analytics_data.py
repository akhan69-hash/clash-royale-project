"""
Aggregates the raw match CSVs in data/raw_matches/ (see fetch_match_sample.py) into
small, committable analytics files the Streamlit app reads:

    data/card_stats.csv       -- per card: times used, win rate, presence rate
    data/card_synergy.csv     -- per card pair: co-occurrence count, win rate together
    data/deck_archetypes.csv  -- k-means clusters over the most common decks
    data/analytics_meta.json  -- data vintage (date range, match count, gamemodes kept)

Uses duckdb to aggregate directly over the ~6GB of raw CSVs without loading them
fully into pandas. Raw files are never committed (see .gitignore) -- only these
small aggregate outputs are.

Card names come from data/card_reference.csv (utils.data_loader.get_card_match_id_map).
Any card id present in the raw data but absent from that reference (a card outside
our current 115-card set, e.g. renamed/removed since this match data was recorded)
is simply dropped from the aggregates -- it has no stats-CSV counterpart to join to.

Usage: python scripts/build_analytics_data.py
"""
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.data_loader import get_card_match_id_map, get_elixir_costs

ROOT = Path(__file__).parent.parent
RAW_GLOB = str(ROOT / "data" / "raw_matches" / "*.csv")
OUT_CARD_STATS = ROOT / "data" / "card_stats.csv"
OUT_SYNERGY = ROOT / "data" / "card_synergy.csv"
OUT_ARCHETYPES = ROOT / "data" / "deck_archetypes.csv"
OUT_META = ROOT / "data" / "analytics_meta.json"

# Standard 1v1 modes only -- excludes CrownRush variants (different win condition),
# Challenge/EventDeck, Friendly, and Tournament, which would skew win rate/synergy.
# See gamemode distribution printed below for the full picture.
KEPT_GAMEMODES = (72000323, 72000006)  # Ranked1v1 (tournament-standard levels), Ladder

TOP_N_DECKS = 5000  # unique decks kept for synergy + clustering, ranked by frequency

RAW_COLUMNS = [
    "datetime", "gamemode",
    "p1_tag", "p1_trophies", "p1_crowns",
    *[f"p1_c{i}" for i in range(1, 9)],
    "p2_tag", "p2_trophies", "p2_crowns",
    *[f"p2_c{i}" for i in range(1, 9)],
]


def main():
    name_to_id, id_to_name = get_card_match_id_map()
    elixir_costs = get_elixir_costs()
    print(f"{len(name_to_id)} cards have a match_id and are usable for match-data analytics")

    con = duckdb.connect()
    raw = con.read_csv(RAW_GLOB, header=False, names=RAW_COLUMNS, ignore_errors=True)
    con.register("raw", raw)

    print("\nGamemode distribution across the sample:")
    dist = con.execute("SELECT gamemode, count(*) c FROM raw GROUP BY gamemode ORDER BY c DESC").fetchall()
    for gm, c in dist:
        print(f"  {gm}: {c:,}{'  <- kept' if gm in KEPT_GAMEMODES else ''}")

    gamemode_list = ",".join(str(g) for g in KEPT_GAMEMODES)

    # Both perspectives of each match, draws dropped, restricted to kept gamemodes.
    con.execute(f"""
        CREATE TEMP TABLE match_decks AS
        SELECT p1_c1 c1, p1_c2 c2, p1_c3 c3, p1_c4 c4, p1_c5 c5, p1_c6 c6, p1_c7 c7, p1_c8 c8,
               CASE WHEN p1_crowns > p2_crowns THEN 1 ELSE 0 END AS win
        FROM raw
        WHERE gamemode IN ({gamemode_list}) AND p1_crowns <> p2_crowns
        UNION ALL
        SELECT p2_c1, p2_c2, p2_c3, p2_c4, p2_c5, p2_c6, p2_c7, p2_c8,
               CASE WHEN p2_crowns > p1_crowns THEN 1 ELSE 0 END AS win
        FROM raw
        WHERE gamemode IN ({gamemode_list}) AND p1_crowns <> p2_crowns
    """)
    total_sides = con.execute("SELECT count(*) FROM match_decks").fetchone()[0]
    print(f"\n{total_sides:,} match-sides after gamemode/draw filtering")

    # ---- card_stats: per-card usage + win rate -----------------------------------
    unpivot_union = " UNION ALL ".join(
        f"SELECT c{i} AS card_id, win FROM match_decks" for i in range(1, 9)
    )
    card_stats_raw = con.execute(f"""
        SELECT card_id, count(*) AS times_used, sum(win) AS wins
        FROM ({unpivot_union})
        GROUP BY card_id
    """).fetchdf()

    card_stats_raw["card_name"] = card_stats_raw["card_id"].map(id_to_name)
    card_stats = card_stats_raw.dropna(subset=["card_name"]).copy()
    card_stats["win_rate"] = (card_stats["wins"] / card_stats["times_used"]).round(4)
    card_stats["presence_rate"] = (card_stats["times_used"] / total_sides).round(5)
    card_stats["elixir"] = card_stats["card_name"].map(elixir_costs)
    card_stats = card_stats[["card_name", "times_used", "wins", "win_rate", "presence_rate", "elixir"]]
    card_stats = card_stats.sort_values("times_used", ascending=False)
    card_stats.to_csv(OUT_CARD_STATS, index=False)
    print(f"\nWrote {len(card_stats)} cards to {OUT_CARD_STATS}")

    # ---- unique decks (top N by frequency), only decks where all 8 cards map ------
    known_ids = "(" + ",".join(str(i) for i in id_to_name) + ")"
    unique_decks = con.execute(f"""
        SELECT c1, c2, c3, c4, c5, c6, c7, c8, count(*) AS freq, avg(win) AS win_rate
        FROM match_decks
        WHERE c1 IN {known_ids} AND c2 IN {known_ids} AND c3 IN {known_ids} AND c4 IN {known_ids}
          AND c5 IN {known_ids} AND c6 IN {known_ids} AND c7 IN {known_ids} AND c8 IN {known_ids}
        GROUP BY c1, c2, c3, c4, c5, c6, c7, c8
        ORDER BY freq DESC
        LIMIT {TOP_N_DECKS}
    """).fetchdf()
    print(f"{len(unique_decks)} unique decks kept (top {TOP_N_DECKS} by frequency)")

    card_cols = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"]
    unique_decks["cards"] = unique_decks[card_cols].apply(
        lambda row: sorted(id_to_name[cid] for cid in row), axis=1
    )

    # ---- card_synergy: expand each kept deck into its 28 pairs, weight by freq ----
    pair_freq = {}
    pair_wins = {}
    for _, row in unique_decks.iterrows():
        freq, win_rate, cards = row["freq"], row["win_rate"], row["cards"]
        for a, b in itertools.combinations(cards, 2):
            key = (a, b) if a < b else (b, a)
            pair_freq[key] = pair_freq.get(key, 0) + freq
            pair_wins[key] = pair_wins.get(key, 0) + freq * win_rate

    synergy_rows = [
        {"card_a": a, "card_b": b, "co_occurrence": freq, "win_rate_together": round(pair_wins[(a, b)] / freq, 4)}
        for (a, b), freq in pair_freq.items()
    ]
    synergy_df = pd.DataFrame(synergy_rows).sort_values("co_occurrence", ascending=False)
    synergy_df.to_csv(OUT_SYNERGY, index=False)
    print(f"Wrote {len(synergy_df)} card pairs to {OUT_SYNERGY}")

    # ---- deck_archetypes: k-means over one-hot deck vectors -----------------------
    all_card_names = sorted(name_to_id.keys())
    onehot = np.zeros((len(unique_decks), len(all_card_names)), dtype=int)
    name_index = {name: i for i, name in enumerate(all_card_names)}
    for row_i, cards in enumerate(unique_decks["cards"]):
        for c in cards:
            onehot[row_i, name_index[c]] = 1

    weights = unique_decks["freq"].to_numpy()

    best_k, best_score, best_labels = None, -1, None
    for k in range(6, 15):
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = km.fit_predict(onehot, sample_weight=weights)
        if len(set(labels)) < 2:
            continue
        sample_n = min(3000, len(onehot))
        idx = np.random.RandomState(42).choice(len(onehot), sample_n, replace=False)
        score = silhouette_score(onehot[idx], labels[idx])
        print(f"  k={k}: silhouette={score:.3f}")
        if score > best_score:
            best_k, best_score, best_labels = k, score, labels

    print(f"Chose k={best_k} (silhouette={best_score:.3f})")
    unique_decks["cluster"] = best_labels

    archetype_rows = []
    for cluster_id in sorted(set(best_labels)):
        mask = unique_decks["cluster"] == cluster_id
        cluster_decks = unique_decks[mask]
        cluster_weight = cluster_decks["freq"].sum()
        cluster_win_rate = np.average(cluster_decks["win_rate"], weights=cluster_decks["freq"])

        card_presence = {}
        for _, row in cluster_decks.iterrows():
            for c in row["cards"]:
                card_presence[c] = card_presence.get(c, 0) + row["freq"]
        top_cards = sorted(card_presence.items(), key=lambda x: -x[1])[:8]
        top_card_names = [c for c, _ in top_cards]
        avg_elixir = round(np.mean([elixir_costs.get(c, 0) for c in top_card_names]), 2)

        # Pick the real deck in this cluster most similar to the representative
        # cards (highest overlap, tie-broken by frequency) -- a raw top-frequency
        # pick can land on an outlier deck that shares little with the archetype.
        top_card_set = set(top_card_names)
        cluster_decks = cluster_decks.copy()
        cluster_decks["overlap"] = cluster_decks["cards"].apply(lambda cards: len(top_card_set & set(cards)))
        example_deck = cluster_decks.sort_values(["overlap", "freq"], ascending=False).iloc[0]["cards"]

        archetype_rows.append({
            "cluster": cluster_id,
            "deck_count": int(mask.sum()),
            "total_frequency": int(cluster_weight),
            "win_rate": round(cluster_win_rate, 4),
            "avg_elixir": avg_elixir,
            "representative_cards": ";".join(top_card_names),
            "example_deck": ";".join(example_deck),
        })

    archetypes_df = pd.DataFrame(archetype_rows).sort_values("total_frequency", ascending=False)
    archetypes_df.to_csv(OUT_ARCHETYPES, index=False)
    print(f"Wrote {len(archetypes_df)} archetypes to {OUT_ARCHETYPES}")

    # ---- metadata (data vintage) ---------------------------------------------------
    date_min, date_max = con.execute("SELECT min(datetime), max(datetime) FROM raw").fetchone()
    meta = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "date_range_start": date_min,
        "date_range_end": date_max,
        "total_matches_sampled": int(total_sides // 2),
        "gamemodes_kept": list(KEPT_GAMEMODES),
        "source": "s1m0n38/clash-royale-games (Kaggle)",
    }
    with open(OUT_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"\nData vintage: {date_min} to {date_max}, {meta['total_matches_sampled']:,} matches")


if __name__ == "__main__":
    main()
