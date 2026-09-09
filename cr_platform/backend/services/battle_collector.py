"""
Persists real battles fetched through the Player Lookup page into a local,
append-only dataset (data/collected_battles.csv), so every player tag a user
looks up organically grows a fresh, current dataset alongside the (now
2.5+ year old) 2023 Kaggle match sample the rest of the Analytics/ML pipeline
was built on.

Honest limitation: the official API only returns ~25 recent battles per
player, so this grows slowly (tens of rows per lookup) -- it's a freshness
signal to blend in over time, not a replacement for the 18M-row historical
base. See scripts/rebuild_card_stats_from_collected.py for how it gets used.

Performance note (found 2026-07-31): this file has grown past 300k rows from
the background crawler. save_battles() used to re-read and re-parse the
ENTIRE file on every single call just to dedupe -- that's what was making
every /players/{tag}/battles request (Player Lookup, Coaching, the crawler
every 30s) take 5+ seconds, and it would only get slower as the file grows.
Fixed with a module-level in-memory cache (_load_cache): the full file is
read once per server process, then kept in sync incrementally as new rows
are saved, so every call after the first is O(new rows) instead of O(all
rows). If this file keeps growing by orders of magnitude, a real database
(SQLite) would be the next step -- flagged here, not built yet.
"""
import csv
import os
import sys
import threading
import time
from collections import Counter, deque
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.data_loader import get_elixir_costs  # noqa: E402

COLLECTED_PATH = REPO_ROOT / "data" / "collected_battles.csv"

# Same cutoff as scripts/retrain_from_collected.py's EVOLUTION_TRACKING_ADDED_AT
# -- battles collected before this were backfilled with blank evolution/hero
# columns by _migrate_schema, so they'd wrongly look like "never evolved" if
# counted. Keep these two constants in sync if either ever changes.
EVOLUTION_TRACKING_ADDED_AT = "2026-08-01T00:00:00+00:00"
# Matches retrain_from_collected.py's TOWER_TROOP_TRACKING_ADDED_AT -- real
# per-match King Tower Troop data only exists from this point on.
TOWER_TROOP_TRACKING_ADDED_AT = "2026-08-01T01:00:00+00:00"

FIELDNAMES = [
    "battle_time", "game_mode", "team_tag", "team_name", "team_cards",
    "team_crowns", "team_trophies", "team_avg_level", "opponent_tag", "opponent_name", "opponent_cards",
    "opponent_crowns", "opponent_trophies", "opponent_avg_level", "result", "collected_at",
    # Real per-match Evolution/Hero slot usage (added 2026-07-31) -- blank for
    # rows collected before this, backfilled by _migrate_schema like every
    # other column added after the initial ~325k-row backlog.
    "team_evolved_cards", "team_hero_cards", "opponent_evolved_cards", "opponent_hero_cards",
    # Real per-match King Tower Troop + elixir-leaked (added 2026-08-01) --
    # same blank-backfill-for-old-rows caveat as the Evolution/Hero columns.
    "team_tower_troop", "opponent_tower_troop", "team_elixir_leaked", "opponent_elixir_leaked",
    # Dual-capable cards (Knight/Musketeer/Wizard/Valkyrie) confirmed
    # actively evolved-or-hero'd but where which of the two can't be told
    # apart from real match data (added 2026-08-06, see
    # card_service.split_evolution_hero_cards's docstring for why) -- kept
    # as its own column rather than silently folded into team_evolved_cards,
    # since asserting a specific one of the two would be a guess.
    "team_ambiguous_cards", "opponent_ambiguous_cards",
]

# Real production incident (2026-08-28, part 5): capping the legacy
# in-memory cache (see MAX_DEDUP_KEYS/MAX_DECK_HISTORY_PER_PLAYER above)
# only bought modest headroom -- a live measurement showed production's row
# count would still cost 6-7GB+ minimum even with aggressive caps, because
# the per-row overhead of a Python dict-per-CSV-row cache is just too high
# in aggregate at this scale. The real fix (see supabase/schema.sql,
# scripts/migrate_to_supabase.py from earlier the same day): save_battles/
# get_collection_stats/get_player_deck_history below now write to and read
# from Postgres directly when SUPABASE_DB_URL is configured -- Postgres's
# own UNIQUE constraint (battles_dedup_key) replaces the Python `keys` set
# for dedup entirely (no in-memory cache needed for that at all), and
# per-player deck history becomes an indexed `WHERE team_tag = ...` query
# instead of holding every player's history in memory at once. Falls back
# to the legacy CSV+cache path when SUPABASE_DB_URL isn't set (e.g. local
# dev without a Postgres project configured) so nothing breaks without it.
ARRAY_COLUMNS = {
    "team_cards", "opponent_cards", "team_evolved_cards", "team_hero_cards",
    "opponent_evolved_cards", "opponent_hero_cards", "team_ambiguous_cards", "opponent_ambiguous_cards",
}
INT_COLUMNS = {"team_crowns", "team_trophies", "opponent_crowns", "opponent_trophies"}
FLOAT_COLUMNS = {"team_avg_level", "opponent_avg_level", "team_elixir_leaked", "opponent_elixir_leaked"}

_PG_INSERT_SQL = f"""
    INSERT INTO battles ({", ".join(FIELDNAMES)})
    VALUES %s
    ON CONFLICT ON CONSTRAINT battles_dedup_key DO NOTHING
    RETURNING *
"""


def _pg_row_to_csv_dict(returned_row: tuple) -> dict:
    """Converts one row RETURNING * from _PG_INSERT_SQL back into a
    FIELDNAMES-shaped dict ready for csv.DictWriter -- schema.sql's column
    order matches FIELDNAMES exactly except for its own leading `id` column,
    skipped here (values[1:])."""
    out = {}
    for col, v in zip(FIELDNAMES, returned_row[1:]):
        if col in ARRAY_COLUMNS:
            out[col] = ";".join(v) if v else ""
        elif v is None:
            out[col] = ""
        elif hasattr(v, "isoformat"):
            out[col] = v.isoformat()
        else:
            out[col] = str(v)
    return out


def _pg_url() -> str | None:
    return os.getenv("SUPABASE_DB_URL") or None


def _pg_connect():
    """None if Postgres isn't configured -- every caller below treats that
    as "fall back to the legacy CSV+in-memory-cache path," never an error."""
    url = _pg_url()
    if not url:
        return None
    import psycopg2
    return psycopg2.connect(url)


def _row_for_pg(row: dict) -> tuple:
    out = []
    for col in FIELDNAMES:
        v = row.get(col, "")
        if col in ARRAY_COLUMNS:
            out.append([c for c in v.split(";") if c] if v else [])
        elif col in INT_COLUMNS:
            out.append(int(v) if v not in (None, "") else None)
        elif col in FLOAT_COLUMNS:
            out.append(float(v) if v not in (None, "") else None)
        else:
            out.append(v or None)
    return tuple(out)

