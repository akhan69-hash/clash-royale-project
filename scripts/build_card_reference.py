"""
One-time (rerunnable) seed script for data/card_reference.csv.

Merges the existing hardcoded ELIXIR_COSTS / CARD_ROLES dicts (utils/deck_analysis.py,
themselves now sourced from card_reference.csv -- see utils/data_loader.get_elixir_costs)
with scripts/live_cards_reference.json -- a snapshot of the OFFICIAL Clash Royale API's
/v1/cards response (fetched 2026-07-28 with a real developer API key) -- to produce a
single, hand-editable CSV covering every playable card. This replaced an earlier version
of this script that used the community-maintained royaleapi/cr-api-data snapshot, which
had gone stale (missing 3 champions, showing only 8 cards with evolutions when the real
game has since given nearly every card at least one evolution tier).

Cards not present in the live API response (Tower Troops -- a separate mechanic not
covered by the /cards endpoint) get match_id left blank and rarity filled in from
MANUAL_OVERRIDES below.

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

# Tower Troops aren't returned by the /v1/cards endpoint (they're equipped to the
# King Tower, not the 8-card deck) -- rarity confirmed via web research 2026-07-27.
MANUAL_OVERRIDES = {
    "Tower Princess":    {"rarity": "Common", "notes": "Tower Troop, not in the /v1/cards endpoint"},
    "Cannoneer":         {"rarity": "Epic", "notes": "Tower Troop, not in the /v1/cards endpoint"},
    "Dagger Duchess":    {"rarity": "Legendary", "notes": "Tower Troop, not in the /v1/cards endpoint"},
    "Royal Chef":        {"rarity": "Legendary", "notes": "Tower Troop, not in the /v1/cards endpoint"},
}


def load_live_cards() -> dict:
    with open(LIVE_CARDS_JSON, encoding="utf-8") as f:
        items = json.load(f)["items"]
    return {c["name"]: c for c in items}


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
            match_id = live_entry["id"]
            rarity = live_entry["rarity"].capitalize()
            evo_tiers = live_entry.get("maxEvolutionLevel", 0)
            has_evolution = evo_tiers >= 1
            evolution_name = f"{card_name} (Evolved)" if has_evolution else ""
            # The live API's elixirCost is authoritative and current -- prefer it,
            # but some cards (e.g. Mirror) have no fixed cost (dynamic: +1 over the
            # copied card), so fall back to whatever's already in the CSV/ELIXIR_COSTS.
            if "elixirCost" in live_entry:
                elixir = live_entry["elixirCost"]
            notes = ""
        else:
            override = MANUAL_OVERRIDES.get(card_name, {})
            match_id = ""
            rarity = override.get("rarity", "")
            evo_tiers = 0
            has_evolution = False
            evolution_name = ""
            notes = override.get("notes", "Not in the live /v1/cards response -- verify rarity/evolution manually")

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
            "roles": roles,
            "notes": notes,
        })

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "card_name", "match_id", "elixir", "rarity", "is_champion",
            "has_evolution", "evolution_tiers", "evolution_name", "roles", "notes",
        ])
        writer.writeheader()
        writer.writerows(rows)

    n_matched = sum(1 for r in rows if r["match_id"])
    n_evo = sum(1 for r in rows if r["has_evolution"])
    n_champ = sum(1 for r in rows if r["is_champion"])
    print(f"Wrote {len(rows)} cards to {OUTPUT_CSV}")
    print(f"  {n_matched} have a match_id (usable for match-data analytics)")
    print(f"  {len(rows) - n_matched} have no match_id (stats-only, 'no match data yet')")
    print(f"  {n_evo} flagged has_evolution=True (from the live API's maxEvolutionLevel)")
    print(f"  {n_champ} flagged as Champions")


if __name__ == "__main__":
    main()
