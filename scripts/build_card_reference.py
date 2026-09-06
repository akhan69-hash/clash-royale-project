"""
One-time (rerunnable) seed script for data/card_reference.csv.

Merges the existing hardcoded ELIXIR_COSTS / CARD_ROLES dicts (utils/deck_analysis.py,
themselves now sourced from card_reference.csv -- see utils/data_loader.get_elixir_costs)
with scripts/live_cards_reference.json -- a snapshot of the OFFICIAL Clash Royale API's
/v1/cards response (fetched 2026-07-28 with a real developer API key) -- to produce a
single, hand-editable CSV covering every playable card. This replaced an earlier version
of this script that used the community-maintained royaleapi/cr-api-data snapshot, which
had gone stale (missing 3 champions, showing only 8 cards with evolutions when the real
game has since given nearly every card at least one evolution/hero tier).

IMPORTANT distinction (discovered 2026-07-29 via a real player's /v1/players/{tag}
response): the live API's maxEvolutionLevel field is reused for TWO different game
systems, only distinguishable by which icon key is actually present:
  - iconUrls.evolutionMedium -> a real, classic Evolution (chip-based, in-battle
    temporary ability, e.g. Knight's Shield).
  - iconUrls.heroMedium -> the newer, separate "Hero" upgrade system (a permanent
    unlock with its own Hero Ability, e.g. Hero Tombstone's "Regal Revival").
Treating every maxEvolutionLevel>=1 card as a classic Evolution (the original version
of this script) mislabels 11 cards that are actually Hero cards.

Cards not present in the live API response (Tower Troops -- a separate mechanic not
covered by the /cards endpoint) get their catalog data from
scripts/tower_troops_reference.json instead (sourced from a real player's supportCards
field, since /v1/cards doesn't return them at all).

Run once to bootstrap the file: python scripts/build_card_reference.py
Safe to rerun, but it will NOT preserve manual edits made directly to the CSV afterward
(e.g. hand-added notes) -- back up data/card_reference.csv first if you've hand-edited it.
Elixir/roles ARE preserved across reruns since they're read back from the current CSV
(via ELIXIR_COSTS/CARD_ROLES) rather than a separate hardcoded source.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import get_card_list
from utils.deck_analysis import ELIXIR_COSTS, CARD_ROLES

ROOT = Path(__file__).parent.parent
LIVE_CARDS_JSON = ROOT / "scripts" / "live_cards_reference.json"
TOWER_TROOPS_JSON = ROOT / "scripts" / "tower_troops_reference.json"
OUTPUT_CSV = ROOT / "data" / "card_reference.csv"

# stats-CSV name -> live API name, where they differ (mostly singular/plural)
NAME_ALIASES = {
    "Archer": "Archers",
    "Bat": "Bats",
    "Barbarian": "Barbarians",
    "Elite Barbarian": "Elite Barbarians",
    "Guard": "Guards",
    "Minion": "Minions",
    "Skeleton": "Skeletons",
    "Spear Goblin": "Spear Goblins",
}

# Sourced from tower_troops_reference.json rather than /v1/cards -- not deployable
# in a deck, so they never appear in the match dataset either.
TOWER_TROOPS = {"Tower Princess", "Cannoneer", "Dagger Duchess", "Royal Chef"}


def load_live_cards() -> dict:
    with open(LIVE_CARDS_JSON, encoding="utf-8") as f:
        items = json.load(f)["items"]
    result = {c["name"]: c for c in items}
    if TOWER_TROOPS_JSON.exists():
        with open(TOWER_TROOPS_JSON, encoding="utf-8") as f:
            tower_items = json.load(f)["items"]
        result.update({c["name"]: c for c in tower_items})
    return result


def build_role_map() -> dict:
    role_map: dict[str, list[str]] = {}
    for role, cards in CARD_ROLES.items():
        for card in cards:
            role_map.setdefault(card, []).append(role)
    return role_map


def main():
    card_list = get_card_list()
    live_cards = load_live_cards()
    role_map = build_role_map()

    rows = []
    for card_name in card_list:
        live_name = NAME_ALIASES.get(card_name, card_name)
        live_entry = live_cards.get(live_name)

        elixir = ELIXIR_COSTS.get(card_name, "")
        roles = ";".join(role_map.get(card_name, []))

        if live_entry:
            # Tower Troops' catalog id (159000xxx, from supportCards) is not a raw
            # match-dataset card id -- they're not deployable and never appear in a
            # match, so match_id must stay blank (this column means "usable for
            # match-data analytics", which is never true for these 4).
            match_id = "" if card_name in TOWER_TROOPS else live_entry["id"]
            rarity = live_entry["rarity"].capitalize()
            icon_keys = live_entry.get("iconUrls", {})
            tiers = live_entry.get("maxEvolutionLevel", 0)

            has_evolution = "evolutionMedium" in icon_keys
            has_hero = "heroMedium" in icon_keys
            evo_tiers = tiers if has_evolution else 0
            hero_tiers = tiers if has_hero else 0
            evolution_name = f"{card_name} (Evolved)" if has_evolution else ""
            hero_name = f"Hero {card_name}" if has_hero else ""

            if "elixirCost" in live_entry:
                elixir = live_entry["elixirCost"]
            notes = ("Tower Troop, sourced from a player's supportCards field -- "
                     "not in /v1/cards, not deployable, no match data") if card_name in TOWER_TROOPS else ""
        else:
            match_id = ""
            rarity = ""
            has_evolution = False
            has_hero = False
            evo_tiers = 0
            hero_tiers = 0
            evolution_name = ""
            hero_name = ""
            notes = "Not in the live /v1/cards response -- verify rarity/evolution manually"

        is_champion = rarity == "Champion"

        rows.append({
            "card_name": card_name,
            "match_id": match_id,
            "elixir": elixir,
            "rarity": rarity,
            "is_champion": is_champion,
            "has_evolution": has_evolution,
            "evolution_tiers": evo_tiers,
            "evolution_name": evolution_name,
            "has_hero": has_hero,
            "hero_tiers": hero_tiers,
            "hero_name": hero_name,
            "roles": roles,
            "notes": notes,
        })

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "card_name", "match_id", "elixir", "rarity", "is_champion",
            "has_evolution", "evolution_tiers", "evolution_name",
            "has_hero", "hero_tiers", "hero_name",
            "roles", "notes",
        ])
        writer.writeheader()
        writer.writerows(rows)

    n_matched = sum(1 for r in rows if r["match_id"])
    n_evo = sum(1 for r in rows if r["has_evolution"])
    n_hero = sum(1 for r in rows if r["has_hero"])
    n_champ = sum(1 for r in rows if r["is_champion"])
    print(f"Wrote {len(rows)} cards to {OUTPUT_CSV}")
    print(f"  {n_matched} have a match_id (usable for match-data analytics)")
    print(f"  {len(rows) - n_matched} have no match_id (stats-only, 'no match data yet')")
    print(f"  {n_evo} flagged has_evolution=True (real evolutionMedium art)")
    print(f"  {n_hero} flagged has_hero=True (real heroMedium art -- a different system)")
    print(f"  {n_champ} flagged as Champions")


if __name__ == "__main__":
    main()
