"""
One-time (rerunnable) seed script for data/card_reference.csv.

Merges the existing hardcoded ELIXIR_COSTS / CARD_ROLES dicts (utils/deck_analysis.py)
with the community-maintained royaleapi/cr-api-data card list (id, rarity, evolution
flags) to produce a single, hand-editable CSV covering every playable card.

Cards not present in cr-api-data (newer than its snapshot) get match_id left blank
and rarity/evolution filled in from manual research recorded in MANUAL_OVERRIDES below
-- these are exactly the rows a user should revisit when a new card/evolution/champion
ships and this script isn't rerun.

Run once to bootstrap the file: python scripts/build_card_reference.py
Safe to rerun, but it will NOT preserve manual edits made directly to the CSV afterward
-- back up data/card_reference.csv first if you've hand-edited it.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import get_card_list
from utils.deck_analysis import ELIXIR_COSTS, CARD_ROLES

ROOT = Path(__file__).parent.parent
CR_API_CARDS_JSON = ROOT / "scripts" / "cr_api_cards_reference.json"
OUTPUT_CSV = ROOT / "data" / "card_reference.csv"

# stats-CSV name -> cr-api-data name, where they differ (mostly singular/plural)
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

# Cards not present in cr-api-data (newer than its snapshot). Rarity confirmed via
# web research on 2026-07-27; evolution status confirmed false as of the same date
# (none of these had a shipped evolution at that time) -- re-verify if it's been a while.
MANUAL_OVERRIDES = {
    "Berserker":         {"rarity": "Common", "notes": "Added after cr-api-data snapshot"},
    "Boss Bandit":       {"rarity": "Champion", "notes": "Newer champion, added after cr-api-data snapshot"},
    "Goblinstein":       {"rarity": "Champion", "notes": "Newer champion, added after cr-api-data snapshot"},
    "Little Prince":     {"rarity": "Champion", "notes": "Newer champion, added after cr-api-data snapshot"},
    "Goblin Curse":      {"rarity": "Epic", "notes": "Added after cr-api-data snapshot"},
    "Goblin Demolisher":  {"rarity": "Rare", "notes": "Added after cr-api-data snapshot"},
    "Goblin Machine":    {"rarity": "Legendary", "notes": "Added after cr-api-data snapshot"},
    "Rune Giant":        {"rarity": "Epic", "notes": "Added after cr-api-data snapshot"},
    "Suspicious Bush":   {"rarity": "Rare", "notes": "Added after cr-api-data snapshot"},
    "Void":              {"rarity": "Epic", "notes": "Added after cr-api-data snapshot"},
    "Spirit Empress":    {"rarity": "Legendary", "notes": "Added after cr-api-data snapshot"},
    "Tower Princess":    {"rarity": "Common", "notes": "Tower Troop, added after cr-api-data snapshot"},
    "Cannoneer":         {"rarity": "Epic", "notes": "Tower Troop, added after cr-api-data snapshot"},
    "Dagger Duchess":    {"rarity": "Legendary", "notes": "Tower Troop, added after cr-api-data snapshot"},
    "Royal Chef":        {"rarity": "Legendary", "notes": "Tower Troop, added after cr-api-data snapshot"},
}


def load_cr_api_cards() -> dict:
    with open(CR_API_CARDS_JSON, encoding="utf-8") as f:
        items = json.load(f)
    return {c["name"]: c for c in items}


def build_role_map() -> dict:
    role_map: dict[str, list[str]] = {}
    for role, cards in CARD_ROLES.items():
        for card in cards:
            role_map.setdefault(card, []).append(role)
    return role_map


def main():
    card_list = get_card_list()
    cr_api_cards = load_cr_api_cards()
    role_map = build_role_map()

    rows = []
    for card_name in card_list:
        cr_name = NAME_ALIASES.get(card_name, card_name)
        cr_entry = cr_api_cards.get(cr_name)

        elixir = ELIXIR_COSTS.get(card_name, "")
        roles = ";".join(role_map.get(card_name, []))

        if cr_entry:
            match_id = cr_entry["id"]
            rarity = cr_entry["rarity"]
            evolved_key = cr_entry.get("evolved_spells_sc_key") or ""
            has_evolution = bool(evolved_key)
            evolution_name = f"{card_name} (Evolved)" if has_evolution else ""
            notes = ""
        else:
            override = MANUAL_OVERRIDES.get(card_name, {})
            match_id = ""
            rarity = override.get("rarity", "")
            has_evolution = False
            evolution_name = ""
            notes = override.get("notes", "No cr-api-data match -- verify rarity/evolution manually")

        is_champion = rarity == "Champion"

        rows.append({
            "card_name": card_name,
            "match_id": match_id,
            "elixir": elixir,
            "rarity": rarity,
            "is_champion": is_champion,
            "has_evolution": has_evolution,
            "evolution_name": evolution_name,
            "roles": roles,
            "notes": notes,
        })

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "card_name", "match_id", "elixir", "rarity", "is_champion",
            "has_evolution", "evolution_name", "roles", "notes",
        ])
        writer.writeheader()
        writer.writerows(rows)

    n_matched = sum(1 for r in rows if r["match_id"])
    n_evo = sum(1 for r in rows if r["has_evolution"])
    n_champ = sum(1 for r in rows if r["is_champion"])
    print(f"Wrote {len(rows)} cards to {OUTPUT_CSV}")
    print(f"  {n_matched} have a match_id (usable for match-data analytics)")
    print(f"  {len(rows) - n_matched} have no match_id (stats-only, 'no match data yet')")
    print(f"  {n_evo} flagged has_evolution=True (from cr-api-data, likely incomplete -- verify)")
    print(f"  {n_champ} flagged as Champions")


if __name__ == "__main__":
    main()
