"""
Recomputes card win-rate/presence stats from the live-collected dataset
(data/collected_battles.csv, built by scripts/crawl_battles.py and every
Player Lookup page visit), and -- once there's enough of it to be meaningful
-- retrains a small supplementary win-predictor model on it.

Deliberately threshold-gated and honest about scale: the historical Kaggle
base has 18.3M matches. A few hundred or even a few thousand crawled battles
cannot retrain that model meaningfully -- doing so would just be overfitting
noise and calling it "training." Instead:
  - Below MIN_BATTLES_FOR_CARD_STATS: just reports current dataset size.
  - Above that: writes data/card_stats_live.csv (kept SEPARATE from
    data/card_stats.csv, which stays the well-validated 18.3M-match result --
    this is a live/fresh supplementary view, not a silent overwrite).
  - Above MIN_BATTLES_FOR_MODEL (much higher, since a classifier needs far
    more signal than a simple win-rate count): trains data/models/
    win_predictor_live.joblib the same way scripts/train_win_predictor.py
    does, but reports accuracy with an explicit small-sample caveat.

Run this any time after scripts/crawl_battles.py to refresh the live view.

VECTORIZED REWRITE (2026-08-28): every build_* function below used to loop
over the full DataFrame with `for _, row in df.iterrows(): ...` -- one of
the slowest, heaviest patterns in pandas -- and there were ~10 such passes
per run. Running that battery over the ENTIRE collected_battles.csv
(unbounded, grows forever via the always-on crawler, 4.3M+ rows at the time
of the incident) meant every retrain got more expensive than the last, until
one retrain's peak memory was enough to exhaust the VM's RAM+swap at the
same time and wedge it (SSH included) for 2 days straight -- see
auto_crawler.py's RETRAIN_INTERVAL_SECONDS docstring for the frequency half
of that incident's fix. A same-day mitigation capped this file to a rolling
120-day window to keep it safe in the meantime, but that meant ML
training/analytics stopped seeing anything older than that -- not
acceptable long-term (real historical volume matters for model quality).
This rewrite removes the need for that cap entirely: every full-dataset pass
is now genuine pandas-vectorized groupby/aggregation (see _long_form,
_typical_card_tally, _typical_tower_tally below) instead of a Python-level
row loop, so the FULL history can be processed safely and efficiently again.
The two genuinely row-wise steps that remain (exact-deck canonicalization,
and archetype_label's opponent-strategy classification) are each done in a
SINGLE pass reused by every function that needs them, and the archetype
classification is computed only once per UNIQUE opponent deck (map/cache,
not once per battle) -- both a fraction of the old cost, which repeated
similar work independently inside multiple separate iterrows() loops.
"""
import itertools
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict, Counter

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.data_loader import get_card_match_id_map, load_card_reference  # noqa: E402
from utils.arena_data import get_arena_for_trophies, ARENA_TABLE  # noqa: E402
from utils.counter_suggester import archetype_label  # noqa: E402

# Trophy count alone is a poor proxy for "what cards this account actually has
# unlocked" -- veteran accounts pass through low trophy ranges constantly
# (season resets, deliberate trophy-dropping, alts) while keeping their fully
# leveled collection. Card level, unlike trophies, only ever goes up, so it's
# a much better signal of account maturity. Below Arena 10 / 3000 trophies
# (the existing Wild-slot-unlock threshold elsewhere in this app) a battle
# side averaging at/above level 11 -- the level Champion cards *start* at,
# already a meaningful reference point used throughout this app -- is clearly
# not a new/mid-progression account, so it's excluded from that arena's
# bucket. This is a blunt, clearly-approximate filter, not exact science --
# see utils/arena_data.py's own caveat about the trophy road's uncertainty.
VETERAN_LEVEL_CUTOFF = 11
LOW_ARENA_TROPHY_CEILING = 3000
ARENA_THRESHOLDS = dict((name, threshold) for threshold, name in ARENA_TABLE)
_ARENA_BIN_EDGES = [t for t, _ in ARENA_TABLE] + [float("inf")]
_ARENA_BIN_LABELS = [name for _, name in ARENA_TABLE]

COLLECTED_PATH = REPO_ROOT / "data" / "collected_battles.csv"
LIVE_CARD_STATS_PATH = REPO_ROOT / "data" / "card_stats_live.csv"
LIVE_SYNERGY_PATH = REPO_ROOT / "data" / "card_synergy_live.csv"
LIVE_ARCHETYPES_PATH = REPO_ROOT / "data" / "deck_archetypes_live.csv"
LIVE_ARENA_USAGE_PATH = REPO_ROOT / "data" / "card_usage_by_arena_live.csv"
LIVE_ARCHETYPES_BY_ARENA_PATH = REPO_ROOT / "data" / "deck_archetypes_by_arena_live.csv"
LIVE_DECK_MATCHUPS_PATH = REPO_ROOT / "data" / "deck_matchups_live.csv"
LIVE_DECK_MATCHUP_SCORELINES_PATH = REPO_ROOT / "data" / "deck_matchup_scorelines_live.csv"
LIVE_CARD_VARIANT_USAGE_PATH = REPO_ROOT / "data" / "card_variant_usage_live.csv"
LIVE_TOWER_TROOP_USAGE_PATH = REPO_ROOT / "data" / "tower_troop_usage_live.csv"
LIVE_ELIXIR_LEAK_PATH = REPO_ROOT / "data" / "elixir_leak_stats_live.csv"
LIVE_DECK_STRATEGY_SUMMARY_PATH = REPO_ROOT / "data" / "deck_strategy_summary_live.csv"
LIVE_STRATEGY_MATCHUPS_PATH = REPO_ROOT / "data" / "strategy_matchups_live.csv"
LIVE_MODEL_PATH = REPO_ROOT / "data" / "models" / "win_predictor_live.joblib"
LIVE_MODEL_META_PATH = REPO_ROOT / "data" / "models" / "win_predictor_live_meta.json"

# Real production incident (2026-08-28, part 2): the vectorized rewrite
# above genuinely fixed the CPU/time cost of retraining (no more iterrows()),
# but a live test at production's actual scale (4.3M+ rows) showed the
# MEMORY cost is still a real problem on its own -- _long_form melts every
# battle into two rows and materializes list-typed columns, and holding that
# (plus each function's own derived tables) for the full unbounded history
# pushed the container to ~90% memory and into swap, caught and aborted
# before it repeated the earlier crash. A first attempt at a safety net
# (RETRAIN_WINDOW_DAYS = 120) turned out to barely reduce row count at all --
# the crawler hasn't been running anywhere near 120 days, so nearly the
# entire dataset was still "within the window," and a second live test
# climbed toward the same danger zone before being aborted again. A
# calendar-day window is fundamentally the wrong kind of cap here: it
# doesn't bound row count directly, and row count (not elapsed days) is what
# memory usage actually scales with -- worse, it silently gets MORE
# dangerous over time as the crawler's daily volume grows, with no signal
# that it's happening until it crashes again. RETRAIN_MAX_ROWS below is a
# hard, deterministic row-count ceiling instead (the CSV is already in
# chronological append order, so "most recent N rows" is just the file's
# tail) -- this bounds memory directly and predictably regardless of how
# long the crawler has been running or how fast it's collecting. Removing
# this cap entirely needs a genuinely different approach (chunked/streaming
# aggregation instead of one big in-memory table), not yet built.
RETRAIN_WINDOW_DAYS = 120
RETRAIN_MAX_ROWS = 800_000  # ~10.4GB peak was observed at 4.3M rows -- this leaves real headroom

