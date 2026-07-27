import pandas as pd
import numpy as np
from utils.data_loader import (
    get_card_at_level, get_card_types, load_playable_cards,
    get_elixir_costs, get_card_roles,
)

# Elixir costs and role tags now live in data/card_reference.csv (hand-editable --
# add a row there for a new card/evolution/champion instead of touching this file).
ELIXIR_COSTS = get_elixir_costs()
CARD_ROLES = get_card_roles()


def analyze_deck(cards: list[str], levels: dict[str, int]) -> dict:
    """
    Analyze a deck of 8 cards and return key metrics and warnings.
    cards: list of card names
    levels: dict of card_name -> level
    """
    if len(cards) == 0:
        return {}

    card_types = get_card_types()

    # Elixir cost
    elixir_costs = [ELIXIR_COSTS.get(c, 0) for c in cards]
    avg_elixir = np.mean([e for e in elixir_costs if e > 0])

    # Per-card stats at chosen level
    stats_rows = []
    for card in cards:
        level = levels.get(card, 11)
        row = get_card_at_level(card, level)
        if row is not None:
            stats_rows.append(row)

    # Role coverage
    roles_covered = set()
    for card in cards:
        for role, role_cards in CARD_ROLES.items():
            if card in role_cards:
                roles_covered.add(role)

    # Warnings
    warnings = []
    if "spell" not in roles_covered:
        warnings.append("⚠️ No spell in deck — you can't reset Inferno Tower/Dragon or clear swarms from range.")
    if "air_defense" not in roles_covered:
        warnings.append("⚠️ No air defense — you'll struggle against Balloon and Lava Hound decks.")
    if "win_condition" not in roles_covered:
        warnings.append("⚠️ No clear win condition — make sure you have a consistent way to pressure towers.")
    if avg_elixir > 4.5:
        warnings.append(f"⚠️ High average elixir ({avg_elixir:.1f}) — you may be outpaced in cycle decks.")
    if avg_elixir < 2.8:
        warnings.append(f"⚠️ Very low average elixir ({avg_elixir:.1f}) — make sure you have enough damage output.")
    if cards.count == 8 and len(set(card_types.get(c) for c in cards if card_types.get(c) == "Tower Troop")) > 0:
        warnings.append("⚠️ Tower Troops are not playable cards in a deck.")

    # Cycle time (simplified: avg elixir of 4 cheapest cards)
    sorted_elixir = sorted([e for e in elixir_costs if e > 0])
    cycle_cost = sum(sorted_elixir[:4]) if len(sorted_elixir) >= 4 else sum(sorted_elixir)

    # Aggregate stats
    total_hp = sum(float(r["Hitpoints"]) for r in stats_rows if pd.notna(r.get("Hitpoints")))
    total_dps = sum(float(r["DPS"]) for r in stats_rows if pd.notna(r.get("DPS")))

    return {
        "avg_elixir": round(avg_elixir, 2),
        "cycle_cost": cycle_cost,
        "total_hp": int(total_hp),
        "total_dps": round(total_dps, 1),
        "roles_covered": sorted(roles_covered),
        "roles_missing": sorted(set(CARD_ROLES.keys()) - roles_covered),
        "warnings": warnings,
        "elixir_costs": dict(zip(cards, elixir_costs)),
    }
