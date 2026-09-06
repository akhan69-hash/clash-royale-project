"""
Scheduled (cron) new-card detector -- real gap found 2026-09-02: nothing in
this codebase ever polls the live /v1/cards endpoint; the app's whole card
catalog is built once from a static snapshot (scripts/live_cards_reference.json)
and only updated by a human manually rerunning build_card_reference.py. When
Supercell ships a genuinely new card, the app has no way to notice on its own.

Real feedback: "twenty four hour new card edition or feature edition checks
from API in game there is new cards coming hero ice wizard and minion giant
add that to the game like the cards and but leave their stats empty till API
finds it in the app itself and then get data for it from their end stats"

TWO real structural facts discovered while building this (verified against
the actual live API response and the codebase, not assumed):

  1. The live /v1/cards response has NO "type" (Troop/Spell/Building) field
     at all -- only name/id/maxLevel/maxEvolutionLevel/elixirCost/iconUrls/
     rarity (confirmed against scripts/live_cards_reference.json's real
     shape, and a fresh production API response). Type genuinely can't be
     determined from this endpoint; it's defaulted to "Troop" (the
     overwhelming majority case for any new card historically) and flagged
     in card_reference.csv's notes column for a human to correct if wrong.

  2. utils.data_loader.get_card_list() -- which is what actually determines
     whether a card shows up ANYWHERE in the app (CardPicker, Browse Cards,
     GET /api/cards) -- is driven by data/clash_royale_master_stats.csv (the
     per-level HP/DPS stats table), NOT data/card_reference.csv. Appending
     only to card_reference.csv (metadata: elixir/rarity/evolution flags)
     would leave a new card fully invisible in the app despite technically
     "existing" in that file. A minimal row (Type/Unit/Level only, every
     real stat column left genuinely blank -- not fabricated) is appended
     to the master stats CSV too, at Level 11 (the app's existing default-
     assumed level elsewhere, e.g. DeckBuilderKit's CardPicker level
     fallback), which is enough for the card to appear everywhere with real
     elixir/rarity/name/image and an honest "no stats yet" for HP/DPS --
     exactly the "leave their stats empty till API finds it" outcome asked
     for, not a half-fabricated one.

Both files are APPENDED to (never rewritten/reparsed) -- doesn't touch or
risk corrupting any existing row, and preserves any hand-edits already made
(card_reference.csv's own docstring warns a full rebuild does NOT preserve
those).

Safe/lightweight to run daily via cron (one API call + a CSV diff) -- see
deploy/'s crontab, scheduled right after the nightly retrain. Exits 0 if
nothing changed, 2 if new cards were found and written (the shell wrapper
uses this to decide whether a backend restart is actually needed -- both
files feed @lru_cache-decorated readers in utils/data_loader.py and
card_service.py that won't pick up an on-disk change without one).
"""
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
CARD_REFERENCE_CSV = ROOT / "data" / "card_reference.csv"
MASTER_STATS_CSV = ROOT / "data" / "clash_royale_master_stats.csv"
WHATS_NEXT_JSON = ROOT / "data" / "whats_next.json"

CR_API_BASE = "https://api.clashroyale.com/v1"
DEFAULT_LEVEL = 11  # matches the app's existing default-assumed level elsewhere (e.g. CardPicker's stepper fallback)

# Real name-format differences between our card_reference.csv naming and the
# live API's (see scripts/build_card_reference.py's own NAME_ALIASES) --
# checked here too so an existing card under an alias is never misdetected
# as "new."
NAME_ALIASES = {
    "Archer": "Archers", "Bat": "Bats", "Barbarian": "Barbarians",
    "Elite Barbarian": "Elite Barbarians", "Guard": "Guards",
    "Minion": "Minions", "Skeleton": "Skeletons", "Spear Goblin": "Spear Goblins",
}
REVERSE_ALIASES = {v: k for k, v in NAME_ALIASES.items()}