MIN_BATTLES_FOR_CARD_STATS = 500
MIN_BATTLES_FOR_SYNERGY = 500
MIN_BATTLES_FOR_MODEL = 5000
MIN_MATCHUP_COUNT = 5
MIN_BATTLES_FOR_EVO_USAGE = 200
MIN_BATTLES_FOR_TOWER_TROOP = 200

# collected_at cutoff for real Evolution/Hero usage tracking (added
# 2026-07-31/08-01) -- rows collected before this were backfilled with BLANK
# team_evolved_cards/team_hero_cards/etc. by _migrate_schema, which means
# "not tracked yet," not "nothing was evolved." Using collected_at (never
# touched by the migration) to only count genuinely-tracked battles keeps
# active_rate_pct from being silently diluted by that untracked backlog.
EVOLUTION_TRACKING_ADDED_AT = "2026-08-01T00:00:00+00:00"

# Same idea, for the Tower Troop + elixir-leaked columns added right after
# (both real fields discovered in the same raw battlelog response --
# supportCards and elixirLeaked -- confirmed via direct API inspection).
TOWER_TROOP_TRACKING_ADDED_AT = "2026-08-01T01:00:00+00:00"


def _count_csv_rows(path: Path) -> int:
    """Fast, memory-safe row count -- streams the file line-by-line without
    ever holding more than one line at a time, unlike pd.read_csv which
    materializes the whole thing."""
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8", newline="") as f:
        return sum(1 for _ in f) - 1  # minus header


def load_collected(max_rows: int | None = None) -> pd.DataFrame:
    """Real production incident (2026-08-28, part 3): the row/date caps in
    main() below used to filter AFTER this function returned -- but this
    function itself did `pd.read_csv(COLLECTED_PATH)` unconditionally,
    reading the ENTIRE file into memory first regardless of what got
    filtered out afterward. A "capped" retrain run still climbed toward the
    same OOM danger a full run did, caught and aborted live on production
    twice in one session, because the expensive part (materializing millions
    of rows) had already happened before any cap applied. `max_rows` fixes
    this at the SOURCE: the CSV is already in chronological append order, so
    the most recent max_rows lines are read via a bounded deque (constant
    memory -- older lines are evicted as new ones arrive, never all held at
    once) instead of a full pandas parse of the whole file."""
    if not COLLECTED_PATH.exists():
        return pd.DataFrame()
    if max_rows is None:
        return pd.read_csv(COLLECTED_PATH)

    from collections import deque
    from io import StringIO

    with open(COLLECTED_PATH, "r", encoding="utf-8", newline="") as f:
        header = f.readline()
        tail = deque(f, maxlen=max_rows)
    return pd.read_csv(StringIO(header + "".join(tail)))


def _long_form(df: pd.DataFrame) -> pd.DataFrame:
    """Melts each battle (one row) into two rows -- one per side -- mirroring
    the `for side in [(team...), (opponent...)]` pattern every build_*
    function used to loop over with iterrows(). Built ONCE and reused by
    every function below instead of each doing its own separate full-dataset
    pass. `won` is 1/0/NaN (NaN for a real Draw, matching the old code's
    "Win"/"Loss"/"Draw" three-way result, which only ever affected win-rate
    denominators via explicit result-string checks, never counted a draw as
    a loss)."""
    n = len(df)
    idx = np.arange(n)
    flip = {"Win": "Loss", "Loss": "Win"}
    result = df["result"]
    opp_result = result.map(flip).fillna("Draw")

    team = pd.DataFrame({
        "battle_id": idx, "side": "team",
        "cards": df["team_cards"], "opp_cards": df["opponent_cards"],
        "result": result, "trophies": df.get("team_trophies"), "avg_level": df.get("team_avg_level"),
        "evolved_cards": df.get("team_evolved_cards"), "hero_cards": df.get("team_hero_cards"),
        "ambiguous_cards": df.get("team_ambiguous_cards"),
        "tower_troop": df.get("team_tower_troop"), "elixir_leaked": df.get("team_elixir_leaked"),
        "my_crowns": df.get("team_crowns"), "opp_crowns": df.get("opponent_crowns"),
        "collected_at": df.get("collected_at"),
    })
    opp = pd.DataFrame({
        "battle_id": idx, "side": "opponent",
        "cards": df["opponent_cards"], "opp_cards": df["team_cards"],
        "result": opp_result, "trophies": df.get("opponent_trophies"), "avg_level": df.get("opponent_avg_level"),
        "evolved_cards": df.get("opponent_evolved_cards"), "hero_cards": df.get("opponent_hero_cards"),
        "ambiguous_cards": df.get("opponent_ambiguous_cards"),
        "tower_troop": df.get("opponent_tower_troop"), "elixir_leaked": df.get("opponent_elixir_leaked"),
        "my_crowns": df.get("opponent_crowns"), "opp_crowns": df.get("team_crowns"),
        "collected_at": df.get("collected_at"),
    })
    long = pd.concat([team, opp], ignore_index=True)
    long["cards"] = long["cards"].fillna("").astype(str)
    long["opp_cards"] = long["opp_cards"].fillna("").astype(str)
    long["cards_list"] = long["cards"].str.split(";")
    long["won"] = np.where(long["result"] == "Win", 1, np.where(long["result"] == "Loss", 0, np.nan))
    long["collected_at"] = long["collected_at"].astype(str)
    return long


def _looks_like_veteran_mask(arena: pd.Series, avg_level: pd.Series) -> pd.Series:
    """Vectorized form of the old per-row _looks_like_veteran_in_low_arena --
    True where a battle-side looks like a veteran account passing through a
    low arena (see the module docstring above) and should be EXCLUDED from
    that arena's bucket."""
    low_arena = arena.map(ARENA_THRESHOLDS).fillna(0) < LOW_ARENA_TROPHY_CEILING
    veteran = pd.to_numeric(avg_level, errors="coerce") >= VETERAN_LEVEL_CUTOFF
    return low_arena & veteran.fillna(False)


def _canonical_deck_key(cards_list: pd.Series) -> pd.Series:
    """Sorted, semicolon-joined 8-card deck key -- same identity
    tuple(sorted(cards)) used to represent as a dict key, just as a string so
    it works directly as a pandas groupby key. NaN/None for anything that
    isn't exactly 8 cards (mirrors the old `if len(cards) != 8: continue`
    skip). This single pass is reused by every deck-level function below,
    instead of each recomputing it inside its own iterrows() loop."""
    def _key(cards):
        return ";".join(sorted(cards)) if len(cards) == 8 else None
    return cards_list.apply(_key)


def _archetype_label_map(opp_cards: pd.Series) -> pd.Series:
    """archetype_label() is a real (if small) function call -- calling it
    once per UNIQUE opponent deck string and mapping the result back is a
    fraction of the cost of calling it once per battle-side (millions of
    calls collapse to however many distinct 8-card decks actually appear)."""
    unique = opp_cards.unique()
    label_of = {s: archetype_label(s.split(";")) for s in unique}
    return opp_cards.map(label_of)


