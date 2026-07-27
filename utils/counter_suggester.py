import pandas as pd
import numpy as np
from utils.data_loader import get_card_at_level, get_card_types
from utils.deck_analysis import ELIXIR_COSTS, CARD_ROLES, analyze_deck

# Roles a well-rounded deck should cover; used to seed counter-deck generation
# before filling remaining slots by raw counter score.
CORE_ROLES = ["win_condition", "spell", "air_defense", "tank", "mini_tank"]

# Hard counters: card_name -> list of cards it counters well
HARD_COUNTERS = {
    "Zap":          ["Skeleton", "Goblins", "Bat", "Fire Spirit", "Electro Spirit", "Sparky", "Inferno Dragon", "Inferno Tower"],
    "The Log":      ["Skeleton", "Goblins", "Bat", "Princess", "Dart Goblin", "Rascal Girl"],
    "Arrows":       ["Minion", "Bat", "Skeleton", "Goblins", "Witch", "Night Witch"],
    "Fireball":     ["Musketeer", "Three Musketeers", "Barbarian", "Wizard", "Witch", "Goblin Gang"],
    "Poison":       ["Graveyard", "Goblin Barrel", "Three Musketeers", "Musketeer"],
    "Lightning":    ["Inferno Tower", "Electro Giant", "Sparky", "Three Musketeers", "X-Bow"],
    "Rocket":       ["X-Bow", "Mortar", "Elixir Collector", "Three Musketeers"],
    "Tornado":      ["Hog Rider", "Battle Ram", "Goblin Giant", "Golem"],
    "Inferno Tower":["Giant", "Golem", "P.E.K.K.A", "Mega Knight", "Lava Hound", "Balloon"],
    "Inferno Dragon":["Giant", "Golem", "P.E.K.K.A", "Mega Knight", "Lava Hound"],
    "Tesla":        ["Hog Rider", "Royal Hogs", "Balloon"],
    "Cannon":       ["Hog Rider", "Royal Hogs", "Giant", "Goblin Drill"],
    "Mini P.E.K.K.A":["Balloon", "Hog Rider", "Giant", "Golem"],
    "Valkyrie":     ["Skeleton", "Goblins", "Bat", "Barbarian", "Witch", "Night Witch"],
    "Bowler":       ["Skeleton Army", "Barbarian", "Goblin Gang", "Royal Recruits"],
    "Executioner":  ["Skeleton Army", "Minion Horde", "Barbarian", "Night Witch"],
    "Musketeer":    ["Balloon", "Lava Hound", "Baby Dragon", "Minion Horde"],
    "Mega Minion":  ["Balloon", "Baby Dragon", "Giant", "P.E.K.K.A"],
    "Electro Wizard":["Sparky", "Inferno Dragon", "Inferno Tower", "Lava Hound"],
    "Electro Dragon":["Sparky", "Skeleton Army", "Goblin Gang", "Minion Horde"],
    "Baby Dragon":  ["Skeleton Army", "Goblin Gang", "Barbarian", "Minion Horde"],
    "Hunter":       ["Giant", "Golem", "Mega Knight", "P.E.K.K.A", "Balloon"],
    "Knight":       ["Miner", "Goblin Barrel", "Princess", "Dart Goblin"],
    "Dark Prince":  ["Skeleton Army", "Goblin Gang", "Barbarian", "Royal Recruits"],
    "Ice Wizard":   ["Hog Rider", "Battle Ram", "Royal Hogs", "Giant"],
    "Fisherman":    ["Giant", "Golem", "Balloon", "Lava Hound"],
    "Mega Knight":  ["Skeleton Army", "Goblin Gang", "Barbarian", "Minion Horde"],
}

# Weaknesses: type of deck -> list of exploiting cards
WEAKNESS_COUNTERS = {
    "no_air_defense": ["Balloon", "Lava Hound", "Inferno Dragon", "Baby Dragon", "Minion Horde", "Flying Machine"],
    "no_spell":       ["Goblin Barrel", "Skeleton Army", "Minion Horde", "Goblin Gang", "Graveyard"],
    "high_elixir":    ["Hog Rider", "Battle Ram", "Royal Hogs", "Goblin Barrel", "Miner", "X-Bow", "Mortar"],
    "no_tank_killer": ["Giant", "Golem", "P.E.K.K.A", "Mega Knight", "Goblin Giant"],
    "no_swarm_clear": ["Valkyrie", "Executioner", "Bowler", "Dark Prince", "Baby Dragon"],
    "building_heavy": ["Rocket", "Lightning", "Earthquake", "Goblin Drill", "Wall Breakers"],
    "low_hp_cards":   ["Fireball", "Rocket", "Lightning", "Poison"],
}