def fetch_live_cards() -> list[dict]:
    api_key = os.getenv("CR_API_KEY", "")
    if not api_key:
        print("CR_API_KEY not set -- skipping (see cr_platform/backend/.env).")
        sys.exit(0)
    resp = httpx.get(f"{CR_API_BASE}/cards", headers={"Authorization": f"Bearer {api_key}"}, timeout=15)
    resp.raise_for_status()
    return resp.json()["items"]


def existing_card_names() -> set[str]:
    with open(CARD_REFERENCE_CSV, encoding="utf-8") as f:
        return {row["card_name"] for row in csv.DictReader(f)}


def main():
    live_cards = fetch_live_cards()
    existing = existing_card_names()

    new_cards = [c for c in live_cards if REVERSE_ALIASES.get(c["name"], c["name"]) not in existing]

    if not new_cards:
        print("No new cards -- catalog unchanged.")
        sys.exit(0)

    names = ", ".join(c["name"] for c in new_cards)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Real, safe metadata into card_reference.csv -- elixir/rarity/
    #    evolution-hero flags/match id are all real fields the live API
    #    genuinely provides for a card the moment it's added, not guessed
    #    (same fields build_card_reference.py already extracts this exact
    #    way for every existing card).
    with open(CARD_REFERENCE_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for c in new_cards:
            icon_keys = c.get("iconUrls", {})
            has_evolution = "evolutionMedium" in icon_keys
            has_hero = "heroMedium" in icon_keys
            tiers = c.get("maxEvolutionLevel", 0)
            writer.writerow([
                c["name"], c["id"], c.get("elixirCost", ""), c["rarity"].capitalize(),
                c["rarity"].capitalize() == "Champion",
                has_evolution, tiers if has_evolution else 0,
                f"{c['name']} (Evolved)" if has_evolution else "",
                has_hero, tiers if has_hero else 0,
                f"Hero {c['name']}" if has_hero else "",
                "", "",  # roles, role_confidence -- genuinely not automatable, a human tags these later
                f"Auto-detected {today} from the live API -- verify Type/roles manually",
            ])

    # 2. Minimal row into the master stats CSV so the card actually shows up
    #    in the app at all (see fact #2 in the module docstring). Every real
    #    stat column stays blank on purpose -- pandas reads a blank CSV cell
    #    as NaN, the same "no data yet" state every existing consumer
    #    already handles gracefully for cards with sparse data.
    with open(MASTER_STATS_CSV, encoding="utf-8") as f:
        n_cols = len(f.readline().rstrip("\n").split(","))
    with open(MASTER_STATS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for c in new_cards:
            row = [""] * n_cols
            row[0] = "Troop"  # Type -- the live API has no type field at all (see
                               # fact #1 above); Troop is the overwhelmingly common
                               # case, flagged in card_reference.csv's notes above
                               # for a human to correct if this card isn't one.
            row[1] = c["name"]
            row[2] = DEFAULT_LEVEL
            writer.writerow(row)

    # 3. Real news entry -- clearly marked as auto-detected (this file is
    #    otherwise hand-researched, see its own top-level "note" field).
    whats_next = json.loads(WHATS_NEXT_JSON.read_text(encoding="utf-8"))
    whats_next["entries"].insert(0, {
        "title": f"New card{'s' if len(new_cards) > 1 else ''} detected: {names}",
        "category": "cards",
        "summary": (f"{names} just appeared in the live Clash Royale API -- added to Royale IQ with real "
                    f"elixir/rarity. Full combat stats and analytics will follow once enough real battles "
                    f"with {'it' if len(new_cards) == 1 else 'them'} are collected."),
        "source_url": "auto-detected from the live Clash Royale API",
    })
    WHATS_NEXT_JSON.write_text(json.dumps(whats_next, indent=2), encoding="utf-8")

    print(f"Added {len(new_cards)} new card(s): {names}")
    sys.exit(2)


if __name__ == "__main__":
    main()