def _typical_card_tally(keys: pd.Series, tracked_mask: pd.Series, field: pd.Series,
                         min_sightings: int) -> pd.DataFrame:
    """Vectorized replacement for the old _record_deck_evo_hero /
    _typical_evo_hero nested-Counter approach: for each group key, the
    single most common non-empty card in `field` (semicolon-joined) among
    TRACKED rows (collected_at >= the relevant tracking-added-at cutoff),
    and what % of that key's tracked sightings it represents. Sightings
    count every tracked row for that key regardless of whether `field` was
    empty on it -- matches the original's unconditional `tracked_sightings
    [deck_key] += 1` once past the cutoff. Returns a DataFrame indexed by
    key with columns 'typical'/'rate_pct' (None where below min_sightings or
    no tracked rows for that key at all)."""
    k = keys[tracked_mask]
    if len(k) == 0:
        return pd.DataFrame(columns=["typical", "rate_pct"])
    sightings = k.groupby(k).size()
    exploded = field[tracked_mask].fillna("").astype(str).str.split(";")
    pairs = pd.DataFrame({"key": k.values, "card": exploded.values}).explode("card")
    pairs = pairs[pairs["card"].fillna("") != ""]
    out = pd.DataFrame(index=sightings.index)
    out["sightings"] = sightings
    if len(pairs) > 0:
        counts = pairs.groupby(["key", "card"]).size().reset_index(name="n")
        top = (counts.sort_values("n", ascending=False)
                      .drop_duplicates("key", keep="first")
                      .set_index("key"))
        out = out.join(top[["card", "n"]])
    else:
        out["card"], out["n"] = None, np.nan
    out["typical"] = out["card"]
    out["rate_pct"] = (out["n"] / out["sightings"] * 100).round(1)
    below = out["sightings"] < min_sightings
    out.loc[below, ["typical", "rate_pct"]] = [None, None]
    return out[["typical", "rate_pct"]]


def _typical_tower_tally(keys: pd.Series, tracked_mask: pd.Series, troop: pd.Series,
                          won: pd.Series, min_sightings: int) -> pd.DataFrame:
    """Same idea as _typical_card_tally, but for the single-value
    team_tower_troop/opponent_tower_troop field (not a semicolon list), and
    also reports the top troop's own real win rate. Sightings only count
    rows where the troop field is actually present -- matches the original
    _record_deck_tower_troop's `... or not troop_field: return` guard,
    unlike the evo/hero tally above (which counts sightings unconditionally
    once tracked)."""
    troop_all = troop.fillna("").astype(str)
    valid = tracked_mask & (troop_all != "")
    k = keys[valid]
    if len(k) == 0:
        return pd.DataFrame(columns=["typical_tower_troop", "tower_troop_rate_pct", "tower_troop_win_rate_pct"])
    sightings = k.groupby(k).size()
    tmp = pd.DataFrame({"key": k.values, "troop": troop_all[valid].values, "won": won[valid].fillna(0).values})
    grp = tmp.groupby(["key", "troop"]).agg(n=("won", "size"), wins=("won", "sum")).reset_index()
    top = grp.sort_values("n", ascending=False).drop_duplicates("key", keep="first").set_index("key")
    out = pd.DataFrame(index=sightings.index)
    out["sightings"] = sightings
    out = out.join(top[["troop", "n", "wins"]])
    out["typical_tower_troop"] = out["troop"]
    out["tower_troop_rate_pct"] = (out["n"] / out["sightings"] * 100).round(1)
    out["tower_troop_win_rate_pct"] = (out["wins"] / out["n"] * 100).round(1)
    below = out["sightings"] < min_sightings
    out.loc[below, ["typical_tower_troop", "tower_troop_rate_pct", "tower_troop_win_rate_pct"]] = [None, None, None]
    return out[["typical_tower_troop", "tower_troop_rate_pct", "tower_troop_win_rate_pct"]]


def build_card_stats(long: pd.DataFrame) -> pd.DataFrame:
    """Same shape as data/card_stats.csv: card_name, times_used, wins, win_rate,
    presence_rate, elixir -- but computed purely from collected_battles.csv."""
    from utils.data_loader import get_elixir_costs
    elixir_costs = get_elixir_costs()

    valid = long[long["cards"] != ""]
    total_sides = len(valid)
    exploded = valid[["cards_list", "won"]].explode("cards_list")
    exploded = exploded[exploded["cards_list"] != ""]
    grp = exploded.groupby("cards_list").agg(
        times_used=("won", "size"), wins=("won", "sum")
    ).reset_index().rename(columns={"cards_list": "card_name"})
    grp["wins"] = grp["wins"].astype(int)
    grp["win_rate"] = (grp["wins"] / grp["times_used"]).round(4)
    grp["presence_rate"] = (grp["times_used"] / total_sides).round(4) if total_sides else np.nan
    grp["elixir"] = grp["card_name"].map(elixir_costs)
    return grp.sort_values("times_used", ascending=False)


def build_arena_card_usage(long: pd.DataFrame) -> pd.DataFrame:
    """card_name x arena -> times_used/wins/win_rate, bucketed by each side's
    real starting trophies (see utils/arena_data.py for the bucket table).
    Only rows collected since trophy capture was added have this -- older
    rows have blank team_trophies/opponent_trophies and are skipped here.
    Also excludes battle-sides that look like a veteran account passing
    through a low arena rather than a genuinely new/mid-progression one --
    see _looks_like_veteran_mask above."""
    trophies = pd.to_numeric(long["trophies"], errors="coerce")
    arena = pd.cut(trophies, bins=_ARENA_BIN_EDGES, labels=_ARENA_BIN_LABELS,
                    right=False, include_lowest=True)
    keep = trophies.notna() & ~_looks_like_veteran_mask(arena, long["avg_level"])
    sub = long[keep].copy()
    sub["arena"] = arena[keep]

    exploded = sub[["arena", "cards_list", "won"]].explode("cards_list")
    exploded = exploded[exploded["cards_list"] != ""]
    usage = exploded.groupby(["arena", "cards_list"]).agg(
        times_used=("won", "size"), wins=("won", "sum")
    ).reset_index().rename(columns={"cards_list": "card_name"})
    usage = usage[usage["times_used"] > 0]
    usage["win_rate"] = (usage["wins"] / usage["times_used"]).round(4)

    level = pd.to_numeric(sub["avg_level"], errors="coerce")
    level_avg = level.groupby(sub["arena"], observed=True).mean().round(1)
    usage["arena_avg_level"] = usage["arena"].map(level_avg)
    usage = usage.drop(columns="wins")
    return usage.sort_values(["arena", "times_used"], ascending=[True, False])