_cache: dict | None = None
# Real production incident (2026-08-23): _load_cache()'s old "if _cache is
# None: build it" check had no lock -- every one of FastAPI's thread-pool
# threads handling a concurrent request to a cache-dependent endpoint (deck
# history, collection stats, ...) right after a container restart would each
# independently see _cache as None and start its OWN full parse of the
# multi-hundred-MB collected_battles.csv at the same time. A single visitor
# is one slow-but-survivable load; a handful of concurrent requests (real
# traffic + retries) multiplied that memory cost N-over, which is what
# actually drove the process into swap and made the whole site unresponsive
# -- worse than, and a different mechanism from, the original slow-single-
# load concern this module's docstring already flagged. This lock makes the
# build genuinely happen once: the first thread in builds it, every other
# thread blocks until it's done and then just reads the finished _cache.
_cache_lock = threading.Lock()

# See search_players' docstring -- caps its worst-case (no-match) file scan
# by wall-clock time instead of letting it run to the end of an ever-growing
# file. Checked every _TIME_CHECK_INTERVAL rows so time.monotonic() itself
# isn't called often enough to matter.
SEARCH_TIME_BUDGET_S = 3.5  # bumped from 2.0 (2026-08-27) as the file has grown past 1.4GB
_TIME_CHECK_INTERVAL = 5000

# Real production incident (2026-08-28, part 4): _load_cache() builds
# by_team_tag as one dict entry per battle row per player -- with the file
# past 4.3M rows, that's the single largest cost in this cache by far (the
# dedup `keys` set and the players/opponents/decks sets are all bounded by
# CARDINALITY -- unique tags/decks -- not total row count, so they stay
# comparatively small; by_team_tag was the biggest single structure -- but
# a local measurement (tracemalloc, real data) after capping it alone still
# projected to ~8GB+ at production's actual row count, not enough headroom.
# The dedup `keys` set turned out to be the other major cost, and it's ALSO
# effectively O(total rows) (each (battle_time, team_tag, opponent_tag)
# triple is all-but-unique per real battle, not bounded by unique player
# count). Both are now capped -- see MAX_DEDUP_KEYS below for why aging out
# old dedup keys is provably safe, not just a memory/correctness tradeoff:
# the Clash Royale API only ever returns a player's ~25 MOST RECENT battles,
# so a dedup key from months ago can never be checked against a genuine
# duplicate again -- keeping it around forever was pure dead weight.
MAX_DECK_HISTORY_PER_PLAYER = 300
# Generous multiple of any realistic re-crawl overlap window (BATCH_SIZE=60
# players/cycle, every 30s -- even frequent re-crawls of the same handful of
# players stay far under this before their oldest-in-window key would need
# to survive a genuine re-check).
MAX_DEDUP_KEYS = 2_000_000


def _dedup_key(row: dict) -> tuple:
    return (row["battle_time"], row["team_tag"], row["opponent_tag"])


def _add_dedup_key(cache: dict, key: tuple) -> None:
    """Adds `key` to the bounded dedup structure (see MAX_DEDUP_KEYS above).
    `keys` (a set) is what every membership check (`key in cache["keys"]`)
    actually uses; `key_order` (a plain deque, no maxlen) records insertion
    order so the OLDEST key can be evicted from both when the cap is
    exceeded -- deque's own maxlen auto-eviction doesn't tell you what got
    dropped, which is needed here to also remove it from `keys`."""
    cache["keys"].add(key)
    cache["key_order"].append(key)
    if len(cache["key_order"]) > MAX_DEDUP_KEYS:
        cache["keys"].discard(cache["key_order"].popleft())


def _migrate_schema():
    """One-time migration when FIELDNAMES gains new columns (e.g. adding trophy
    capture on top of ~8,000 already-collected rows) -- backfills blank values
    for old rows rather than leaving a header/row mismatch that would break
    pandas.read_csv downstream. Cheap in the steady state: DictReader exposes
    fieldnames from just the header line, no row-scan needed unless a
    migration actually fires."""
    if not COLLECTED_PATH.exists():
        return
    with open(COLLECTED_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames == FIELDNAMES:
            return  # already current
        rows = list(reader)

    with open(COLLECTED_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})


def _deck_tuple(cards_field: str) -> tuple | None:
    cards = cards_field.split(";") if cards_field else []
    return tuple(sorted(cards)) if len(cards) == 8 else None


def _index_deck_history(by_team_tag: dict, row: dict) -> None:
    """Records one lightweight entry per real battle this specific player (as
    the looked-up/crawled 'team' side) played -- the raw material for 'My
    Decks' (get_player_deck_history): every real deck a player has actually
    used, not just their single currently-equipped one."""
    deck = _deck_tuple(row.get("team_cards", ""))
    if not deck:
        return
    # deque(maxlen=...) -- see MAX_DECK_HISTORY_PER_PLAYER above -- so a
    # prolific player's history can't grow unbounded; oldest entries are
    # dropped automatically as new ones are appended, both during the
    # initial full-file load and incrementally in save_battles().
    by_team_tag.setdefault(row["team_tag"], deque(maxlen=MAX_DECK_HISTORY_PER_PLAYER)).append({
        "deck": deck,
        "result": row.get("result", ""),
        "evolved": tuple(c for c in (row.get("team_evolved_cards") or "").split(";") if c),
        "hero": tuple(c for c in (row.get("team_hero_cards") or "").split(";") if c),
        "ambiguous": tuple(c for c in (row.get("team_ambiguous_cards") or "").split(";") if c),
        "collected_at": row.get("collected_at") or "",
        "tower_troop": row.get("team_tower_troop") or "",
    })


