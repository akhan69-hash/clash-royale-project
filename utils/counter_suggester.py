import math

import pandas as pd
import numpy as np
from utils.data_loader import get_card_at_level, get_card_types
from utils.deck_analysis import ELIXIR_COSTS, CARD_ROLES, analyze_deck

# Roles a well-rounded deck should cover; used to seed counter-deck generation
# before filling remaining slots by raw counter score. "spell_big" represents
# the single most impactful spell slot to guarantee (tower-damage output) --
# the old generic "spell" tag was split into spell_small/spell_big/spell_utility.
CORE_ROLES = ["win_condition", "spell_big", "air_defense", "tank", "mini_tank"]

# Hard counters: card_name -> list of cards it counters well
HARD_COUNTERS = {
    "Zap":          ["Skeleton", "Goblins", "Bat", "Fire Spirit", "Electro Spirit", "Sparky", "Inferno Dragon", "Inferno Tower"],
    "The Log":      ["Skeleton", "Goblins", "Princess", "Dart Goblin", "Rascals"],  # ground-only spell -- can't hit Bat, it flies
    "Arrows":       ["Minion", "Bat", "Skeleton", "Goblins", "Witch", "Night Witch", "Rascals"],
    "Fireball":     ["Musketeer", "Three Musketeers", "Barbarian", "Wizard", "Witch", "Goblin Gang", "Rascals", "Skeleton Dragons"],
    "Poison":       ["Graveyard", "Goblin Barrel", "Three Musketeers", "Musketeer", "Rascals", "Skeleton Dragons"],
    "Lightning":    ["Inferno Tower", "Electro Giant", "Sparky", "Three Musketeers", "X-Bow"],
    "Rocket":       ["X-Bow", "Mortar", "Elixir Collector", "Three Musketeers"],
    "Tornado":      ["Hog Rider", "Battle Ram", "Goblin Giant", "Golem"],
    "Inferno Tower":["Giant", "Golem", "P.E.K.K.A", "Mega Knight", "Lava Hound", "Balloon"],
    "Inferno Dragon":["Giant", "Golem", "P.E.K.K.A", "Mega Knight", "Lava Hound"],
    "Tesla":        ["Hog Rider", "Royal Hogs", "Balloon"],
    "Cannon":       ["Hog Rider", "Royal Hogs", "Giant", "Goblin Drill"],
    "Mini P.E.K.K.A":["Hog Rider", "Giant", "Golem"],  # ground melee -- can't touch Balloon, it flies
    "Valkyrie":     ["Skeleton", "Goblins", "Barbarian", "Witch", "Night Witch", "Rascals"],  # ground melee splash -- can't hit Bat, it flies
    "Bowler":       ["Skeleton Army", "Barbarian", "Goblin Gang", "Royal Recruits", "Rascals"],
    "Executioner":  ["Skeleton Army", "Minion Horde", "Barbarian", "Night Witch", "Rascals"],
    "Musketeer":    ["Balloon", "Lava Hound", "Baby Dragon", "Minion Horde", "Ram Rider", "Ronin"],
    "Mega Minion":  ["Balloon", "Baby Dragon", "Giant", "P.E.K.K.A", "Skeleton Dragons"],
    "Electro Wizard":["Sparky", "Inferno Dragon", "Inferno Tower", "Lava Hound"],
    "Electro Dragon":["Sparky", "Skeleton Army", "Goblin Gang", "Minion Horde"],
    "Baby Dragon":  ["Skeleton Army", "Goblin Gang", "Barbarian", "Minion Horde", "Skeleton Dragons"],
    "Hunter":       ["Giant", "Golem", "Mega Knight", "P.E.K.K.A"],  # shotgun spread is ground-only -- can't hit Balloon, it flies
    "Knight":       ["Miner", "Goblin Barrel", "Princess", "Dart Goblin"],
    "Dark Prince":  ["Skeleton Army", "Goblin Gang", "Barbarian", "Royal Recruits"],
    "Ice Wizard":   ["Hog Rider", "Battle Ram", "Royal Hogs", "Giant"],
    "Fisherman":    ["Giant", "Golem", "Balloon", "Lava Hound"],
    "Mega Knight":  ["Skeleton Army", "Goblin Gang", "Barbarian", "Ram Rider"],  # ground-only attacks -- can't hit Minion Horde, it flies
    "P.E.K.K.A":    ["Ram Rider", "Hog Rider", "Royal Hogs"],
    "Barbarian Barrel": ["Rascals", "Goblin Gang"],
    "Ice Golem":    ["Skeleton Dragons", "Hog Rider"],
    "Skeleton Army":["Ram Rider", "Ronin", "Vines"],
    "Dart Goblin":  ["Ronin", "Balloon"],
    "Ronin":        ["P.E.K.K.A", "Mega Knight", "Boss Bandit", "Prince", "Dark Prince", "Golem"],
    "Vines":        ["Balloon", "Lava Hound", "Baby Dragon", "Minion Horde", "Flying Machine"],
}

SPELL_ROLES = ("spell_small", "spell_big", "spell_utility")