def build_card_synergy(long: pd.DataFrame) -> pd.DataFrame:
    """Same shape as data/card_synergy.csv (card_a, card_b, co_occurrence,
    win_rate_together) -- but from real, current collected battles instead of
    the 2023 sample. Each battle-side's full deck contributes every pairwise
    combination of its cards (mirroring scripts/build_analytics_data.py's
    approach, just per-battle-side instead of per-unique-deck). Genuine
    pairwise counting doesn't reduce to a plain groupby the way the other
    functions here do, so this uses itertuples() (which -- unlike iterrows()
    -- doesn't box each row into a full Series, a real, measurable saving at
    this scale) over just the 2 columns actually needed, instead of the
    wide 26-column frame the old iterrows() version pulled per row."""
    pair_freq = Counter()
    pair_wins = Counter()

    for cards, won in long[["cards", "won"]].itertuples(index=False, name=None):
        if not cards:
            continue
        deck = sorted(set(cards.split(";")))
        if len(deck) < 2:
            continue
        w = 1 if won == 1 else 0
        for a, b in itertools.combinations(deck, 2):
            pair_freq[(a, b)] += 1
            pair_wins[(a, b)] += w

    rows = [
        {"card_a": a, "card_b": b, "co_occurrence": freq,
         "win_rate_together": round(pair_wins[(a, b)] / freq, 4)}
        for (a, b), freq in pair_freq.items()
    ]
    return pd.DataFrame(rows).sort_values("co_occurrence", ascending=False)


MIN_EVO_HERO_SIGHTINGS_PER_DECK = 5  # below this, "typical evolution/hero" for a deck is noise
MIN_TOWER_TROOP_SIGHTINGS_PER_DECK = 5  # same reasoning, for typical_tower_troop below


def _deck_level_frame(long: pd.DataFrame) -> pd.DataFrame:
    """Shared setup for build_deck_archetypes[_by_arena]/build_deck_matchups/
    build_deck_matchup_scorelines: adds the canonical 8-card deck key (see
    _canonical_deck_key) and drops any side that isn't a real 8-card deck,
    once, for every deck-level function to reuse."""
    sub = long.copy()
    sub["deck_key"] = _canonical_deck_key(sub["cards_list"])
    return sub[sub["deck_key"].notna()]


def _attach_typical_columns(rows: pd.DataFrame, key_col: str, deck_level: pd.DataFrame,
                             group_keys: pd.Series) -> pd.DataFrame:
    """Joins typical_evolution/hero/ambiguous + typical_tower_troop columns
    onto an already-aggregated deck/matchup table, keyed by `group_keys`
    (same length/order as deck_level, one aggregation key per row -- either
    just deck_key, or a combined (arena, deck_key)/(vs_archetype, deck_key)
    string for the bucketed variants)."""
    tracked_evo = deck_level["collected_at"] >= EVOLUTION_TRACKING_ADDED_AT
    tracked_tower = deck_level["collected_at"] >= TOWER_TROOP_TRACKING_ADDED_AT

    evo = _typical_card_tally(group_keys, tracked_evo, deck_level["evolved_cards"], MIN_EVO_HERO_SIGHTINGS_PER_DECK)
    hero = _typical_card_tally(group_keys, tracked_evo, deck_level["hero_cards"], MIN_EVO_HERO_SIGHTINGS_PER_DECK)
    ambig = _typical_card_tally(group_keys, tracked_evo, deck_level["ambiguous_cards"], MIN_EVO_HERO_SIGHTINGS_PER_DECK)
    tower = _typical_tower_tally(group_keys, tracked_tower, deck_level["tower_troop"], deck_level["won"],
                                  MIN_TOWER_TROOP_SIGHTINGS_PER_DECK)

    rows = rows.set_index(key_col)
    rows["typical_evolution"] = evo["typical"]
    rows["evolution_rate_pct"] = evo["rate_pct"]
    rows["typical_hero"] = hero["typical"]
    rows["hero_rate_pct"] = hero["rate_pct"]
    rows["typical_ambiguous"] = ambig["typical"]
    rows["ambiguous_rate_pct"] = ambig["rate_pct"]
    rows["typical_tower_troop"] = tower["typical_tower_troop"]
    rows["tower_troop_rate_pct"] = tower["tower_troop_rate_pct"]
    rows["tower_troop_win_rate_pct"] = tower["tower_troop_win_rate_pct"]
    return rows.reset_index().rename(columns={key_col: key_col})


def build_deck_archetypes(long: pd.DataFrame, min_deck_count: int = 3) -> pd.DataFrame:
    """Groups battles by their exact 8-card deck (both sides), same idea as
    scripts/build_analytics_data.py's clustering step but simpler -- exact-deck
    grouping instead of KMeans, since live volume is still far too small for
    meaningful clustering. Real decks appearing at least min_deck_count times.
    Also tracks each deck's real 'typical' Evolution/Hero card so Top Decks
    can show which card is actually evolved/hero'd for that specific deck,
    not just base card art."""
    dl = _deck_level_frame(long)
    agg = dl.groupby("deck_key").agg(
        frequency=("won", "size"), wins=("won", "sum")
    ).reset_index()
    agg = agg[agg["frequency"] >= min_deck_count].copy()
    agg["deck"] = agg["deck_key"]
    agg["wins"] = agg["wins"].astype(int)
    agg["win_rate"] = (agg["wins"] / agg["frequency"]).round(4)

    result = _attach_typical_columns(agg, "deck_key", dl, dl["deck_key"])
    result = result.drop(columns="deck_key")
    return result[["deck", "frequency", "wins", "win_rate",
                    "typical_evolution", "evolution_rate_pct", "typical_hero", "hero_rate_pct",
                    "typical_ambiguous", "ambiguous_rate_pct",
                    "typical_tower_troop", "tower_troop_rate_pct", "tower_troop_win_rate_pct"]] \
        .sort_values("frequency", ascending=False)


def build_deck_archetypes_by_arena(long: pd.DataFrame, min_deck_count: int = 2) -> pd.DataFrame:
    """Same idea as build_deck_archetypes, but bucketed by arena (via each
    side's real starting trophies, see utils/arena_data.py) so 'Top Decks'
    can be filtered to a specific arena/trophy range instead of only an
    all-time view. Lower min_deck_count than the all-time version since each
    arena bucket naturally has less volume. Also excludes battle-sides that
    look like a veteran account passing through a low arena rather than a
    genuinely new/mid-progression one -- see _looks_like_veteran_mask."""
    dl = _deck_level_frame(long)
    trophies = pd.to_numeric(dl["trophies"], errors="coerce")
    arena = pd.cut(trophies, bins=_ARENA_BIN_EDGES, labels=_ARENA_BIN_LABELS,
                    right=False, include_lowest=True)
    keep = trophies.notna() & ~_looks_like_veteran_mask(arena, dl["avg_level"])
    dl = dl[keep].copy()
    dl["arena"] = arena[keep].astype(str)
    dl["key"] = dl["arena"] + "\x1f" + dl["deck_key"]

    agg = dl.groupby("key").agg(frequency=("won", "size"), wins=("won", "sum")).reset_index()
    agg = agg[agg["frequency"] >= min_deck_count].copy()
    agg["wins"] = agg["wins"].astype(int)
    agg["win_rate"] = (agg["wins"] / agg["frequency"]).round(4)

    result = _attach_typical_columns(agg, "key", dl, dl["key"])
    result[["arena", "deck"]] = result["key"].str.split("\x1f", n=1, expand=True)
    result = result.drop(columns="key")
    return result[["arena", "deck", "frequency", "wins", "win_rate",
                    "typical_evolution", "evolution_rate_pct", "typical_hero", "hero_rate_pct",
                    "typical_ambiguous", "ambiguous_rate_pct",
                    "typical_tower_troop", "tower_troop_rate_pct", "tower_troop_win_rate_pct"]] \
        .sort_values(["arena", "frequency"], ascending=[True, False])


