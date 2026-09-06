"""
Thin API-facing wrapper around utils.data_loader / utils.deck_analysis -- the
same modules the Streamlit app uses -- so the FastAPI backend and the
Streamlit app share one source of truth for card data instead of drifting
apart. Replaces an earlier version that re-parsed a separate, stale CSV
(clash_royale_master_stats_corrected.csv) with its own hardcoded
elixir/role/max-level tables.
"""
import json
import sys
from pathlib import Path
from functools import lru_cache

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.data_loader import (
    get_card_list, get_card_at_level, get_card_types, get_card_meta,
    load_card_reference, get_elixir_costs, CURRENT_LEVEL_CAP,
    get_evolution_abilities, get_hero_abilities, get_evolution_stat_bonus,
    api_level_to_csv_level as api_to_absolute,
)

LIVE_CARDS_JSON = REPO_ROOT / "scripts" / "live_cards_reference.json"
TOWER_TROOPS_JSON = REPO_ROOT / "scripts" / "tower_troops_reference.json"


def _load_live_catalog() -> list[dict]:
    with open(LIVE_CARDS_JSON, encoding="utf-8") as f:
        items = list(json.load(f)["items"])
    if TOWER_TROOPS_JSON.exists():
        with open(TOWER_TROOPS_JSON, encoding="utf-8") as f:
            items += json.load(f)["items"]
    return items

# Fallback only for the 4 Tower Troop cards, which aren't in the live
# /v1/cards response at all (see scripts/build_card_reference.py's
# MANUAL_OVERRIDES for the same exception).
RARITY_MAX_LEVEL_FALLBACK = {
    "Common": 16, "Rare": 14, "Epic": 11, "Legendary": 8, "Champion": 6,
}

# Special deck slots unlock by Arena (never lost once reached, hence keyed off
# best_trophies rather than current trophies) -- confirmed via the March 2026
# deck-slot rework: 1 Evolution slot at Arena 3 (800 trophies), 1 Hero/Champion
# slot at Arena 5 (1,300), 1 Wild slot (Evolution, Hero, or Champion) at
# Arena 10 (3,000).
SLOT_THRESHOLDS = {
    "evolution_slots": 800,
    "hero_slots": 1300,
    "wild_slots": 3000,
}


def get_unlocked_slots(best_trophies: int | None) -> dict:
    bt = best_trophies or 0
    return {slot: (1 if bt >= threshold else 0) for slot, threshold in SLOT_THRESHOLDS.items()}

# CSV card name -> live API name, same aliasing as scripts/build_card_reference.py
NAME_ALIASES = {
    "Archer": "Archers", "Bat": "Bats", "Barbarian": "Barbarians",
    "Elite Barbarian": "Elite Barbarians", "Guard": "Guards",
    "Minion": "Minions", "Skeleton": "Skeletons", "Spear Goblin": "Spear Goblins",
}

# live API name -> our CSV name (the reverse of NAME_ALIASES). A live player's
# deck/collection/battlelog reports these 8 cards with their real (plural) API
# names, which never match our card_reference.csv naming directly -- without
# this, image/stat/counter lookups for these cards silently fail whenever they
# come from real player data (they still work fine when picked from our own
# card lists, which already use the CSV names).
REVERSE_NAME_ALIASES = {v: k for k, v in NAME_ALIASES.items()}


def normalize_card_name(name: str) -> str:
    """Map a card name as reported by the live Clash Royale API to our internal
    (card_reference.csv) naming."""
    return REVERSE_NAME_ALIASES.get(name, name)

def _by_live_name(icon_key: str | None = None) -> dict[str, dict]:
    """live API name -> catalog entry (icon_key filters to entries that actually
    have that key in iconUrls, e.g. only cards with a real Hero art variant)."""
    items = _load_live_catalog()
    if icon_key is None:
        return {c["name"]: c for c in items}
    return {c["name"]: c for c in items if icon_key in c.get("iconUrls", {})}