# Real swarm troops (many cheap bodies) -- there's no dedicated "swarm" tag in
# CARD_ROLES (the taxonomy tags swarm_CLEAR, i.e. what answers a swarm, not
# what a swarm troop IS), so this one stays a short curated list rather than
# derived, same as HARD_COUNTERS below. Everything else in WEAKNESS_COUNTERS
# is derived directly from CARD_ROLES so new cards don't need a manual edit
# here every time card_reference.csv's roles column is updated.
SWARM_TROOPS = ["Skeleton Army", "Minion Horde", "Goblin Gang", "Guard", "Royal Recruits", "Barbarian", "Elite Barbarian"]

# Weaknesses: type of deck -> list of exploiting cards
WEAKNESS_COUNTERS = {
    "no_air_defense": CARD_ROLES.get("flying", []),
    "no_spell":       CARD_ROLES.get("bait", []),
    "high_elixir":    ["Hog Rider", "Battle Ram", "Royal Hogs", "Goblin Barrel", "Miner", "X-Bow", "Mortar"],
    "no_tank_killer": CARD_ROLES.get("tank", []),
    "no_swarm_clear": SWARM_TROOPS,
    "building_heavy": ["Rocket", "Lightning", "Earthquake", "Goblin Drill", "Wall Breakers"],
    "low_hp_cards":   ["Fireball", "Rocket", "Lightning", "Poison"],
}


# Roles used to flavor an archetype label beyond just its win condition, e.g.
# "Hog Rider (building_targeted_only, cycle)" reads more usefully than just "Hog Rider".
ARCHETYPE_FLAVOR_ROLES = ("building_targeted_only", "bait", "spawner", "cycle")


def archetype_label(deck: list[str]) -> str:
    """Labels an 8-card deck by its primary win condition (+ flavor roles),
    e.g. 'Hog Rider (cycle)'. Shared by loss-pattern classification
    (utils/coaching.py) and real deck-vs-archetype matchup aggregation
    (scripts/retrain_from_collected.py's build_deck_matchups)."""
    win_conditions = [c for c in deck if c in CARD_ROLES.get("win_condition", [])]
    if not win_conditions:
        return "No clear win condition"
    primary = win_conditions[0]
    flavor = [role for role in ARCHETYPE_FLAVOR_ROLES if any(c in CARD_ROLES.get(role, []) for c in deck)]
    return primary if not flavor else f"{primary} ({', '.join(flavor)})"


def wilson_lower_bound(wins: int, n: int, z: float = 1.96) -> float:
    """95% Wilson-score lower bound on a real win rate -- ranks 'tested decks
    that beat this' by how MUCH real evidence backs the number, not the raw
    win rate alone. Without this, a deck that went 5-0 (a tiny, lucky sample)
    always outranks a deck that went 40-10 (a much more reliable 80%), which
    is exactly why the same handful of small-sample '100%' decks kept showing
    up for every opponent regardless of how different they actually were."""
    if n == 0:
        return 0.0
    phat = wins / n
    denom = 1 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)
    return (center - margin) / denom


def explain_deck_vs_opponent(
    deck_cards: list[str], opponent_cards: list[str], weaknesses: list[str] | None = None
) -> tuple[list[str], int]:
    """Real, specific reasoning for why `deck_cards` counters THIS opponent's
    actual 8 cards -- not just their archetype bucket. Cross-references the
    same curated HARD_COUNTERS/WEAKNESS_COUNTERS tables get_counter_cards
    already uses for the synthetic fallback, applied deck-wide instead of
    per-card. Also returns a relevance score (higher = more of this specific
    deck's cards actually answer something in this specific opponent's deck)
    so real tested decks that share an archetype bucket can be reranked by
    genuine relevance to the deck actually being faced, instead of all
    getting identical treatment just because their archetype label matches.

    Callers reranking many candidate decks against the SAME opponent (e.g.
    decks.py's /decks/counter, which calls this once per real tested deck)
    should compute detect_weaknesses(opponent_cards) once and pass it in --
    it never changes across candidates, and recomputing it per-candidate was
    the actual cause of a real ~20s slowdown (see _load_raw's docstring in
    utils/data_loader.py)."""
    if weaknesses is None:
        weaknesses = detect_weaknesses(opponent_cards)
    reasons = []
    score = 0
    for card in deck_cards:
        for opp_card in HARD_COUNTERS.get(card, []):
            if opp_card in opponent_cards:
                reasons.append(f"{card} counters {opp_card}")
                score += 2
        for weakness in weaknesses:
            if card in WEAKNESS_COUNTERS.get(weakness, []):
                label = weakness.replace("_", " ").replace("no ", "their lack of ")
                reasons.append(f"{card} exploits {label}")
                score += 3
    # Dedup while preserving order, cap at a readable handful.
    seen = set()
    deduped = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            deduped.append(r)
    return deduped[:4], score


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
    if not any(r in opp_roles for r in SPELL_ROLES):
        weaknesses.append("no_spell")
    # "no_tank_killer" means the opponent has no answer that specifically
    # melts tanks -- distinct from merely owning a tank themselves (that was
    # the previous, mislabeled check).
    if "tank_killer" not in opp_roles:
        weaknesses.append("no_tank_killer")
    if "swarm_clear" not in opp_roles:
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