def build_deck_matchups(long: pd.DataFrame, min_matchup_count: int = MIN_MATCHUP_COUNT) -> pd.DataFrame:
    """The real-data backbone for 'decks that have been seen and tested to
    beat X' -- replaces the old approach of synthesizing a counter deck from
    disconnected per-card counter scores (utils/counter_suggester.py's
    generate_counter_deck). For every real battle-side, labels the OPPONENT's
    deck by archetype (utils.counter_suggester.archetype_label, keyed off its
    win condition) and groups by (my exact 8-card deck, opponent's archetype)
    -> how often that deck was actually played against that archetype and how
    often it won. Also tracks each (archetype, deck)'s real 'typical'
    Evolution/Hero card, same as build_deck_archetypes."""
    dl = _deck_level_frame(long)
    dl = dl.copy()
    dl["vs_archetype"] = _archetype_label_map(dl["opp_cards"])
    dl["key"] = dl["vs_archetype"] + "\x1f" + dl["deck_key"]

    agg = dl.groupby("key").agg(frequency=("won", "size"), wins=("won", "sum")).reset_index()
    agg = agg[agg["frequency"] >= min_matchup_count].copy()
    agg["wins"] = agg["wins"].astype(int)
    agg["win_rate"] = (agg["wins"] / agg["frequency"]).round(4)

    result = _attach_typical_columns(agg, "key", dl, dl["key"])
    result[["vs_archetype", "deck"]] = result["key"].str.split("\x1f", n=1, expand=True)
    result = result.drop(columns="key")
    return result[["vs_archetype", "deck", "frequency", "wins", "win_rate",
                    "typical_evolution", "evolution_rate_pct", "typical_hero", "hero_rate_pct",
                    "typical_ambiguous", "ambiguous_rate_pct",
                    "typical_tower_troop", "tower_troop_rate_pct", "tower_troop_win_rate_pct"]] \
        .sort_values(["vs_archetype", "win_rate"], ascending=[True, False])


def build_deck_matchup_scorelines(long: pd.DataFrame, min_matchup_count: int = MIN_MATCHUP_COUNT) -> pd.DataFrame:
    """Real crown-score distribution (e.g. '2-1', '3-0') for every (my deck,
    opponent archetype) matchup already tracked by build_deck_matchups -- same
    grouping, but tallying the real team_crowns/opponent_crowns fields (always
    present, no tracked-since cutoff) instead of collapsing to a plain
    win/loss. Backs a 'predicted outcome' feature that can cite an actual
    observed scoreline distribution ('this exact matchup ends 2-1 38% of the
    time, 3-0 22% of the time...') rather than only a binary win probability."""
    dl = _deck_level_frame(long)
    dl = dl.copy()
    my_crowns = pd.to_numeric(dl["my_crowns"], errors="coerce")
    opp_crowns = pd.to_numeric(dl["opp_crowns"], errors="coerce")

    valid = my_crowns.notna() & opp_crowns.notna()
    dl = dl[valid].copy()
    my_crowns, opp_crowns = my_crowns[valid], opp_crowns[valid]
    dl["vs_archetype"] = _archetype_label_map(dl["opp_cards"])
    dl["scoreline"] = my_crowns.astype(int).astype(str) + "-" + opp_crowns.astype(int).astype(str)
    dl["key"] = dl["vs_archetype"] + "\x1f" + dl["deck_key"]

    total = dl.groupby("key").size().rename("total")
    counts = dl.groupby(["key", "scoreline"]).size().reset_index(name="count")
    counts = counts.join(total, on="key")
    counts = counts[counts["total"] >= min_matchup_count]
    counts["pct"] = (counts["count"] / counts["total"] * 100).round(1)
    counts[["vs_archetype", "deck"]] = counts["key"].str.split("\x1f", n=1, expand=True)
    counts = counts.drop(columns="key")
    return counts[["vs_archetype", "deck", "scoreline", "count", "total", "pct"]] \
        .sort_values(["vs_archetype", "deck", "pct"], ascending=[True, True, False])


def build_card_variant_usage(long: pd.DataFrame, min_battles: int = MIN_BATTLES_FOR_EVO_USAGE) -> pd.DataFrame:
    """Real usage/win-rate stats PER VARIANT for every Evolution/Hero-capable
    card -- "Knight" isn't one card for this purpose, it's up to real,
    separately-tracked ones: Regular Knight, Evolved Knight, Hero Knight, and
    (for the dual-capable cards only -- Knight/Musketeer/Wizard/Valkyrie)
    "Evolved-or-Hero Knight" when the real match confirms it was active but
    which of the two systems can't be told apart (see
    services/card_service.split_evolution_hero_cards's docstring). Only ever
    computed over battles collected AFTER evolution/hero tracking was added
    (see EVOLUTION_TRACKING_ADDED_AT), never the backfilled-blank historical
    backlog. Cards with no Evolution/Hero capability at all aren't included
    here -- their single real number is already build_card_stats's
    card_stats_live.csv."""
    if "evolved_cards" not in long.columns or "collected_at" not in long.columns:
        return pd.DataFrame()

    tracked = long[long["collected_at"] >= EVOLUTION_TRACKING_ADDED_AT]
    if len(tracked) < min_battles:
        return pd.DataFrame()

    ref = load_card_reference()
    capable = {row["card_name"] for _, row in ref.iterrows()
               if bool(row["has_evolution"]) or bool(row.get("has_hero", False))}

    exploded = tracked[["cards_list", "evolved_cards", "hero_cards", "ambiguous_cards", "won"]].explode("cards_list")
    exploded = exploded[exploded["cards_list"].isin(capable)]
    if exploded.empty:
        return pd.DataFrame()

    evolved_set = exploded["evolved_cards"].fillna("").astype(str).str.split(";")
    hero_set = exploded["hero_cards"].fillna("").astype(str).str.split(";")
    ambig_set = exploded["ambiguous_cards"].fillna("").astype(str).str.split(";")
    card = exploded["cards_list"]

    is_evo = [c in s for c, s in zip(card, evolved_set)]
    is_hero = [c in s for c, s in zip(card, hero_set)]
    is_ambig = [c in s for c, s in zip(card, ambig_set)]
    variant = np.select([is_evo, is_hero, is_ambig], ["evolution", "hero", "evolved_or_hero"], default="regular")

    tmp = pd.DataFrame({"card_name": card.values, "kind": variant, "won": exploded["won"].values})
    usage = tmp.groupby(["card_name", "kind"]).agg(times_used=("won", "size"), wins=("won", "sum")).reset_index()
    total_seen = usage.groupby("card_name")["times_used"].transform("sum")
    usage["total_seen"] = total_seen
    usage["win_rate_pct"] = (usage["wins"] / usage["times_used"] * 100).round(1)
    return usage[["card_name", "kind", "times_used", "total_seen", "win_rate_pct"]].sort_values(["card_name", "kind"])