@lru_cache(maxsize=1)
def _live_icon_urls() -> dict[str, str]:
    """card_name (our CSV naming) -> real card art URL, from the live API dump's
    iconUrls.medium field (api-assets.clashroyale.com -- the actual Supercell
    CDN; there is no "cdn.clashroyale.com", that domain doesn't resolve). Now
    includes the 4 Tower Troops too (sourced from tower_troops_reference.json,
    since they aren't in the regular /v1/cards catalog at all)."""
    by_name = _by_live_name("medium")
    result = {}
    for card_name in get_card_list():
        live_name = NAME_ALIASES.get(card_name, card_name)
        if live_name in by_name:
            result[card_name] = by_name[live_name]["iconUrls"]["medium"]
    return result


def get_card_image_url(name: str) -> str | None:
    return _live_icon_urls().get(name)


@lru_cache(maxsize=1)
def _live_evolution_icon_urls() -> dict[str, str]:
    """card_name -> real evolved-form art URL, from iconUrls.evolutionMedium --
    the classic Evolution system (chip-based, temporary in-battle ability)."""
    by_name = _by_live_name("evolutionMedium")
    result = {}
    for card_name in get_card_list():
        live_name = NAME_ALIASES.get(card_name, card_name)
        if live_name in by_name:
            result[card_name] = by_name[live_name]["iconUrls"]["evolutionMedium"]
    return result


def get_evolution_image_url(name: str) -> str | None:
    return _live_evolution_icon_urls().get(name)


@lru_cache(maxsize=1)
def _live_hero_icon_urls() -> dict[str, str]:
    """card_name -> real Hero-form art URL, from iconUrls.heroMedium -- a
    separate, newer permanent-upgrade system (distinct from classic
    Evolutions; see scripts/build_card_reference.py for how the two are told
    apart, since the live API's maxEvolutionLevel field is reused for both)."""
    by_name = _by_live_name("heroMedium")
    result = {}
    for card_name in get_card_list():
        live_name = NAME_ALIASES.get(card_name, card_name)
        if live_name in by_name:
            result[card_name] = by_name[live_name]["iconUrls"]["heroMedium"]
    return result


def get_hero_image_url(name: str) -> str | None:
    return _live_hero_icon_urls().get(name)


@lru_cache(maxsize=1)
def _live_max_levels() -> dict[str, int]:
    """card_name (our CSV naming) -> real maxLevel, from the live API dump."""
    by_name = _by_live_name()
    result = {}
    for card_name in get_card_list():
        live_name = NAME_ALIASES.get(card_name, card_name)
        if live_name in by_name:
            result[card_name] = by_name[live_name]["maxLevel"]
    return result


def get_max_level(card_name: str, rarity: str) -> int:
    live = _live_max_levels()
    if card_name in live:
        return live[card_name]
    return RARITY_MAX_LEVEL_FALLBACK.get(rarity, 14)


def absolute_to_relative(abs_level: int, max_level: int) -> int | None:
    rel = abs_level - (CURRENT_LEVEL_CAP - max_level)
    return rel if rel >= 1 else None


@lru_cache(maxsize=1)
def get_rarity_map() -> dict[str, str]:
    ref = load_card_reference()
    return dict(zip(ref["card_name"], ref["rarity"]))


@lru_cache(maxsize=1)
def get_evolution_hero_map() -> dict[str, tuple[bool, bool]]:
    """card_name -> (has_evolution, has_hero), from card_reference.csv. Used to
    disambiguate the battlelog's evolutionLevel field, which the live API
    reuses for both Evolution and Hero slot assignment. IMPORTANT (corrected
    2026-08-02): some cards -- confirmed via the live catalog's iconUrls,
    Knight/Musketeer/Wizard -- genuinely have BOTH an evolutionMedium and a
    heroMedium variant, i.e. has_evolution AND has_hero can both be True for
    the same card. An earlier version of this docstring wrongly claimed
    'never both' -- see split_evolution_hero_cards for how dual-capable cards
    get disambiguated per real match."""
    ref = load_card_reference()
    return {
        row["card_name"]: (bool(row["has_evolution"]), bool(row.get("has_hero", False)))
        for _, row in ref.iterrows()
    }