def detect_weaknesses(opponent_cards: list[str]) -> list[str]:
    """Detect weaknesses in an opponent's deck."""
    card_types = get_card_types()
    weaknesses = []

    opp_roles = set()
    for card in opponent_cards:
        for role, role_cards in CARD_ROLES.items():
            if card in role_cards:
                opp_roles.add(role)

    if "air_defense" not in opp_roles:
        weaknesses.append("no_air_defense")
    if "spell" not in opp_roles:
        weaknesses.append("no_spell")
    if "tank" not in opp_roles and "mini_tank" not in opp_roles:
        weaknesses.append("no_tank_killer")
    if "cycle" not in opp_roles:
        weaknesses.append("no_swarm_clear")

    opp_elixir = [ELIXIR_COSTS.get(c, 0) for c in opponent_cards if ELIXIR_COSTS.get(c, 0) > 0]
    if opp_elixir and np.mean(opp_elixir) >= 4.2:
        weaknesses.append("high_elixir")

    building_count = sum(1 for c in opponent_cards if card_types.get(c) == "Building")
    if building_count >= 2:
        weaknesses.append("building_heavy")

    return weaknesses


def get_counter_cards(
    opponent_cards: list[str],
    top_n: int = 12,
    card_levels: dict[str, int] | None = None,
    default_level: int = 11,
) -> pd.DataFrame:
    """Score all cards by how well they counter the opponent's deck.

    card_levels lets callers show HP/DPS at each card's real level (e.g. from a
    connected API collection) instead of assuming everyone's at level 11 --
    cards missing from card_levels fall back to default_level.
    """
    card_types = get_card_types()
    card_levels = card_levels or {}
    scores = {}

    for counter_card, countered_list in HARD_COUNTERS.items():
        for opp_card in opponent_cards:
            if opp_card in countered_list:
                scores[counter_card] = scores.get(counter_card, 0) + 2

    weaknesses = detect_weaknesses(opponent_cards)
    for weakness in weaknesses:
        for exploit_card in WEAKNESS_COUNTERS.get(weakness, []):
            scores[exploit_card] = scores.get(exploit_card, 0) + 3

    for c in opponent_cards:
        scores.pop(c, None)

    rows = []
    for card, score in sorted(scores.items(), key=lambda x: -x[1])[:top_n]:
        elixir = ELIXIR_COSTS.get(card, "?")
        card_type = card_types.get(card, "Troop")
        level = card_levels.get(card, default_level)
        row_data = get_card_at_level(card, level)
        hp = int(row_data["Hitpoints"]) if row_data is not None and pd.notna(row_data.get("Hitpoints")) else "—"
        dps = round(float(row_data["DPS"]), 1) if row_data is not None and pd.notna(row_data.get("DPS")) else "—"

        reasons = []
        for opp_card in opponent_cards:
            if card in HARD_COUNTERS and opp_card in HARD_COUNTERS.get(card, []):
                reasons.append(f"Counters {opp_card}")
        for weakness in weaknesses:
            if card in WEAKNESS_COUNTERS.get(weakness, []):
                label = weakness.replace("_", " ").replace("no ", "Exploits lack of ").title()
                if label not in reasons:
                    reasons.append(label)

        rows.append({
            "Card": card,
            "Type": card_type,
            "Elixir": elixir,
            "Level": level,
            "HP": hp,
            "DPS": dps,
            "Counter Score": score,
            "Reasons": ", ".join(reasons[:2]) if reasons else "General value",
        })

    return pd.DataFrame(rows)


def generate_counter_deck(
    opponent_cards: list[str],
    card_levels: dict[str, int] | None = None,
    default_level: int = 11,
) -> dict:
    """Assemble a full 8-card deck to counter the given opponent deck.

    Greedily fills CORE_ROLES first (one card each, highest counter score per
    role) so the deck is actually playable -- a raw top-8-by-score list tends
    to double up on one role (e.g. five air answers, no win condition) -- then
    fills any remaining slots with the next highest-scoring cards regardless
    of role. card_levels (e.g. from a connected API collection) lets each
    card use its real owned level instead of assuming default_level for all.
    """
    pool = get_counter_cards(opponent_cards, top_n=40, card_levels=card_levels, default_level=default_level)
    if pool.empty:
        return {"deck": [], "analysis": {}, "picks": pd.DataFrame()}

    scores = dict(zip(pool["Card"], pool["Counter Score"]))
    deck: list[str] = []
    pick_reasons: dict[str, str] = {}

    for role in CORE_ROLES:
        role_cards = [c for c in CARD_ROLES.get(role, []) if c in scores and c not in deck]
        if role_cards:
            best = max(role_cards, key=lambda c: scores[c])
            deck.append(best)
            pick_reasons[best] = f"Fills {role.replace('_', ' ')}"
        if len(deck) >= 8:
            break

    for card in pool["Card"]:
        if len(deck) >= 8:
            break
        if card not in deck:
            deck.append(card)
            pick_reasons.setdefault(card, "Top counter score")

    levels = {c: (card_levels or {}).get(c, default_level) for c in deck}
    analysis = analyze_deck(deck, levels)

    picks_df = pool[pool["Card"].isin(deck)].copy()
    picks_df["Deck Role"] = picks_df["Card"].map(pick_reasons)
    picks_df = picks_df.set_index("Card").loc[deck].reset_index()

    return {"deck": deck, "levels": levels, "analysis": analysis, "picks": picks_df}
