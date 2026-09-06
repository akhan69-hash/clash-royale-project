"""
Breadth-first battle-data crawler: starts from every player tag already known
(from data/collected_battles.csv), fetches each one's real recent battle log,
saves it via the same dedup logic the Player Lookup page uses, then adds any
new opponent tags it discovers to the frontier -- so each run expands outward
one layer (known players -> their opponents -> their opponents' opponents...).

Also expands via clan rosters: each newly-crawled player's clan (if any) gets
its full member list (up to 50 tags) pulled from the official /clans/{tag}
endpoint and added to the frontier too. This is a much denser source of real,
connected accounts than opponent-BFS alone -- one clan-members call yields up
to 50 real tags for the cost of 1 extra request, versus ~1 opponent tag per
battle-log row. (The Clash Royale API has no "friends list" endpoint --
Supercell doesn't expose that -- so clan rosters are the closest real
equivalent for "pull people this player actually plays with.") Each clan is
only expanded once (tracked in crawl_state.json's "crawled_clans"), so
players sharing a clan don't repeat the same clan-members fetch.

Safely re-runnable: data/crawl_state.json tracks which tags/clans have
already been crawled, so re-running this script continues expanding the
frontier instead of re-fetching players it already has. Run it again any
time to keep growing the dataset -- that's the intended usage ("keep
repeating it every time").

Once the frontier of never-seen tags runs dry for a given run, remaining
budget is spent RE-crawling players already crawled before (oldest-crawled
first, respecting RECRAWL_COOLDOWN_SECONDS so the same account isn't hit
needlessly often). This matters because the live battlelog endpoint only
ever returns a player's last ~25 battles -- their older battles silently
age out of that window over time. Re-fetching a known player later is the
only way to keep discovering the *rest* of their real decks (see
services/battle_collector.get_player_deck_history) instead of forever
being capped at whatever 25 battles they happened to have on the one
occasion they were first crawled.

Usage:
    python scripts/crawl_battles.py --api-key YOUR_KEY --max-new-players 100
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "cr_platform" / "backend"))

from services.battle_collector import save_battles, get_collection_stats, COLLECTED_PATH  # noqa: E402
from services.card_service import normalize_card_name, get_max_level, get_rarity_map, split_evolution_hero_cards  # noqa: E402
from utils.data_loader import api_level_to_csv_level as api_to_absolute  # noqa: E402

CR_API_BASE = "https://api.clashroyale.com/v1"
STATE_PATH = REPO_ROOT / "data" / "crawl_state.json"
REQUEST_DELAY = 0.35  # seconds between requests -- be polite to the API
RECRAWL_COOLDOWN_SECONDS = 3 * 3600  # don't re-fetch the same known player sooner than this


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seconds_since(ts: str | None) -> float:
    """Infinite for a tag never recorded (i.e. always eligible), so old
    crawl_state.json files without this field still work correctly."""
    if not ts:
        return float("inf")
    try:
        then = datetime.fromisoformat(ts)
    except ValueError:
        return float("inf")
    return (datetime.now(timezone.utc) - then).total_seconds()


def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH, encoding="utf-8") as f:
            state = json.load(f)
        state.setdefault("crawled_clans", [])
        state.setdefault("last_crawled_at", {})
        return state
    return {"crawled": [], "frontier": [], "crawled_clans": [], "last_crawled_at": {}}


def save_state(state: dict):
    """Atomic write -- this file is rewritten in full on every save (now
    multi-MB, millions of frontier entries), and a process killed mid-write
    (e.g. a forced restart) previously left a truncated, unparseable file
    with no way to tell which top-level key got cut off. Writing to a temp
    file first and renaming over the real path means readers only ever see
    either the fully-old or fully-new version, never a half-written one --
    same atomic-replace pattern already used by
    scripts/migrate_ambiguous_evo_hero.py for the same reason."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STATE_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp_path, STATE_PATH)