def split_evolution_hero_cards(cards: list[dict]) -> tuple[list[str], list[str], list[str]]:
    """Given a raw card list (each a dict with at least `name` and possibly
    `evolutionLevel`) -- either one side's battlelog `cards`, OR a player's
    `currentDeck` -- returns (evolved_names, hero_names, ambiguous_names):
    the real cards actively Evolution/Hero-slotted (not just owned -- see
    get_evolution_hero_map's docstring). Card names are normalized to our
    internal (card_reference.csv) naming before the has_evolution/has_hero
    lookup.

    CORRECTED 2026-08-06, important: for cards that are BOTH Evolution- and
    Hero-capable (Knight, Musketeer, Wizard, Valkyrie), evolutionLevel alone
    can't tell you which system was active, and Supercell's API has no
    second field that does either (confirmed by dumping the full raw card
    object for a dual-capable card -- there is exactly one shared
    evolutionLevel/maxEvolutionLevel pair, reused for both systems, nothing
    hero-specific). An earlier version of this function used the card's
    ARRAY POSITION to guess (index 0 = Evolution, index 1 = Hero), based on
    one compelling-looking real example. That was re-tested more rigorously
    on 2026-08-06 and DISPROVEN: pulling multiple real battles for the same
    player using the literal same 8-card deck showed the battlelog's card
    order is NOT stable between battles -- cards shuffle position freely
    while the real equipped deck doesn't change -- so position is noise, not
    a deck-slot signal. Guessing off it produced real, confirmed damage: the
    same real deck usage was sometimes classified as Evolution and sometimes
    as Hero purely because of where the card happened to land in that
    match's array, which fragmented one real deck into multiple fake
    "different" decks in downstream per-variant grouping (see
    battle_collector.get_player_deck_history).

    There is currently no reliable way to distinguish Evolution vs Hero for
    a dual-capable card from real match data alone. Rather than guess and
    call it certain, dual-capable cards with a truthy evolutionLevel go into
    `ambiguous_names` (real: this card WAS actively evolved-or-hero'd this
    match; unknown: which of the two systems). Single-capable cards are
    unaffected -- there's no ambiguity possible for those, since only one
    system applies, so they remain 100% reliably classified into
    evolved_names/hero_names as before."""
    evo_hero_map = get_evolution_hero_map()
    evolved, hero, ambiguous = [], [], []
    for c in cards:
        if not c.get("evolutionLevel"):
            continue
        name = normalize_card_name(c.get("name", ""))
        has_evolution, has_hero = evo_hero_map.get(name, (False, False))
        if has_evolution and has_hero:
            ambiguous.append(name)
        elif has_evolution:
            evolved.append(name)
        elif has_hero:
            hero.append(name)
    return evolved, hero, ambiguous


def get_all_cards() -> list[dict]:
    ref = load_card_reference().set_index("card_name")
    types = get_card_types()
    ranges = get_card_meta("Range")
    hit_speeds = get_card_meta("Hit Speed (sec)")
    evo_abilities = get_evolution_abilities()
    hero_abilities = get_hero_abilities()

    cards = []
    for name in get_card_list():
        row = ref.loc[name] if name in ref.index else None
        rarity = row["rarity"] if row is not None else "Common"
        elixir = int(row["elixir"]) if row is not None and pd.notna(row["elixir"]) else None
        max_level = get_max_level(name, rarity)
        rng = ranges.get(name)
        hit_speed = hit_speeds.get(name)
        evo_ability = evo_abilities.get(name, {})
        hero_ability = hero_abilities.get(name, {})
        cards.append({
            "name": name,
            "type": types.get(name, "Troop"),
            "rarity": rarity,
            "elixir_cost": elixir,
            "max_level": max_level,
            "card_id": int(row["match_id"]) if row is not None and pd.notna(row["match_id"]) else None,
            "image_url": get_card_image_url(name),
            "range": rng if pd.notna(rng) else None,
            "hit_speed": float(hit_speed) if pd.notna(hit_speed) else None,
            "has_evolution": bool(row["has_evolution"]) if row is not None else False,
            "evolution_tiers": int(row["evolution_tiers"]) if row is not None and pd.notna(row.get("evolution_tiers")) else 0,
            "evolution_name": row["evolution_name"] if row is not None and row.get("evolution_name") else None,
            "evolution_image_url": get_evolution_image_url(name),
            "evolution_ability_name": evo_ability.get("ability_name"),
            "evolution_ability_description": evo_ability.get("ability_description"),
            "evolution_confidence": evo_ability.get("confidence"),
            "has_hero": bool(row.get("has_hero", False)) if row is not None else False,
            "hero_tiers": int(row["hero_tiers"]) if row is not None and pd.notna(row.get("hero_tiers")) else 0,
            "hero_name": row["hero_name"] if row is not None and row.get("hero_name") else None,
            "hero_image_url": get_hero_image_url(name),
            "hero_ability_name": hero_ability.get("ability_name"),
            "hero_ability_description": hero_ability.get("ability_description"),
            "hero_confidence": hero_ability.get("confidence"),
        })
    return sorted(cards, key=lambda x: x["name"])