def build_tower_troop_usage(long: pd.DataFrame, min_battles: int = MIN_BATTLES_FOR_TOWER_TROOP) -> pd.DataFrame:
    """Real 'which King Tower Troop do people actually use, how often, how
    well' -- from the battlelog's real per-match supportCards field (see
    players.py's _tower_troop_name). Same tracked-battles-only cutoff pattern
    as build_card_variant_usage, for the same reason (old rows were
    backfilled blank, not genuinely 'no tower troop used')."""
    if "tower_troop" not in long.columns or "collected_at" not in long.columns:
        return pd.DataFrame()

    tracked = long[long["collected_at"] >= TOWER_TROOP_TRACKING_ADDED_AT]
    if len(tracked) < min_battles:
        return pd.DataFrame()

    sub = tracked[tracked["tower_troop"].notna() & (tracked["tower_troop"] != "")]
    if sub.empty:
        return pd.DataFrame()
    usage = sub.groupby("tower_troop").agg(times_used=("won", "size"), wins=("won", "sum")).reset_index()
    usage = usage.rename(columns={"tower_troop": "tower_troop"})
    usage["win_rate"] = (usage["wins"] / usage["times_used"]).round(4)
    return usage[["tower_troop", "times_used", "win_rate"]].sort_values("times_used", ascending=False)


def build_elixir_leak_stats(long: pd.DataFrame, min_battles: int = MIN_BATTLES_FOR_TOWER_TROOP) -> pd.DataFrame:
    """Real average elixir-leaked (unspent elixir sitting idle, per Supercell's
    own elixirLeaked field) bucketed by deck archetype (same archetype_label
    used for deck-matchup aggregation) -- lets Coaching compare a player's own
    real average against what similar decks typically leak. Tracked-battles-
    only, same reasoning as the other post-cutoff aggregations above."""
    if "elixir_leaked" not in long.columns or "collected_at" not in long.columns:
        return pd.DataFrame()

    tracked = long[long["collected_at"] >= TOWER_TROOP_TRACKING_ADDED_AT]
    if len(tracked) < min_battles:
        return pd.DataFrame()

    leak = pd.to_numeric(tracked["elixir_leaked"], errors="coerce")
    dl = tracked[leak.notna() & (tracked["cards_list"].str.len() == 8)].copy()
    leak = leak[leak.notna() & (tracked["cards_list"].str.len() == 8)]
    if dl.empty:
        return pd.DataFrame()
    dl["archetype"] = _archetype_label_map(dl["cards"])
    tmp = pd.DataFrame({"archetype": dl["archetype"].values, "leak": leak.values})
    grp = tmp.groupby("archetype").agg(avg_elixir_leaked=("leak", "mean"), battles=("leak", "size")).reset_index()
    grp["avg_elixir_leaked"] = grp["avg_elixir_leaked"].round(2)
    grp = grp[grp["battles"] >= 5]  # per-archetype minimum sample, separate from the overall gate above
    return grp.sort_values("battles", ascending=False)


def build_deck_strategy_summary(archetypes_df: pd.DataFrame) -> pd.DataFrame:
    """Groups the COMPLETE deck_archetypes_live.csv table (every real deck ever
    seen, any context) by real strategy label (archetype_label: primary win
    condition + flavor tags, e.g. 'Hog Rider (cycle)'), pooling every exact
    8-card variant of that strategy's real frequency/wins together. This is
    the 'games played across all decks of that strategy' number -- e.g. every
    Hog Cycle build's real games summed, a much larger and more reliable
    sample than any single exact 8-card build usually has on its own. One
    canonical table (built from the all-time archetypes, not a smaller
    context-filtered one) so 'Hog Cycle overall' means the same thing
    everywhere it's shown -- Top Decks, Counter tab, or anywhere else that
    joins on this by archetype_label(deck)."""
    if archetypes_df.empty:
        return pd.DataFrame(columns=["strategy", "deck_count", "total_frequency", "total_wins", "win_rate"])
    tmp = archetypes_df.copy()
    tmp["strategy"] = tmp["deck"].apply(lambda d: archetype_label(str(d).split(";")))
    grouped = tmp.groupby("strategy").agg(
        deck_count=("deck", "nunique"),
        total_frequency=("frequency", "sum"),
        total_wins=("wins", "sum"),
    ).reset_index()
    grouped["win_rate"] = (grouped["total_wins"] / grouped["total_frequency"]).round(4)
    return grouped.sort_values("total_frequency", ascending=False)


def build_strategy_matchups(deck_matchups_df: pd.DataFrame) -> pd.DataFrame:
    """Pools build_deck_matchups's per-EXACT-DECK rows up to the STRATEGY
    level on both sides (the opponent's vs_archetype, and MY deck's own real
    strategy via archetype_label) -- e.g. 'X-Bow Siege has real games against
    Hog Cycle: 4,200, winning 54%', not a single exact deck's much smaller
    matchup count (which can be as low as MIN_MATCHUP_COUNT). This is what
    lets 'counters for strategy X' rank by STRATEGY with a genuinely large,
    reliable sample, instead of only ever exact-deck numbers. Real games
    played per (opponent strategy, my strategy) pair, summed across every
    exact deck variant that clears MIN_MATCHUP_COUNT -- a slight undercount
    of the true total is possible since deck_matchups_live.csv itself already
    dropped exact matchups seen fewer times than that, but that only makes
    this conservative, never inflated."""
    if deck_matchups_df.empty:
        return pd.DataFrame(columns=["vs_strategy", "my_strategy", "frequency", "wins", "win_rate", "deck_count"])
    tmp = deck_matchups_df.copy()
    tmp["my_strategy"] = tmp["deck"].apply(lambda d: archetype_label(str(d).split(";")))
    grouped = tmp.groupby(["vs_archetype", "my_strategy"]).agg(
        frequency=("frequency", "sum"),
        wins=("wins", "sum"),
        deck_count=("deck", "nunique"),
    ).reset_index().rename(columns={"vs_archetype": "vs_strategy"})
    grouped["win_rate"] = (grouped["wins"] / grouped["frequency"]).round(4)
    return grouped.sort_values(["vs_strategy", "frequency"], ascending=[True, False])


# Deck Quality Model -- predicts a deck's win rate from its CARD COMPOSITION
# (role-tag counts, elixir curve, primary win condition, evolution/hero
# presence) rather than its exact 8-card identity. That's what lets it
# generalize ACROSS decks: two different Hog Cycle variants share almost all
# of these features, so a well-tested variant's real result informs the
# estimate for a barely-tested one, instead of every exact build being judged
# in total isolation on its own tiny sample. Trained only on decks with
# enough real games to trust as training signal; applied afterward to every
# deck, including the thin ones this whole thing exists to help.
DECK_QUALITY_MODEL_PATH = REPO_ROOT / "data" / "models" / "deck_quality_model.joblib"
DECK_QUALITY_MODEL_META_PATH = REPO_ROOT / "data" / "models" / "deck_quality_model_meta.json"
MIN_FREQUENCY_FOR_DECK_QUALITY_TRAINING = 25

_deck_feature_ctx: dict = {}


def _deck_feature_context() -> dict:
    """Lazily built once per process and reused for every deck featurized,
    instead of reloading card_reference.csv/roles per row."""
    if not _deck_feature_ctx:
        from utils.data_loader import get_elixir_costs, get_card_roles

        roles_map = get_card_roles()
        card_ref = load_card_reference().drop_duplicates("card_name")
        _deck_feature_ctx["role_tags"] = sorted(roles_map.keys())
        _deck_feature_ctx["role_sets"] = {role: set(cards) for role, cards in roles_map.items()}
        _deck_feature_ctx["elixir_costs"] = get_elixir_costs()
        _deck_feature_ctx["evo_hero"] = {
            row["card_name"]: (bool(row["has_evolution"]), bool(row.get("has_hero", False)))
            for _, row in card_ref.iterrows()
        }
        # Sorted so index 0 matches archetype_label()'s own win_conditions[0]
        # pick on an already-sorted deck -- keeps this feature and the
        # strategy label it's meant to echo pointing at the same card.
        _deck_feature_ctx["win_conditions"] = sorted(roles_map.get("win_condition", []))
    return _deck_feature_ctx


