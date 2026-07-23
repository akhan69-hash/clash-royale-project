import pandas as pd
import numpy as np
from utils.data_loader import get_card_at_level, get_card_types, load_playable_cards

# Elixir costs per card (from metadata — you can extend this dict as you add more)
# These are base elixir costs; load from metadata CSV if available
ELIXIR_COSTS = {
    "Tower Princess": 0, "Cannoneer": 0, "Dagger Duchess": 0, "Royal Chef": 0,
    "Knight": 3, "Archer": 3, "Goblin": 2, "Giant": 5, "Minion": 3,
    "Musketeer": 4, "Mini P.E.K.K.A": 4, "Fireball": 4, "Arrows": 3,
    "Goblin Hut": 5, "Goblin Cage": 4, "Goblin Brawler": 4, "Skeleton": 1,
    "Valkyrie": 4, "Bomber": 2, "Tombstone": 3, "Barbarian": 5,
    "Battle Ram": 4, "Mega Minion": 3, "Cannon": 3, "Wizard": 5,
    "Fire Spirit": 1, "Electro Spirit": 1, "Inferno Tower": 5, "Bomb Tower": 4,
    "Hog Rider": 4, "Bat": 2, "Flying Machine": 4, "Mortar": 4,
    "Rocket": 6, "Zap": 2, "P.E.K.K.A": 7, "Baby Dragon": 4,
    "Guard": 3, "Goblin Barrel": 3, "Balloon": 5, "Prince": 5,
    "Royal Recruits": 7, "Royal Hogs": 5, "Giant Skeleton": 6, "Ice Spirit": 1,
    "Ice Golem": 2, "Battle Healer": 4, "Freeze": 4, "Lightning": 6,
    "Giant Snowball": 2, "Dart Goblin": 3, "Goblin Gang": 3, "Skeleton Barrel": 3,
    "Goblin Giant": 6, "Rune Giant": 5, "Berserker": 2, "Barbarian Hut": 7,
    "Poison": 4, "Barbarian Barrel": 3, "Golem": 8, "Golemite": 0,
    "Elite Barbarian": 6, "Hunter": 4, "Zappies": 5, "Tesla": 4,
    "X-Bow": 6, "Furnace": 4, "Dagger Duchess": 0, "Princess": 3,
    "Miner": 3, "Sparky": 6, "Inferno Dragon": 4, "Electro Wizard": 4,
    "Ram Rider": 5, "Mega Knight": 7, "The Log": 2, "Royal Ghost": 3,
    "Electro Dragon": 5, "Wall Breakers": 2, "Ice Wizard": 3, "Lumberjack": 4,
    "Executioner": 5, "Night Witch": 4, "Elixir Golem": 4, "Goblin Drill": 4,
    "Rage": 2, "Royal Delivery": 3, "Goblin Curse": 4, "Cannon Cart": 5,
    "Fisherman": 3, "Mother Witch": 4, "Goblin Machine": 6, "Elixir Collector": 6,
    "Tornado": 3, "Void": 5, "Skeleton King": 4, "Golden Knight": 4,
    "Mighty Miner": 4, "Archer Queen": 4, "Boss Bandit": 4, "Monk": 5,
    "Little Prince": 4, "Goblinstein": 6, "Witch": 5, "Royal Giant": 6,
    "Dark Prince": 4, "Three Musketeers": 9, "Graveyard": 5,
    "Spirit Empress": 6, "Heal Spirit": 1, "Firecracker": 3, "Phoenix": 4,
    "Goblin Demolisher": 5, "Earthquake": 3, "Royal Chef": 0,
    "Lava Hound": 7, "Bowler": 6, "Bandit": 3, "Rascals": 5,
    "Magic Archer": 4, "Electro Giant": 7, "Suspicious Bush": 4,
}

# Card role tags for synergy analysis
CARD_ROLES = {
    "tank": ["Giant", "Golem", "P.E.K.K.A", "Mega Knight", "Lava Hound", "Royal Giant",
             "Giant Skeleton", "Goblin Giant", "Electro Giant", "Rune Giant"],
    "mini_tank": ["Knight", "Valkyrie", "Ice Golem", "Dark Prince", "Battle Healer",
                  "Bowler", "Goblin Machine"],
    "win_condition": ["Hog Rider", "Balloon", "Battle Ram", "Royal Hogs", "Goblin Drill",
                      "X-Bow", "Mortar", "Miner", "Goblin Giant", "Ram Rider", "Rocket"],
    "spell": ["Fireball", "Arrows", "Zap", "Rocket", "The Log", "Lightning", "Freeze",
              "Poison", "Giant Snowball", "Barbarian Barrel", "Earthquake", "Tornado",
              "Void", "Rage", "Royal Delivery", "Goblin Curse", "Goblin Barrel"],
    "air_defense": ["Musketeer", "Mega Minion", "Inferno Tower", "Tesla", "Inferno Dragon",
                    "Electro Dragon", "Electro Wizard", "Baby Dragon", "Minion",
                    "Flying Machine", "Hunter", "Zappies", "Dagger Duchess"],
    "cycle": ["Skeleton", "Goblin", "Bat", "Ice Spirit", "Electro Spirit", "Fire Spirit",
              "Zap", "Giant Snowball", "The Log", "Arrows", "Heal Spirit"],
    "spawner": ["Goblin Hut", "Barbarian Hut", "Tombstone", "Furnace", "Goblin Cage",
                "Night Witch", "Witch", "Skeleton King"],
}


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