def _load_cache() -> dict:
    """Lazily loads the whole file ONCE per process into an in-memory
    summary (dedup keys, unique players/opponents/decks, earliest/latest
    timestamps, row count), then save_battles() keeps it in sync
    incrementally so this never re-scans the full file again.

    Double-checked locking around the actual build (see _cache_lock's
    comment): the fast, warm-cache path (the overwhelming majority of real
    calls) still never touches the lock at all, so this adds no real
    per-request overhead once loaded -- it only serializes the one-time
    build so concurrent requests can't each trigger their own full parse."""
    global _cache
    if _cache is not None:
        return _cache

    with _cache_lock:
        # Re-check: another thread may have finished the build while this
        # one was waiting for the lock.
        if _cache is not None:
            return _cache

        keys: set = set()
        key_order: deque = deque()
        players: set = set()
        opponents: set = set()
        decks: set = set()
        by_team_tag: dict = {}
        earliest = latest = None
        total = 0
        cache_build: dict = {"keys": keys, "key_order": key_order}

        if COLLECTED_PATH.exists():
            with open(COLLECTED_PATH, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    _add_dedup_key(cache_build, (row["battle_time"], row["team_tag"], row["opponent_tag"]))
                    players.add(row["team_tag"])
                    opponents.add(row["opponent_tag"])
                    team_deck = _deck_tuple(row.get("team_cards", ""))
                    if team_deck:
                        decks.add(team_deck)
                    opp_deck = _deck_tuple(row.get("opponent_cards", ""))
                    if opp_deck:
                        decks.add(opp_deck)
                    _index_deck_history(by_team_tag, row)
                    bt = row["battle_time"]
                    if bt:
                        if earliest is None or bt < earliest:
                            earliest = bt
                        if latest is None or bt > latest:
                            latest = bt
                    total += 1

        _cache = {
            "keys": keys, "key_order": key_order, "players": players, "opponents": opponents, "decks": decks,
            "by_team_tag": by_team_tag,
            "earliest": earliest, "latest": latest, "total": total,
        }
        return _cache


def save_battles(team_tag: str, battles: list[dict]) -> int:
    """battles: the same list of dicts players.py's /battles endpoint already
    builds (type, battle_time, result, your_deck, opponent_deck, etc). Returns
    the number of genuinely new rows appended (0 if all were duplicates).

    Real production incident (2026-08-28, part 5): this used to call
    _load_cache() unconditionally, up front, on every single call -- meaning
    the crawler's very first save_battles() after ANY restart re-triggered
    the full-file cold load immediately, independent of anything else in the
    app. See _save_battles_pg/_save_battles_legacy below: the Postgres path
    (used whenever SUPABASE_DB_URL is configured) never touches _load_cache()
    at all."""
    _migrate_schema()
    candidate_rows = []
    now = datetime.now(timezone.utc).isoformat()

    for b in battles:
        row = {
            "battle_time": b.get("battle_time", ""),
            "game_mode": b.get("type", ""),
            "team_tag": team_tag,
            # Real fix (2026-08-27) -- see players.py's get_battles: this is
            # the looked-up player's own real name, straight from the
            # battlelog's own team entry (free, no extra API call). Used to
            # always be written as "" here, which is why search_players()
            # could never find someone by name if they'd only ever been
            # looked up directly.
            "team_name": b.get("your_name") or "",
            "team_cards": ";".join(b.get("your_deck") or []),
            "team_crowns": (b.get("crowns") or "-").split("-")[0],
            "team_trophies": b.get("your_trophies") or "",
            "team_avg_level": b.get("your_avg_level") or "",
            "opponent_tag": (b.get("opponent_tag") or "").lstrip("#"),
            "opponent_name": b.get("opponent_name") or "",
            "opponent_cards": ";".join(b.get("opponent_deck") or []),
            "opponent_crowns": (b.get("crowns") or "-").split("-")[-1],
            "opponent_trophies": b.get("opponent_trophies") or "",
            "opponent_avg_level": b.get("opponent_avg_level") or "",
            "result": b.get("result", ""),
            "collected_at": now,
            "team_evolved_cards": ";".join(b.get("your_evolved") or []),
            "team_hero_cards": ";".join(b.get("your_hero") or []),
            "team_ambiguous_cards": ";".join(b.get("your_ambiguous") or []),
            "opponent_evolved_cards": ";".join(b.get("opponent_evolved") or []),
            "opponent_hero_cards": ";".join(b.get("opponent_hero") or []),
            "opponent_ambiguous_cards": ";".join(b.get("opponent_ambiguous") or []),
            "team_tower_troop": b.get("your_tower_troop") or "",
            "opponent_tower_troop": b.get("opponent_tower_troop") or "",
            "team_elixir_leaked": b.get("your_elixir_leaked") if b.get("your_elixir_leaked") is not None else "",
            "opponent_elixir_leaked": b.get("opponent_elixir_leaked") if b.get("opponent_elixir_leaked") is not None else "",
        }
        if row["team_cards"] and row["opponent_cards"]:
            candidate_rows.append(row)

    if not candidate_rows:
        return 0

    conn = _pg_connect()
    if conn is not None:
        accepted = _save_battles_pg(conn, candidate_rows)
    else:
        accepted = _save_battles_legacy(candidate_rows)

    if accepted:
        _append_csv(accepted)
    return len(accepted)


def _save_battles_pg(conn, candidate_rows: list[dict]) -> list[dict]:
    """Postgres-backed path (see the 2026-08-28 part 5 note above FIELDNAMES):
    a single batched INSERT ... ON CONFLICT DO NOTHING RETURNING * both
    performs the dedup check (Postgres's own UNIQUE constraint, not a Python
    set) and tells us exactly which rows were genuinely new -- no full-file
    load needed at all for this path."""
    from psycopg2.extras import execute_values

    try:
        with conn:
            with conn.cursor() as cur:
                execute_values(cur, _PG_INSERT_SQL, [_row_for_pg(r) for r in candidate_rows])
                returned = cur.fetchall()
        return [_pg_row_to_csv_dict(r) for r in returned]
    finally:
        conn.close()


def _save_battles_legacy(candidate_rows: list[dict]) -> list[dict]:
    """Fallback when SUPABASE_DB_URL isn't configured (e.g. local dev) --
    same in-memory-cache dedup this function always used before the
    Postgres path existed."""
    cache = _load_cache()
    accepted = []
    for row in candidate_rows:
        key = _dedup_key(row)
        if key in cache["keys"]:
            continue
        accepted.append(row)
        _add_dedup_key(cache, key)
        cache["players"].add(row["team_tag"])
        cache["opponents"].add(row["opponent_tag"])
        team_deck = _deck_tuple(row["team_cards"])
        if team_deck:
            cache["decks"].add(team_deck)
        opp_deck = _deck_tuple(row["opponent_cards"])
        if opp_deck:
            cache["decks"].add(opp_deck)
        _index_deck_history(cache["by_team_tag"], row)
        bt = row["battle_time"]
        if bt:
            if cache["earliest"] is None or bt < cache["earliest"]:
                cache["earliest"] = bt
            if cache["latest"] is None or bt > cache["latest"]:
                cache["latest"] = bt
        cache["total"] += 1
    return accepted


def _append_csv(rows: list[dict]) -> None:
    if not rows:
        return
    write_header = not COLLECTED_PATH.exists()
    COLLECTED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(COLLECTED_PATH, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)
    _update_lifetime_totals(rows)
    _append_archive(rows)


# Real regression found 2026-09-07 (user-reported): "My Decks" on Player/
# Coach used to show a real player's FULL deck history; after the 2026-09-06
# disk emergency pruned Postgres's battles table to a small rolling recent
# window (see prune_old_battles.py/rebuild_battles_table.py), any player not
# active in that exact window lost most of their real history -- because
# _pg_deck_history_records only ever looked at Postgres, which is now
# INTENTIONALLY bounded. That's the real tension the user flagged: keeping
# Supabase's disk usage in check should never come at the cost of real
# personal data like a player's own deck history.
#
# Real fix: a local SQLite mirror (this project's own "SQLite migration
# still overdue" note, now actually built) -- FULL history, a real index on
# team_tag, and zero Supabase disk quota impact since it lives entirely on
# the VM's own (currently 24GB-free) disk. Postgres keeps doing exactly what
# it's good at (fast recent-window aggregate queries, bounded on purpose);
# this is the separate "personal data" store for anything that genuinely
# needs a specific player's full real history regardless of age.
ARCHIVE_DB_PATH = REPO_ROOT / "data" / "battles_archive.db"
_archive_schema_ready = False


def _archive_connect():
    import sqlite3
    conn = sqlite3.connect(ARCHIVE_DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")  # lets reads proceed concurrently with the occasional write
    conn.execute("PRAGMA busy_timeout=30000")
    global _archive_schema_ready
    if not _archive_schema_ready:
        cols = ", ".join(f'"{c}" TEXT' for c in FIELDNAMES)
        conn.execute(f"CREATE TABLE IF NOT EXISTS battles ({cols})")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_archive_team_tag ON battles(team_tag)")
        # UNIQUE (not just an index) -- must match scripts/backfill_battles_archive.py's
        # own CREATE UNIQUE INDEX exactly (same name), since whichever of the
        # two runs first is what actually defines this index -- SQLite's
        # "IF NOT EXISTS" silently no-ops the second CREATE, uniqueness and
        # all, if the names don't produce compatible definitions.
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_archive_dedup ON battles(battle_time, team_tag, opponent_tag)")
        # Real fix (2026-09-08, "make my search engine stronger and faster"):
        # search_players() below used to only have _pg_search_players (fast,
        # but Postgres's `battles` table is now a deliberately pruned RECENT
        # WINDOW, see the tiered-storage comments elsewhere in this file) or
        # this file's own full-history-but-unindexed CSV stream as a fallback
        # (a real 41s worst case against production's size, per that
        # function's own docstring). This archive has the FULL history (every
        # accepted battle is dual-written here regardless of the Postgres
        # path, see _append_csv) but until now only had team_tag indexed --
        # opponent_tag and the two name columns (COLLATE NOCASE so a
        # case-insensitive prefix LIKE can actually use the index, matching
        # how every other comparison in this file already lowercases first)
        # were missing entirely, meaning a name search or opponent-tag search
        # here would ALSO be a full unindexed table scan. These four make
        # _sqlite_search_players below a real indexed query on the full
        # dataset instead of a tradeoff between speed and coverage.
        # Real production finding (2026-09-08): the first version of these
        # two name indexes covered team_name/opponent_name alone -- a real
        # index seek (confirmed via EXPLAIN QUERY PLAN), but the query also
        # needs to return team_tag/opponent_tag, which wasn't in the index,
        # so every matching row needed a SEPARATE random lookup back into
        # the base table. On this VM's actual disk I/O that measured 4-9s
        # per search (vs. sub-100ms locally) -- hundreds of individual random
        # reads add up fast on real (as opposed to locally-tested) storage.
        # Including the tag column in the index too makes it a COVERING
        # index -- the whole query is answered from the index alone, no
        # base-table lookups at all, matching how idx_archive_team_tag/
        # idx_archive_opponent_tag already behave for the tag-side tiers.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_archive_opponent_tag ON battles(opponent_tag)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_archive_team_name_nocase ON battles(team_name COLLATE NOCASE, team_tag)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_archive_opponent_name_nocase ON battles(opponent_name COLLATE NOCASE, opponent_tag)")
        conn.commit()
        _archive_schema_ready = True
    return conn


def _append_archive(rows: list[dict]) -> None:
    conn = _archive_connect()
    try:
        placeholders = ", ".join("?" for _ in FIELDNAMES)
        # OR IGNORE -- defense in depth against the unique dedup index above.
        # In the normal flow these rows are already the genuinely-accepted
        # ones (Postgres's own ON CONFLICT DO NOTHING already filtered candidate_rows
        # down before this is ever called), so this should rarely actually
        # trigger -- but a plain INSERT would raise and drop the whole batch
        # if it ever did, which OR IGNORE avoids.
        conn.executemany(
            f"INSERT OR IGNORE INTO battles ({', '.join(FIELDNAMES)}) VALUES ({placeholders})",
            [tuple(r.get(c, "") for c in FIELDNAMES) for r in rows],
        )
        conn.commit()
    finally:
        conn.close()


def _archive_deck_history_records(team_tag: str) -> list[dict]:
    """Same record shape/cap as _pg_deck_history_records, sourced from the
    local SQLite archive instead -- has the player's REAL FULL history
    (mirrors collected_battles.csv), not just whatever Postgres's bounded
    recent window happens to still contain."""
    conn = _archive_connect()
    try:
        cur = conn.execute(
            """SELECT team_cards, result, team_evolved_cards, team_hero_cards,
                      team_ambiguous_cards, collected_at, team_tower_troop
               FROM battles WHERE team_tag = ?
               ORDER BY collected_at DESC LIMIT ?""",
            (team_tag, MAX_DECK_HISTORY_PER_PLAYER),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    records = []
    for team_cards, result, evolved, hero, ambiguous, collected_at, tower_troop in rows:
        cards = [c for c in (team_cards or "").split(";") if c]
        deck = tuple(sorted(cards)) if len(cards) == 8 else None
        if not deck:
            continue
        records.append({
            "deck": deck,
            "result": result or "",
            "evolved": tuple(c for c in (evolved or "").split(";") if c),
            "hero": tuple(c for c in (hero or "").split(";") if c),
            "ambiguous": tuple(c for c in (ambiguous or "").split(";") if c),
            "collected_at": collected_at or "",
            "tower_troop": tower_troop or "",
        })
    return records


LIFETIME_TOTALS_PATH = REPO_ROOT / "data" / "lifetime_totals.json"
_lifetime_lock = threading.Lock()

# Real incident (2026-09-06): Postgres's disk quota turned out far tighter
# than the battles table's actual growth -- fixed by keeping only a small
# recent slice hot in Postgres (see scripts/rebuild_battles_table.py /
# prune_old_battles.py) while data/collected_battles.csv keeps the REAL full
# history (already true before this incident -- save_battles() always wrote
# both, this just makes Postgres's row count intentionally bounded instead
# of unboundedly growing). Once Postgres no longer holds everything, its own
# count(*) stops being an honest "how many battles has this app EVER
# collected" answer -- this tiny JSON file tracks that number directly,
# updated incrementally (O(1) per save, no full-file rescan -- the exact
# thing that caused this project's earlier OOM incidents) instead of ever
# re-deriving it from a full scan of either the CSV or Postgres.
def _read_lifetime_totals() -> dict:
    try:
        import json
        return json.loads(LIFETIME_TOTALS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {"total_battles": 0, "earliest": None, "latest": None}


def _update_lifetime_totals(rows: list[dict]) -> None:
    with _lifetime_lock:
        totals = _read_lifetime_totals()
        totals["total_battles"] = totals.get("total_battles", 0) + len(rows)
        for r in rows:
            bt = r.get("battle_time") or ""
            if bt:
                if not totals.get("earliest") or bt < totals["earliest"]:
                    totals["earliest"] = bt
                if not totals.get("latest") or bt > totals["latest"]:
                    totals["latest"] = bt
        import json
        LIFETIME_TOTALS_PATH.write_text(json.dumps(totals), encoding="utf-8")


def _escape_like(s: str) -> str:
    """Postgres's default LIKE escape char is backslash -- without this, a
    query containing a literal % or _ would be misinterpreted as a wildcard
    instead of matched literally."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _sqlite_search_players(q: str, limit: int) -> list[dict]:
    """Primary search path as of 2026-09-08 -- see search_players's docstring
    for why this now runs before _pg_search_players. Same rank tiers (0=name
    prefix, 1=tag prefix, 2=name substring, 3=tag substring) as both the
    Postgres and legacy-scan versions.

    Two SEPARATE queries (name tiers, tag tiers), not one combined UNION --
    a real, confirmed-via-EXPLAIN-QUERY-PLAN constraint forced this split.
    SQLite's LIKE case-sensitivity is controlled ONLY by the connection-wide
    `case_sensitive_like` pragma (a per-comparison `COLLATE NOCASE` clause
    only tells the query PLANNER it's safe to use a NOCASE index for range
    pruning -- it does NOT restore case-insensitive matching once the
    pragma is on, confirmed the hard way: turning the pragma on to unlock a
    real index seek for the BINARY-collated tag columns silently broke name
    matching too, since a mixed-case query no longer matched any name).
    team_tag/opponent_tag need the pragma ON to get a real range-seek
    (they're BINARY-collated with no NOCASE index, and every tag in this
    app -- both stored and the q_tag below -- is already normalized
    uppercase, so comparing case-sensitively loses nothing real); the two
    name columns need it OFF (their own COLLATE NOCASE + the NOCASE indexes
    from _archive_connect already gives them a real seek under the default
    pragma state, confirmed separately). One connection, one pragma value
    at a time -- so each pair of tiers runs as its own query, merged and
    re-ranked in Python.

    Deliberately NOT using an ESCAPE clause anywhere (unlike
    _pg_search_players) -- confirmed via EXPLAIN QUERY PLAN that ANY ESCAPE
    clause silently disables the LIKE-to-index-range optimization entirely,
    which defeats the entire point of adding these indexes. The tradeoff: a
    literal `%`/`_` typed into the search box acts as a wildcard instead of
    a literal character (Supercell tags never contain either, and it's rare
    in real display names) -- a real but minor and non-harmful loosening
    (a few extra loosely-matching results, never wrong/missing data), worth
    it for real index seeks on the common case."""
    conn = _archive_connect()
    try:
        q_lower, q_tag = q.lower(), q.lstrip("#").upper()
        name_prefix, tag_prefix = f"{q_lower}%", f"{q_tag}%"
        name_contains, tag_contains = f"%{q_lower}%", f"%{q_tag}%"
        pool = limit * 20

        # Rank tiers 0/1 (prefix) are real index seeks -- always run, always
        # fast. Tiers 2/3 (substring, `%x%`) can't use a B-tree index at all
        # (no FTS5/trigram table exists here yet) -- worst case (few or no
        # real substring matches anywhere in 6.3M+ rows) means scanning a
        # large chunk of the whole table with nothing to stop early on,
        # confirmed via direct timing (~1.4s) even though the LIMIT bounds
        # ROWS RETURNED, not rows CHECKED. Real fix: only pay for that scan
        # when the prefix tiers didn't already find enough on their own --
        # the overwhelmingly common case for search-as-you-type. A query
        # with truly no prefix match anywhere still hits the slow path, same
        # as the old CSV-streaming version's documented worst case, just
        # rarer now that prefix alone covers most real searches.
        name_prefix_sql = """
            SELECT tag, name, rnk FROM (
                SELECT team_tag AS tag, team_name AS name, 0 AS rnk FROM battles
                    WHERE team_name COLLATE NOCASE LIKE ? LIMIT ?)
            UNION ALL
            SELECT tag, name, rnk FROM (
                SELECT opponent_tag AS tag, opponent_name AS name, 0 AS rnk FROM battles
                    WHERE opponent_name COLLATE NOCASE LIKE ? LIMIT ?)
        """
        rows = list(conn.execute(name_prefix_sql, [name_prefix, pool, name_prefix, pool]).fetchall())

        # Tag tiers -- pragma ON for these, see the docstring above for why.
        conn.execute("PRAGMA case_sensitive_like = ON")
        tag_prefix_sql = """
            SELECT tag, name, rnk FROM (
                SELECT team_tag AS tag, team_name AS name, 1 AS rnk FROM battles
                    WHERE team_tag LIKE ? LIMIT ?)
            UNION ALL
            SELECT tag, name, rnk FROM (
                SELECT opponent_tag AS tag, opponent_name AS name, 1 AS rnk FROM battles
                    WHERE opponent_tag LIKE ? LIMIT ?)
        """
        rows += conn.execute(tag_prefix_sql, [tag_prefix, pool, tag_prefix, pool]).fetchall()

        if len({r[0] for r in rows if r[0]}) < limit:
            name_contains_sql = """
                SELECT tag, name, rnk FROM (
                    SELECT team_tag AS tag, team_name AS name, 2 AS rnk FROM battles
                        WHERE team_name COLLATE NOCASE LIKE ? LIMIT ?)
                UNION ALL
                SELECT tag, name, rnk FROM (
                    SELECT opponent_tag AS tag, opponent_name AS name, 2 AS rnk FROM battles
                        WHERE opponent_name COLLATE NOCASE LIKE ? LIMIT ?)
            """
            # Pragma is still ON from the tag-prefix pass above -- harmless
            # here too (COLLATE NOCASE on these still forces case-insensitive
            # matching regardless, same override behavior noted above).
            rows += conn.execute(name_contains_sql, [name_contains, pool, name_contains, pool]).fetchall()
            tag_contains_sql = """
                SELECT tag, name, rnk FROM (
                    SELECT team_tag AS tag, team_name AS name, 3 AS rnk FROM battles
                        WHERE team_tag LIKE ? LIMIT ?)
                UNION ALL
                SELECT tag, name, rnk FROM (
                    SELECT opponent_tag AS tag, opponent_name AS name, 3 AS rnk FROM battles
                        WHERE opponent_tag LIKE ? LIMIT ?)
            """
            rows += conn.execute(tag_contains_sql, [tag_contains, pool, tag_contains, pool]).fetchall()

        # A tag can surface with a blank name from one row (e.g. the
        # opponent-name field wasn't captured that battle) and a real name
        # from another, and/or at more than one rank tier across the two
        # passes above -- keep the best (lowest) rank and the first
        # non-blank name seen per tag, same real-data quirk
        # _pg_search_players's `max(name) FILTER`/`min(rnk)` handled in SQL,
        # done here in Python since this is now two result sets to merge.
        best_name: dict[str, str] = {}
        order: list[str] = []
        best_rank: dict[str, int] = {}
        for tag, name, rnk in rows:
            if not tag:
                continue
            if tag not in best_rank:
                order.append(tag)
                best_rank[tag] = rnk
            elif rnk < best_rank[tag]:
                best_rank[tag] = rnk
            if name and tag not in best_name:
                best_name[tag] = name
        order.sort(key=lambda t: (best_rank[t], t))
        return [{"tag": t, "name": best_name.get(t)} for t in order[:limit]]
    finally:
        conn.close()


def _pg_search_players(conn, q: str, limit: int) -> list[dict]:
    """Postgres-backed replacement for the legacy full-file streaming scan
    below -- same ranking (name prefix > tag prefix > name substring > tag
    substring, see _rank in the legacy path's docstring), as a real indexed
    query.

    Real production bug (2026-09-01): the first version of this wrapped the
    ranking logic in a CASE WHEN over a `candidates` CTE built from an
    unfiltered `WHERE tag <> ''` scan -- since the actual ILIKE conditions
    only appeared inside that CASE, not in candidates' own WHERE clause,
    Postgres couldn't push them down to use ANY trigram index (confirmed via
    EXPLAIN ANALYZE: two full sequential scans over 1M+ rows, ~12s). Also,
    team_tag/team_name had no trigram index at all yet -- added
    idx_battles_team_tag_trgm/idx_battles_team_name_trgm to match the
    opponent side (see supabase/schema.sql). Restructured into one UNION ALL
    per rank tier, each with the ILIKE condition directly in ITS OWN WHERE
    clause (and its own LIMIT, so a tier stops scanning once it has enough
    candidates) -- this is what actually lets the planner use the indexes."""
    q_lower = _escape_like(q.lower())
    q_tag = _escape_like(q.lstrip("#").upper())
    pool = limit * 20
    sql = """
        WITH candidates AS (
            (SELECT team_tag AS tag, team_name AS name, 0 AS rnk FROM battles
                WHERE team_name ILIKE %(name_prefix)s LIMIT %(pool)s)
            UNION ALL
            (SELECT opponent_tag, opponent_name, 0 FROM battles
                WHERE opponent_name ILIKE %(name_prefix)s LIMIT %(pool)s)
            UNION ALL
            (SELECT team_tag, team_name, 1 FROM battles
                WHERE team_tag ILIKE %(tag_prefix)s LIMIT %(pool)s)
            UNION ALL
            (SELECT opponent_tag, opponent_name, 1 FROM battles
                WHERE opponent_tag ILIKE %(tag_prefix)s LIMIT %(pool)s)
            UNION ALL
            (SELECT team_tag, team_name, 2 FROM battles
                WHERE team_name ILIKE %(name_contains)s LIMIT %(pool)s)
            UNION ALL
            (SELECT opponent_tag, opponent_name, 2 FROM battles
                WHERE opponent_name ILIKE %(name_contains)s LIMIT %(pool)s)
            UNION ALL
            (SELECT team_tag, team_name, 3 FROM battles
                WHERE team_tag ILIKE %(tag_contains)s LIMIT %(pool)s)
            UNION ALL
            (SELECT opponent_tag, opponent_name, 3 FROM battles
                WHERE opponent_tag ILIKE %(tag_contains)s LIMIT %(pool)s)
        )
        SELECT tag, max(name) FILTER (WHERE name IS NOT NULL AND name <> '') AS name, min(rnk) AS best_rank
        FROM candidates
        WHERE tag IS NOT NULL AND tag <> ''
        GROUP BY tag
        ORDER BY best_rank, tag
        LIMIT %(limit)s
    """
    params = {
        "name_prefix": q_lower + "%", "tag_prefix": q_tag + "%",
        "name_contains": "%" + q_lower + "%", "tag_contains": "%" + q_tag + "%",
        "pool": pool, "limit": limit,
    }
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
    finally:
        conn.close()
    return [{"tag": tag, "name": name} for tag, name, _rank in rows]


def search_players(query: str, limit: int = 8) -> list[dict]:
    """Look up a player by (partial) name or tag against everyone this app
    has ever seen -- real feedback (2026-08-21): "why not try to use search
    queries to help find the account if its already in the dataset, might
    help the player not to type the whole thing in." Matches on real name
    first (Supercell's battle log includes each opponent's real name
    alongside their tag; the looked-up player's own name is never captured,
    only their tag -- an honest coverage gap, not every real CR player is
    name-searchable), falling back to a plain tag substring match.

    Real incident (2026-08-21): a first version of this built a PERMANENT
    name->tags index at server-startup cache-load time, held in memory for
    the life of the process. That OOM-killed the production server within
    minutes of deploying -- its size scaled with the full collected-battles
    file (2.5M+ rows and growing), and production's real file is far larger
    than anything tested locally. This version instead streams the file
    fresh on every search call, bailing out the moment `limit` name matches
    are found -- slower per call (a real file read, not an in-memory
    lookup), but memory stays flat and bounded no matter how large the
    dataset grows, which is the property that actually matters after a
    production OOM. Revisit with a real bounded/on-disk index (e.g. SQLite)
    if this ever becomes a real latency problem, but not before then.

    Second real problem found the same day: a query with NO matches has to
    scan the entire file with nothing to bail out early on -- measured at
    41+ seconds against production's real dataset size, which is both a bad
    hang for the person typing and a thread tied up that long per request.
    SEARCH_TIME_BUDGET_S caps the scan by wall-clock time (checked every
    _TIME_CHECK_INTERVAL rows, not every row, so the check itself isn't
    the bottleneck) -- worst case now returns "no matches (yet)" quickly
    rather than blocking for however long the full file takes to read.

    Real feedback (2026-08-26): "remembering playertags and suggestions on
    the load... it is very weird right now." Root cause -- the original
    version returned the first `limit` matches found in FILE ORDER (whatever
    row happened to be scanned first), with no ranking at all: searching
    "NOB" could surface "Arnob" (a real but non-prefix substring match)
    ahead of "Nobin" (the obviously-better prefix match) purely because
    Arnob's row came first in the file. Fixed by collecting a wider
    candidate POOL (still bounded by SEARCH_TIME_BUDGET_S, so this doesn't
    reopen the OOM/latency risk above) and ranking real prefix matches
    (name or tag) ahead of real substring matches before slicing to `limit`
    -- same "prefix beats substring" idea utils/cardSearch.ts already uses
    for card search, applied here too.

    Real bug fixed 2026-08-27: "searched Cheeka_peeka multiple times using
    the tag 9UV9VLV8V, but when i try to search it up it does not show at
    all." This function used to only ever check `opponent_tag`/
    `opponent_name` -- exactly the "looked-up player's own name is never
    captured" gap the paragraph above already (honestly) flagged. Now that
    players.py's get_battles captures that real name into `team_name` (see
    save_battles), this checks BOTH sides of every row -- a player is
    findable by name whether they were looked up directly (team side) or
    just showed up as someone else's opponent (opponent side).

    Case sensitivity: already handled on both sides -- `q_lower`/`name_lower`
    compare lowercased strings, and tags are compared against `q_tag`
    (uppercased, matching how Supercell tags are always stored).

    RESOLVED 2026-08-28: the fix flagged above -- "a real fix needs a real
    index" -- went live via _pg_search_players.

    SUPERSEDED 2026-09-08 ("make my search engine stronger and faster"):
    that Postgres path has a real coverage gap now that the tiered-storage
    work (see this file's ARCHIVE_DB_PATH comments) turned Postgres's own
    `battles` table into a deliberately pruned RECENT-WINDOW-ONLY table --
    a player whose battles have aged out of that window became invisible to
    search even though their full history was sitting right there in the
    local SQLite archive the whole time. _sqlite_search_players is now tried
    FIRST: same rank-tiered indexed-query approach as _pg_search_players,
    against the archive's full, never-pruned history (every accepted battle
    is dual-written there regardless of the Postgres path -- see
    _append_csv), now that idx_archive_opponent_tag/team_name_nocase/
    opponent_name_nocase exist to actually back it with real indexes instead
    of a table scan. Postgres and the raw CSV stream stay as fallbacks, in
    that order, for the edge case where the archive file itself doesn't
    exist yet (e.g. a brand new environment before its first battle)."""
    q = query.strip()
    if len(q) < 2:
        return []

    if ARCHIVE_DB_PATH.exists():
        return _sqlite_search_players(q, limit)

    conn = _pg_connect()
    if conn is not None:
        return _pg_search_players(conn, q, limit)

    if not COLLECTED_PATH.exists():
        return []
    q_lower = q.lower()
    q_tag = q.lstrip("#").upper()
    # Wider than `limit` so there's real material to rank -- still bounded,
    # not "keep scanning until the file ends."
    POOL_SIZE = limit * 8
    candidates: list[tuple[int, dict]] = []  # (rank, hit) -- lower rank = better match
    seen: set = set()
    deadline = time.monotonic() + SEARCH_TIME_BUDGET_S

    def _rank(tag: str, name: str) -> int | None:
        name_lower = name.lower() if name else ""
        if name_lower.startswith(q_lower):
            return 0  # name prefix -- best match
        if tag.startswith(q_tag):
            return 1  # tag prefix
        if q_lower in name_lower:
            return 2  # name substring
        if q_tag in tag:
            return 3  # tag substring -- weakest real match
        return None

    with open(COLLECTED_PATH, encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if i % _TIME_CHECK_INTERVAL == 0 and time.monotonic() > deadline:
                break
            for tag_field, name_field in (("team_tag", "team_name"), ("opponent_tag", "opponent_name")):
                tag = row.get(tag_field, "")
                if not tag or tag in seen:
                    continue
                name = row.get(name_field, "")
                rank = _rank(tag, name)
                if rank is not None:
                    seen.add(tag)
                    candidates.append((rank, {"tag": tag, "name": name or None}))
            if len(candidates) >= POOL_SIZE:
                break

    candidates.sort(key=lambda c: c[0])
    return [hit for _, hit in candidates[:limit]]


def _pg_collection_stats(conn) -> dict:
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT count(*), count(DISTINCT team_tag), count(DISTINCT opponent_tag),
                           min(battle_time), max(battle_time)
                    FROM battles
                """)
                total, unique_players, unique_opponents, earliest, latest = cur.fetchone()
                cur.execute("""
                    SELECT count(*) FROM (
                        SELECT team_cards AS d FROM battles WHERE cardinality(team_cards) = 8
                        UNION
                        SELECT opponent_cards FROM battles WHERE cardinality(opponent_cards) = 8
                    ) t
                """)
                unique_decks = cur.fetchone()[0]
    finally:
        conn.close()
    return {
        "total_battles": total,
        "unique_players": unique_players,
        "unique_opponents": unique_opponents,
        "unique_decks_seen": unique_decks,
        "earliest": earliest.isoformat() if earliest else None,
        "latest": latest.isoformat() if latest else None,
    }


_collection_stats_cache: dict = {"value": None, "fetched_at": 0.0}
_COLLECTION_STATS_TTL = 60  # seconds

def get_collection_stats() -> dict:
    """Real production incident (2026-09-05/06): callers (routers/meta.py,
    routers/ml.py) used to call this fresh on EVERY request -- a genuinely
    expensive Postgres query (dedupes every real 8-card deck ever seen in
    the retained window). That's what turned "one somewhat heavy query"
    into hundreds of repeated failures once the database's disk filled up
    (every hit re-ran and re-failed it). A 60s TTL cache here, shared by
    every caller, stops that amplification without making the displayed
    totals meaningfully stale for what's just a dashboard summary."""
    now = time.monotonic()
    if _collection_stats_cache["value"] is None or now - _collection_stats_cache["fetched_at"] > _COLLECTION_STATS_TTL:
        _collection_stats_cache["value"] = _compute_collection_stats()
        _collection_stats_cache["fetched_at"] = now
    return _collection_stats_cache["value"]


def _compute_collection_stats() -> dict:
    lifetime = _read_lifetime_totals()

    conn = _pg_connect()
    if conn is not None:
        stats = _pg_collection_stats(conn)
    else:
        cache = _load_cache()
        stats = {
            "unique_players": len(cache["players"]),
            "unique_opponents": len(cache["opponents"]),
            # Every distinct exact 8-card deck seen at least once, either side
            # of any real battle -- the raw "how many unique decks has this
            # app ever seen" number. A much bigger, noisier count than
            # deck_archetypes_live.csv's "seen 3+ times" figure (that one
            # filters for decks reliable enough to trust a win rate on);
            # this one is just the full collection.
            "unique_decks_seen": len(cache["decks"]),
        }

    # total_battles/earliest/latest come from the lifetime tracker (the full
    # real history, see _update_lifetime_totals) rather than whatever Postgres
    # happens to currently retain -- Postgres only holds a bounded recent
    # slice on purpose (see scripts/rebuild_battles_table.py), so its own
    # count(*)/min/max would silently under-report "how many EVER collected"
    # once old rows are pruned. unique_players/unique_opponents/
    # unique_decks_seen stay scoped to whatever's actually retained (exact
    # all-time set-cardinality would mean holding millions of tags/decks in
    # memory forever -- the same OOM pattern already hit 4 times this project).
    stats["total_battles"] = lifetime.get("total_battles") or stats.get("total_battles", 0)
    stats["earliest"] = lifetime.get("earliest") or stats.get("earliest")
    stats["latest"] = lifetime.get("latest") or stats.get("latest")
    return stats


def _pg_deck_history_records(conn, team_tag: str) -> list[dict]:
    """Same record shape _index_deck_history builds from a CSV row, but
    queried directly from Postgres's indexed team_tag column instead of
    scanning/holding every player's history in memory at once. Capped at
    MAX_DECK_HISTORY_PER_PLAYER rows, same reasoning as the legacy cache's
    per-player deque cap."""
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT team_cards, result, team_evolved_cards, team_hero_cards,
                           team_ambiguous_cards, collected_at, team_tower_troop
                    FROM battles
                    WHERE team_tag = %s
                    ORDER BY collected_at DESC
                    LIMIT %s
                """, (team_tag, MAX_DECK_HISTORY_PER_PLAYER))
                rows = cur.fetchall()
    finally:
        conn.close()

    records = []
    for team_cards, result, evolved, hero, ambiguous, collected_at, tower_troop in rows:
        deck = tuple(sorted(team_cards)) if team_cards and len(team_cards) == 8 else None
        if not deck:
            continue
        records.append({
            "deck": deck,
            "result": result or "",
            "evolved": tuple(evolved or []),
            "hero": tuple(hero or []),
            "ambiguous": tuple(ambiguous or []),
            "collected_at": collected_at.isoformat() if collected_at else "",
            "tower_troop": tower_troop or "",
        })
    return records


def _deck_history_records(team_tag: str) -> list[dict]:
    # Personal per-player history -- always the local SQLite archive now
    # (real full history, see the big comment above ARCHIVE_DB_PATH), not
    # Postgres (intentionally bounded to a recent window for disk reasons)
    # or the legacy in-memory cache. Falls back to those only if the archive
    # genuinely has nothing yet for this player (e.g. a brand-new deploy
    # before the one-time backfill has run).
    records = _archive_deck_history_records(team_tag)
    if records:
        return records
    conn = _pg_connect()
    if conn is not None:
        return _pg_deck_history_records(conn, team_tag)
    cache = _load_cache()
    return cache["by_team_tag"].get(team_tag, [])


def get_player_deck_history(team_tag: str) -> list[dict]:
    """Every real, EXACT deck THIS specific player has actually used across
    every battle they've been looked up or crawled for (not just their
    single currently-equipped deck, and not capped at the live API's most
    recent 25 -- this covers their full collected history).

    CORRECTED 2026-08-06: "exact" now includes which of those 8 cards were
    actually Evolution/Hero-slotted, not just the 8 card names -- a deck
    played with Hero Knight and the same 8 cards played with Regular Knight
    are two different real decks now, each with its own real win rate,
    rather than being merged into one deck with a "typically evolved X% of
    the time" statistical overlay on top (the old approach; it correctly
    reported a majority tendency, but that's not the same as "this is what
    was actually used," which is what a personal deck history should show).
    Only battles collected since Evolution/Hero tracking was added
    (EVOLUTION_TRACKING_ADDED_AT) carry real per-match evolved/hero data --
    older battles are grouped into their own "variant not known" bucket
    (`variant_known: false`) rather than being guessed at or silently folded
    into a specific-variant bucket.

    CORRECTED AGAIN 2026-08-06: grouping additionally includes an
    `ambiguous` set (dual-capable cards -- Knight/Musketeer/Wizard/Valkyrie
    -- confirmed active but Evolution-vs-Hero undeterminable, see
    card_service.split_evolution_hero_cards). This was necessary after
    finding the previous version's positional Evolution/Hero guess for
    those 4 cards was unreliable (battlelog card order isn't stable between
    battles of the identical real deck) and was silently fragmenting one
    real deck into multiple fake "different" variant rows whenever the
    guess flip-flopped. Grouping on the honest ambiguous set instead means
    those battles now correctly collapse back into ONE real group again."""
    records = _deck_history_records(team_tag)
    if not records:
        return []

    elixir_costs = get_elixir_costs()
    grouped: dict[tuple, dict] = {}
    for r in records:
        is_tracked = r["collected_at"] >= EVOLUTION_TRACKING_ADDED_AT
        evolved_key = tuple(sorted(r["evolved"])) if is_tracked else None
        hero_key = tuple(sorted(r["hero"])) if is_tracked else None
        ambiguous_key = tuple(sorted(r["ambiguous"])) if is_tracked else None
        sig = (r["deck"], evolved_key, hero_key, ambiguous_key)
        g = grouped.setdefault(sig, {"wins": 0, "total": 0, "tower_troops": Counter(), "tower_troop_wins": Counter()})
        g["total"] += 1
        if r["result"] == "Win":
            g["wins"] += 1
        # Real per-match King Tower Troop (added 2026-08-01) -- tallied the
        # same way as evolved/hero above, so 'Your Decks' can show which
        # Tower Troop this exact deck has actually been played with most,
        # and that troop's own real win rate in this deck (not a guess).
        troop = r.get("tower_troop") or ""
        if troop and r["collected_at"] >= TOWER_TROOP_TRACKING_ADDED_AT:
            g["tower_troops"][troop] += 1
            if r["result"] == "Win":
                g["tower_troop_wins"][troop] += 1

    decks = []
    for (deck, evolved_key, hero_key, ambiguous_key), g in grouped.items():
        costs = [elixir_costs.get(c, 0) for c in deck]
        troop_counts = g["tower_troops"]
        typical_tower_troop = None
        tower_troop_rate_pct = None
        tower_troop_win_rate_pct = None
        tower_troop_games = 0
        if troop_counts:
            typical_tower_troop, tower_troop_games = troop_counts.most_common(1)[0]
            tower_troop_rate_pct = round(tower_troop_games / sum(troop_counts.values()) * 100, 1)
            tower_troop_win_rate_pct = round(g["tower_troop_wins"][typical_tower_troop] / tower_troop_games * 100, 1)
        decks.append({
            "cards": list(deck),
            "times_played": g["total"],
            "wins": g["wins"],
            "win_rate": round(g["wins"] / g["total"] * 100, 1),
            "avg_elixir": round(sum(costs) / len(costs), 1) if costs else None,
            "cycle_cost": sum(sorted(costs)[:4]) if len(costs) >= 4 else sum(costs),
            # Exact, not a guess -- every real battle in this group had
            # precisely these cards Evolution/Hero-slotted (or, if
            # variant_known is false, we genuinely don't know for these
            # older, pre-tracking battles). ambiguous_cards were confirmed
            # active but Evolution-vs-Hero genuinely can't be determined.
            "evolved_cards": list(evolved_key) if evolved_key else [],
            "hero_cards": list(hero_key) if hero_key else [],
            "ambiguous_cards": list(ambiguous_key) if ambiguous_key else [],
            "variant_known": evolved_key is not None,
            "typical_tower_troop": typical_tower_troop,
            "tower_troop_rate_pct": tower_troop_rate_pct,
            "tower_troop_win_rate_pct": tower_troop_win_rate_pct,
            "tower_troop_games": tower_troop_games or None,
        })
    decks.sort(key=lambda d: d["times_played"], reverse=True)
    return decks


def get_likely_variant_for_card(team_tag: str, card_name: str) -> dict | None:
    """For one of the 4 dual-capable cards (Knight/Musketeer/Wizard/Valkyrie),
    the owned-collection API gives no way to tell whether a player's shards
    went to the Evolution pool or the Hero pool (see players.py's
    owns_evolution_shards/owns_hero_unlock comment) -- a real Supercell API
    limitation, not something guessable from a single static field (an
    earlier attempt at guessing this from battlelog card position was
    disproven via real multi-battle testing, see split_evolution_hero_cards's
    docstring; this does NOT repeat that mistake).

    This instead uses real evidence already collected for a different
    purpose: get_player_deck_history's per-deck evolved_cards/hero_cards,
    built from this player's own actually-tracked battles. If `card_name`
    shows up as evolved in some tracked games and hero'd in others, report
    whichever is more common, with the real counts -- never a guess dressed
    up as certainty, and honestly returns None (not a fabricated 50/50) when
    there's no tracked evidence for this card at all yet.
    """
    evo_games = 0
    hero_games = 0
    for d in get_player_deck_history(team_tag):
        if not d["variant_known"]:
            continue
        # ambiguous_cards deliberately excluded from both tallies -- those
        # tracked games still can't tell Evolution from Hero for this card,
        # so they're neither evidence for one side nor the other.
        if card_name in d["evolved_cards"]:
            evo_games += d["times_played"]
        elif card_name in d["hero_cards"]:
            hero_games += d["times_played"]

    total = evo_games + hero_games
    if total == 0:
        return None
    if evo_games >= hero_games:
        return {"likely_variant": "evolution", "likely_variant_confidence": f"{evo_games} of {total} tracked games as Evolution"}
    return {"likely_variant": "hero", "likely_variant_confidence": f"{hero_games} of {total} tracked games as Hero"}