def _deck_feature_vector(cards: list[str]) -> list[float]:
    ctx = _deck_feature_context()
    features = [float(sum(1 for c in cards if c in ctx["role_sets"].get(tag, ()))) for tag in ctx["role_tags"]]
    elixirs = [ctx["elixir_costs"].get(c, 0) for c in cards]
    features.append(sum(elixirs) / len(elixirs) if elixirs else 0.0)
    features.append(1.0 if any(ctx["evo_hero"].get(c, (False, False))[0] for c in cards) else 0.0)
    features.append(1.0 if any(ctx["evo_hero"].get(c, (False, False))[1] for c in cards) else 0.0)
    win_conditions = ctx["win_conditions"]
    wc_onehot = [0.0] * len(win_conditions)
    present = sorted(c for c in cards if c in win_conditions)
    if present:
        wc_onehot[win_conditions.index(present[0])] = 1.0
    features.extend(wc_onehot)
    return features


def _build_feature_matrix(deck_strings) -> np.ndarray:
    return np.array([_deck_feature_vector(str(d).split(";")) for d in deck_strings], dtype=np.float32)


def train_deck_quality_model(archetypes_df: pd.DataFrame):
    """Fits the Deck Quality Model on decks with
    frequency >= MIN_FREQUENCY_FOR_DECK_QUALITY_TRAINING (real, well-tested
    decks only -- training on the 1-25 game rows this model exists to help
    would just be fitting noise). Returns the fitted model (or None if there
    aren't enough well-tested decks yet), also persisted to
    DECK_QUALITY_MODEL_PATH so it doesn't need retraining to be reused."""
    import xgboost as xgb
    import joblib
    import json
    from datetime import datetime, timezone

    trainable = archetypes_df[archetypes_df["frequency"] >= MIN_FREQUENCY_FOR_DECK_QUALITY_TRAINING]
    if len(trainable) < 200:
        print(f"Only {len(trainable)} decks with frequency>={MIN_FREQUENCY_FOR_DECK_QUALITY_TRAINING} -- "
              "too few to train the deck quality model yet, skipping (will fill in as more battles are collected).")
        return None

    X = _build_feature_matrix(trainable["deck"])
    y = trainable["win_rate"].to_numpy(dtype=np.float64)
    weights = trainable["frequency"].to_numpy(dtype=np.float64)

    idx = np.arange(len(X))
    np.random.default_rng(42).shuffle(idx)
    split = int(len(idx) * 0.8)
    train_idx, test_idx = idx[:split], idx[split:]

    model = xgb.XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.1)
    model.fit(X[train_idx], y[train_idx], sample_weight=weights[train_idx])

    mae = float(np.mean(np.abs(model.predict(X[test_idx]) - y[test_idx]))) if len(test_idx) else None

    DECK_QUALITY_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, DECK_QUALITY_MODEL_PATH)
    with open(DECK_QUALITY_MODEL_META_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "n_train": int(len(train_idx)),
            "n_test": int(len(test_idx)),
            "mean_absolute_error_on_holdout": mae,
            "min_frequency_for_training": MIN_FREQUENCY_FOR_DECK_QUALITY_TRAINING,
            "feature_count": int(X.shape[1]),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "caveat": (
                "Predicts a deck's win rate from its CARD COMPOSITION (role-tag counts, elixir "
                "curve, primary win condition, evolution/hero presence), trained only on decks "
                f"with {MIN_FREQUENCY_FOR_DECK_QUALITY_TRAINING}+ real recorded games. Meant to "
                "give a reasonable estimate for decks with too few real games to trust on their "
                "own -- always shown alongside, never in place of, the real recorded win rate "
                "and game count."
            ),
        }, f, indent=2)
    mae_str = f"MAE={mae:.4f}" if mae is not None else "no holdout"
    print(f"Trained deck quality model on {len(train_idx)} well-tested decks ({len(test_idx)} held out, {mae_str}).")
    return model


def apply_deck_quality_model(model, df: pd.DataFrame) -> pd.DataFrame:
    """Adds an estimated_win_rate column to any deck table with a `deck`
    column (works on deck_archetypes_live.csv AND deck_matchups_live.csv --
    the model generalizes by composition, not by having been trained on that
    exact table). NaN when there's no trained model yet (too little data)."""
    df = df.copy()
    if model is None or df.empty:
        df["estimated_win_rate"] = np.nan
        return df
    df["estimated_win_rate"] = np.round(model.predict(_build_feature_matrix(df["deck"])).astype(float), 4)
    return df


def train_live_model(df: pd.DataFrame):
    import xgboost as xgb
    import joblib
    import json
    from datetime import datetime, timezone

    name_to_id, _ = get_card_match_id_map()
    known_cards = sorted(name_to_id.keys())
    card_index = {c: i for i, c in enumerate(known_cards)}

    team_lists = df["team_cards"].fillna("").astype(str).str.split(";")
    opp_lists = df["opponent_cards"].fillna("").astype(str).str.split(";")
    results = df["result"]

    X, y = [], []
    for team, opp, result in zip(team_lists, opp_lists, results):
        team = [c for c in team if c in card_index]
        opp = [c for c in opp if c in card_index]
        if len(team) != 8 or len(opp) != 8 or result not in ("Win", "Loss"):
            continue
        x = np.zeros(len(known_cards), dtype=np.int8)
        for c in team:
            x[card_index[c]] += 1
        for c in opp:
            x[card_index[c]] -= 1
        X.append(x)
        y.append(1 if result == "Win" else 0)

    if len(X) < 200:
        print(f"Only {len(X)} fully-known-deck battles usable for training -- too few, skipping model fit.")
        return

    X, y = np.array(X), np.array(y)
    split = int(len(X) * 0.8)
    model = xgb.XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.1, eval_metric="logloss")
    model.fit(X[:split], y[:split])
    acc = model.score(X[split:], y[split:])

    LIVE_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, LIVE_MODEL_PATH)
    with open(LIVE_MODEL_META_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "accuracy": acc,
            "n_train": int(split),
            "n_test": int(len(X) - split),
            "card_order": known_cards,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "caveat": (
                f"Trained on only {len(X)} live-collected battles -- an order of magnitude "
                "(or more) smaller than the 18.3M-match historical model. Treat this accuracy "
                "number as noisy/preliminary, not a real improvement over the historical model."
            ),
        }, f, indent=2)
    print(f"Trained live model on {len(X)} battles ({split} train / {len(X)-split} test). Accuracy: {acc:.3f}")
    print("(Small-sample result -- see the 'caveat' field in the saved meta file.)")