def seed_frontier_from_collected() -> set:
    """Every player tag already present in collected_battles.csv (as either
    the looked-up player or an opponent) is a valid crawl starting point."""
    if not COLLECTED_PATH.exists():
        return set()
    import csv
    tags = set()
    with open(COLLECTED_PATH, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["team_tag"]:
                tags.add(row["team_tag"])
            if row["opponent_tag"]:
                tags.add(row["opponent_tag"])
    return tags


def fetch_battles(client: httpx.Client, tag: str, api_key: str) -> list[dict] | None:
    tag = tag.lstrip("#").upper()
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = client.get(f"{CR_API_BASE}/players/%23{tag}/battlelog", headers=headers, timeout=10)
    except httpx.RequestError as e:
        print(f"  ! {tag}: request failed ({e})")
        return None

    if resp.status_code == 404:
        print(f"  ! {tag}: not found")
        return None
    if resp.status_code == 403:
        print(f"  ! {tag}: 403 (private profile or IP restriction)")
        return None
    if resp.status_code != 200:
        print(f"  ! {tag}: HTTP {resp.status_code}")
        return None
    return resp.json()


def fetch_player_clan_tag(client: httpx.Client, tag: str, api_key: str) -> str | None:
    tag = tag.lstrip("#").upper()
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = client.get(f"{CR_API_BASE}/players/%23{tag}", headers=headers, timeout=10)
    except httpx.RequestError:
        return None
    if resp.status_code != 200:
        return None
    clan = resp.json().get("clan")
    return (clan or {}).get("tag", "").lstrip("#") or None


def fetch_clan_member_tags(client: httpx.Client, clan_tag: str, api_key: str) -> set[str]:
    clan_tag = clan_tag.lstrip("#").upper()
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = client.get(f"{CR_API_BASE}/clans/%23{clan_tag}/members", headers=headers, timeout=10)
    except httpx.RequestError:
        return set()
    if resp.status_code != 200:
        return set()
    return {(m.get("tag") or "").lstrip("#") for m in resp.json().get("items", []) if m.get("tag")}


def _avg_absolute_level(raw_cards: list[dict], rarity_map: dict) -> float | None:
    """Average real absolute card level for one side of a battle -- a far
    more reliable signal of account maturity than current trophies, since
    trophies swing with season resets / deliberate trophy-dropping while
    unlocked card levels only ever go up. See players.py's identical helper;
    duplicated here since this script runs standalone without the FastAPI app."""
    levels = []
    for c in raw_cards:
        name = normalize_card_name(c.get("name", ""))
        max_lvl = get_max_level(name, rarity_map.get(name, "Common"))
        levels.append(api_to_absolute(c.get("level", 1), max_lvl))
    return round(sum(levels) / len(levels), 2) if levels else None


def _tower_troop_name(side: dict) -> str | None:
    """See players.py's identical helper -- duplicated here since this script
    runs standalone. supportCards[0] is the real King Tower Troop used in
    THIS specific battle (confirmed via direct API inspection 2026-08-01)."""
    support = side.get("supportCards") or []
    if not support:
        return None
    return normalize_card_name(support[0].get("name", "")) or None


def parse_battles(raw_battles: list[dict]) -> tuple[list[dict], set[str]]:
    """Mirror players.py's /battles response shape, and collect opponent tags."""
    results = []
    new_tags = set()
    rarity_map = get_rarity_map()
    for b in raw_battles[:25]:
        team = b.get("team", [{}])[0]
        opponent = b.get("opponent", [{}])[0]
        team_crowns = team.get("crowns", 0)
        opp_crowns = opponent.get("crowns", 0)
        opp_tag = (opponent.get("tag") or "").lstrip("#")
        your_evolved, your_hero, your_ambiguous = split_evolution_hero_cards(team.get("cards", []))
        opponent_evolved, opponent_hero, opponent_ambiguous = split_evolution_hero_cards(opponent.get("cards", []))
        results.append({
            "type": b.get("type", ""),
            "battle_time": b.get("battleTime", ""),
            "result": "Win" if team_crowns > opp_crowns else ("Loss" if team_crowns < opp_crowns else "Draw"),
            "crowns": f"{team_crowns}-{opp_crowns}",
            "your_trophies": team.get("startingTrophies"),
            "opponent_name": opponent.get("name"),
            "opponent_tag": opp_tag,
            "opponent_trophies": opponent.get("startingTrophies"),
            "your_deck": [normalize_card_name(c.get("name", "")) for c in team.get("cards", [])],
            "opponent_deck": [normalize_card_name(c.get("name", "")) for c in opponent.get("cards", [])],
            "your_avg_level": _avg_absolute_level(team.get("cards", []), rarity_map),
            "opponent_avg_level": _avg_absolute_level(opponent.get("cards", []), rarity_map),
            "your_evolved": your_evolved,
            "your_hero": your_hero,
            "your_ambiguous": your_ambiguous,
            "opponent_evolved": opponent_evolved,
            "opponent_hero": opponent_hero,
            "opponent_ambiguous": opponent_ambiguous,
            "your_tower_troop": _tower_troop_name(team),
            "opponent_tower_troop": _tower_troop_name(opponent),
            "your_elixir_leaked": team.get("elixirLeaked"),
            "opponent_elixir_leaked": opponent.get("elixirLeaked"),
        })
        if opp_tag:
            new_tags.add(opp_tag)
    return results, new_tags


def run_crawl(api_key: str, max_new_players: int = 100, verbose: bool = True) -> dict:
    """Runs one crawl batch (up to max_new_players new players) and returns a
    stats dict. Shared by the CLI below and the backend's auto-crawl loop
    (cr_platform/backend/services/auto_crawler.py) so both use the exact same
    logic and the same on-disk state file."""
    state = load_state()
    crawled = set(state["crawled"])
    crawled_clans = set(state["crawled_clans"])
    frontier = list(dict.fromkeys(state["frontier"]))  # preserve order, dedup
    last_crawled_at = dict(state.get("last_crawled_at", {}))

    if not frontier:
        frontier = sorted(seed_frontier_from_collected() - crawled)

    # Once there's nothing new left to discover this run, spend remaining
    # budget re-crawling already-known players -- oldest-crawled first --
    # to catch battles that happened since they were last fetched (see the
    # module docstring: the live battlelog only ever shows ~25 battles, so
    # this is the only way to keep growing a known player's full deck
    # history rather than being stuck with their first 25-battle snapshot).
    recrawl_queue = sorted(
        (t for t in crawled if _seconds_since(last_crawled_at.get(t)) >= RECRAWL_COOLDOWN_SECONDS),
        key=lambda t: last_crawled_at.get(t, ""),
    )

    if not frontier and not recrawl_queue:
        if verbose:
            print("No known player tags yet -- look up at least one real player in the app first,")
            print("or pass a seed tag: this script grows outward from data/collected_battles.csv.")
        return {"crawled_this_run": 0, "new_battles": 0, "frontier_remaining": 0}

    # Reserve a slice of every run's budget for re-crawling, even while the
    # frontier still has millions of never-seen tags queued (found 2026-08-06:
    # with a frontier this large, "only re-crawl once the frontier is empty"
    # meant re-crawling would never actually happen in practice -- new-player
    # discovery alone keeps replenishing the frontier faster than it drains).
    # A fixed ~25% reservation means known players' deck histories keep
    # deepening in parallel with new-player growth, instead of being starved
    # indefinitely by a backlog that never runs out.
    recrawl_budget = min(len(recrawl_queue), max(1, max_new_players // 4)) if recrawl_queue else 0

    if verbose:
        print(f"Starting crawl: {len(crawled)} already crawled, {len(frontier)} in frontier, "
              f"{len(recrawl_queue)} eligible for re-crawl (reserving {recrawl_budget} slots this run)")
        print(f"Cap for this run: {max_new_players} players\n")

    total_new_battles = 0
    crawled_this_run = 0
    new_players_this_run = 0
    recrawled_this_run = 0

    with httpx.Client() as client:
        while (frontier or recrawl_queue) and crawled_this_run < max_new_players:
            # Draw from recrawl_queue whenever there's reserved budget left
            # for it (and something to recrawl); otherwise take the next
            # never-seen tag from the frontier.
            if recrawl_queue and recrawled_this_run < recrawl_budget:
                tag = recrawl_queue.pop(0)
                is_recrawl = True
            elif frontier:
                tag = frontier.pop(0)
                if tag in crawled:
                    continue
                is_recrawl = False
            elif recrawl_queue:
                tag = recrawl_queue.pop(0)
                is_recrawl = True
            else:
                break

            raw = fetch_battles(client, tag, api_key)
            last_crawled_at[tag] = _now_iso()
            crawled.add(tag)
            crawled_this_run += 1
            if is_recrawl:
                recrawled_this_run += 1
            else:
                new_players_this_run += 1

            if raw:
                results, new_tags = parse_battles(raw)
                added = save_battles(tag, results)
                total_new_battles += added
                fresh = [t for t in new_tags if t not in crawled and t not in frontier]
                frontier.extend(fresh)
                if verbose:
                    tag_kind = "recrawl" if is_recrawl else "new"
                    print(f"[{crawled_this_run}/{max_new_players}] {tag} ({tag_kind}): "
                          f"{len(results)} battles ({added} new), +{len(fresh)} new tags discovered "
                          f"(frontier now {len(frontier)})")

            time.sleep(REQUEST_DELAY)

            # Clan expansion: a clan's member list yields up to 50 real tags
            # for one extra request -- much denser than opponent-BFS alone.
            # Each clan is only ever expanded once (see crawled_clans).
            clan_tag = fetch_player_clan_tag(client, tag, api_key)
            time.sleep(REQUEST_DELAY)
            if clan_tag and clan_tag not in crawled_clans:
                member_tags = fetch_clan_member_tags(client, clan_tag, api_key)
                crawled_clans.add(clan_tag)
                fresh_clan_tags = [t for t in member_tags if t not in crawled and t not in frontier]
                frontier.extend(fresh_clan_tags)
                if verbose and fresh_clan_tags:
                    print(f"    + clan {clan_tag}: {len(fresh_clan_tags)} new members added to frontier")
                time.sleep(REQUEST_DELAY)

    save_state({
        "crawled": sorted(crawled), "frontier": frontier, "crawled_clans": sorted(crawled_clans),
        "last_crawled_at": last_crawled_at,
    })

    stats = get_collection_stats()
    if verbose:
        print(f"\n{'='*60}")
        print(f"Crawled {crawled_this_run} players this run ({new_players_this_run} new, {recrawled_this_run} re-crawled).")
        print(f"Added {total_new_battles} new battles.")
        print(f"Dataset total: {stats['total_battles']} battles, "
              f"{stats['unique_players']} players, {stats['unique_opponents']} opponents seen.")
        print(f"Date range: {stats['earliest']} to {stats['latest']}")
        print(f"Frontier remaining: {len(frontier)} players (run again to keep expanding)")
        print(f"Clans expanded so far: {len(crawled_clans)}")

    return {
        "crawled_this_run": crawled_this_run,
        "new_players_this_run": new_players_this_run,
        "recrawled_this_run": recrawled_this_run,
        "new_battles": total_new_battles,
        "frontier_remaining": len(frontier),
        "clans_expanded": len(crawled_clans),
        "collection": stats,
    }


def main():
    parser = argparse.ArgumentParser(description="BFS crawler for real Clash Royale battle data")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--max-new-players", type=int, default=100,
                        help="Safety cap on how many new players to crawl this run")
    args = parser.parse_args()
    run_crawl(args.api_key, args.max_new_players)


if __name__ == "__main__":
    main()