STAT_COLS = [
    "Hitpoints", "Damage", "DPS", "Crown Tower Damage", "Charge Damage",
    "Death Damage", "Shield Hitpoints", "Heal (per hit)", "Heal per Second",
    "Spawn Damage", "Jump Damage", "Area Damage", "Combo Damage", "Dash Damage",
]


def get_card_stats(name: str, evolved: bool = False) -> list[dict]:
    """evolved=True applies the confirmed flat HP bonus for the handful of
    evolutions that have one (see data/evolution_stat_bonus.csv) -- most
    evolutions are pure-ability with no stat change, so this is a no-op for
    everything else, and the ability text (not a stat delta) is what actually
    describes their effect."""
    rarity = get_rarity_map().get(name, "Common")
    max_level = get_max_level(name, rarity)
    hp_bonus = get_evolution_stat_bonus().get(name, 0.0) if evolved else 0.0

    rows = []
    for abs_level in range(1, 19):
        row = get_card_at_level(name, abs_level)
        if row is None:
            continue
        relative_level = absolute_to_relative(abs_level, max_level)
        if relative_level is None:
            # Below this card's real achievable floor (e.g. a Champion can
            # never actually be "absolute level 1" -- its lowest real level
            # is 11) -- the underlying stats CSV has a synthetic/extrapolated
            # row here anyway (built with a uniform 1-18 growth formula for
            # every card), so skip it rather than showing an impossible level.
            continue
        r = {
            "absolute_level": abs_level,
            "relative_level": relative_level,
        }
        for col in STAT_COLS:
            if col in row.index and pd.notna(row[col]):
                val = float(row[col])
                if col == "Hitpoints" and hp_bonus:
                    val = round(val * (1 + hp_bonus))
                r[col.lower().replace(" ", "_").replace("(", "").replace(")", "")] = val
        rows.append(r)
    return rows


def get_card_at_relative_level(name: str, relative_level: int) -> dict | None:
    rarity = get_rarity_map().get(name, "Common")
    max_level = get_max_level(name, rarity)
    abs_level = api_to_absolute(relative_level, max_level)
    row = get_card_at_level(name, abs_level)
    if row is None:
        return None
    return {
        "name": name,
        "relative_level": relative_level,
        "absolute_level": abs_level,
        "hitpoints": float(row["Hitpoints"]) if pd.notna(row.get("Hitpoints")) else None,
        "damage": float(row["Damage"]) if pd.notna(row.get("Damage")) else None,
        "dps": float(row["DPS"]) if pd.notna(row.get("DPS")) else None,
        "rarity": rarity,
        "image_url": get_card_image_url(name),
    }


def get_card_rankings(stat: str = "DPS", normalize_by_elixir: bool = False) -> list[dict]:
    elixir_costs = get_elixir_costs()
    results = []
    for name in get_card_list():
        row = get_card_at_level(name, 11)  # reference level, matches the Streamlit app's convention
        if row is None or stat not in row.index or pd.isna(row[stat]):
            continue
        val = float(row[stat])
        elixir = elixir_costs.get(name, 1)
        if normalize_by_elixir and elixir > 0:
            val = val / elixir
        results.append({
            "name": name,
            "value": round(val, 2),
            "elixir": elixir_costs.get(name),
            "image_url": get_card_image_url(name),
        })
    return sorted(results, key=lambda x: -x["value"])