def main():
    df = load_collected()
    n_total = len(df)
    print(f"Collected dataset: {n_total} battles (all-time)")

    if "collected_at" in df.columns and n_total > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RETRAIN_WINDOW_DAYS)).isoformat()
        df = df[df["collected_at"].astype(str) >= cutoff]
    if len(df) > RETRAIN_MAX_ROWS:
        df = df.tail(RETRAIN_MAX_ROWS)

    n = len(df)
    if n_total > n:
        print(f"Retraining on {n} of {n_total} battles (last {RETRAIN_WINDOW_DAYS} days, "
              f"capped to the most recent {RETRAIN_MAX_ROWS:,} rows as a hard memory safety net)")

    if n < MIN_BATTLES_FOR_CARD_STATS:
        print(f"Below the {MIN_BATTLES_FOR_CARD_STATS}-battle threshold for even a rough card-stats view -- "
              f"nothing to recompute yet. Run scripts/crawl_battles.py to grow it, then re-run this.")
        return

    long = _long_form(df)
    long.attrs["my_crowns"] = pd.to_numeric(
        pd.concat([df.get("team_crowns"), df.get("opponent_crowns")], ignore_index=True), errors="coerce")
    long.attrs["opp_crowns"] = pd.to_numeric(
        pd.concat([df.get("opponent_crowns"), df.get("team_crowns")], ignore_index=True), errors="coerce")

    stats = build_card_stats(long)
    stats.to_csv(LIVE_CARD_STATS_PATH, index=False)
    print(f"Wrote {LIVE_CARD_STATS_PATH.name}: {len(stats)} cards with live win-rate data.")

    if n >= MIN_BATTLES_FOR_SYNERGY:
        synergy = build_card_synergy(long)
        synergy.to_csv(LIVE_SYNERGY_PATH, index=False)
        print(f"Wrote {LIVE_SYNERGY_PATH.name}: {len(synergy)} card pairs with live co-occurrence data.")

        archetypes = build_deck_archetypes(long)

        # Deck Quality Model: trained once here on the well-tested subset of
        # `archetypes`, then applied to it (and to deck_matchups below) so
        # every deck -- including the 1-25 game ones -- gets a composition-
        # based estimated_win_rate alongside its real record. See the model's
        # own docstring/caveat for what this is and isn't.
        deck_quality_model = train_deck_quality_model(archetypes)
        archetypes = apply_deck_quality_model(deck_quality_model, archetypes)
        archetypes.to_csv(LIVE_ARCHETYPES_PATH, index=False)
        print(f"Wrote {LIVE_ARCHETYPES_PATH.name}: {len(archetypes)} real decks seen 3+ times.")

        strategy_summary = build_deck_strategy_summary(archetypes)
        if len(strategy_summary) > 0:
            strategy_summary.to_csv(LIVE_DECK_STRATEGY_SUMMARY_PATH, index=False)
            print(f"Wrote {LIVE_DECK_STRATEGY_SUMMARY_PATH.name}: {len(strategy_summary)} real strategies "
                  f"(win condition + flavor), pooling all their decks' real games together.")

        archetypes_by_arena = build_deck_archetypes_by_arena(long)
        if len(archetypes_by_arena) > 0:
            archetypes_by_arena.to_csv(LIVE_ARCHETYPES_BY_ARENA_PATH, index=False)
            print(f"Wrote {LIVE_ARCHETYPES_BY_ARENA_PATH.name}: {len(archetypes_by_arena)} (arena, deck) rows.")

        deck_matchups = build_deck_matchups(long)
        if len(deck_matchups) > 0:
            deck_matchups = apply_deck_quality_model(deck_quality_model, deck_matchups)
            deck_matchups.to_csv(LIVE_DECK_MATCHUPS_PATH, index=False)
            print(f"Wrote {LIVE_DECK_MATCHUPS_PATH.name}: {len(deck_matchups)} (archetype, deck) real matchup rows.")

            strategy_matchups = build_strategy_matchups(deck_matchups)
            if len(strategy_matchups) > 0:
                strategy_matchups.to_csv(LIVE_STRATEGY_MATCHUPS_PATH, index=False)
                print(f"Wrote {LIVE_STRATEGY_MATCHUPS_PATH.name}: {len(strategy_matchups)} (vs_strategy, my_strategy) "
                      f"pooled rows -- real counters for a whole STRATEGY, not just one exact deck.")

        scorelines = build_deck_matchup_scorelines(long)
        if len(scorelines) > 0:
            scorelines.to_csv(LIVE_DECK_MATCHUP_SCORELINES_PATH, index=False)
            print(f"Wrote {LIVE_DECK_MATCHUP_SCORELINES_PATH.name}: {len(scorelines)} (archetype, deck, scoreline) rows.")
    else:
        print(f"Below the {MIN_BATTLES_FOR_SYNERGY}-battle threshold for synergy/archetypes -- skipping.")

    card_variant_usage = build_card_variant_usage(long)
    if len(card_variant_usage) > 0:
        card_variant_usage.to_csv(LIVE_CARD_VARIANT_USAGE_PATH, index=False)
        print(f"Wrote {LIVE_CARD_VARIANT_USAGE_PATH.name}: {len(card_variant_usage)} card/variant rows "
              f"(Regular/Evolved/Hero split) with real usage data.")
    else:
        print(f"Below the {MIN_BATTLES_FOR_EVO_USAGE}-battle threshold for card variant usage (counting only "
              f"battles collected since tracking was added) -- skipping. Will fill in as fresh battles are collected.")

    tower_troop_usage = build_tower_troop_usage(long)
    if len(tower_troop_usage) > 0:
        tower_troop_usage.to_csv(LIVE_TOWER_TROOP_USAGE_PATH, index=False)
        print(f"Wrote {LIVE_TOWER_TROOP_USAGE_PATH.name}: {len(tower_troop_usage)} tower troops with real usage data.")
    else:
        print(f"Below the {MIN_BATTLES_FOR_TOWER_TROOP}-battle threshold for tower troop usage (counting only "
              f"battles collected since tracking was added) -- skipping. Will fill in as fresh battles are collected.")

    elixir_leak_stats = build_elixir_leak_stats(long)
    if len(elixir_leak_stats) > 0:
        elixir_leak_stats.to_csv(LIVE_ELIXIR_LEAK_PATH, index=False)
        print(f"Wrote {LIVE_ELIXIR_LEAK_PATH.name}: {len(elixir_leak_stats)} archetypes with real elixir-leaked data.")
    else:
        print(f"Below the {MIN_BATTLES_FOR_TOWER_TROOP}-battle threshold for elixir-leak stats (counting only "
              f"battles collected since tracking was added) -- skipping. Will fill in as fresh battles are collected.")

    arena_usage = build_arena_card_usage(long)
    if len(arena_usage) > 0:
        arena_usage.to_csv(LIVE_ARENA_USAGE_PATH, index=False)
        print(f"Wrote {LIVE_ARENA_USAGE_PATH.name}: {len(arena_usage)} (arena, card) rows.")
    else:
        print("No battles with trophy data yet for the arena breakdown -- trophy capture was just added, "
              "so only newly-collected battles (not the existing backlog) have it. Will fill in over time.")

    if n < MIN_BATTLES_FOR_MODEL:
        print(f"Below the {MIN_BATTLES_FOR_MODEL}-battle threshold for retraining the win predictor "
              f"({n}/{MIN_BATTLES_FOR_MODEL}) -- skipping model fit for now.")
        return

    train_live_model(df)


if __name__ == "__main__":
    main()
