from functools import lru_cache

import pandas as pd
import numpy as np
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data" / "clash_royale_master_stats.csv"
CARD_REFERENCE_PATH = Path(__file__).parent.parent / "data" / "card_reference.csv"
CARD_EVOLUTIONS_PATH = Path(__file__).parent.parent / "data" / "card_evolutions.csv"
CARD_HEROES_PATH = Path(__file__).parent.parent / "data" / "card_heroes.csv"
EVOLUTION_STAT_BONUS_PATH = Path(__file__).parent.parent / "data" / "evolution_stat_bonus.csv"

# Cards that are sub-units or spawned troops (not directly playable)
SUB_UNITS = {
    "Ram (Ram Rider)", "Rider (Ram Rider)", "Rascal Boy", "Rascal Girl",
    "Phoenix Egg", "Lava Pups", "Elixir Golemite", "Elixir Blob",
    "Golemite", "Bush Goblin", "Cursed Hog", "Goblin Brawler",
    "Monster (Goblinstein)", "Guardian (Little Prince)", "Goblin Machine Rocket"
}

# The official API reports each card's level relative to that card's own
# maxLevel (e.g. a real response shows {"level": 1, "maxLevel": 5}), not an
# absolute number -- but our stats CSV's "Level" column IS absolute (verified
# empirically: real-world Lava Hound level-1 stats match our CSV's Level 9,
# not Level 1, since Legendaries' lowest real level has never been "1" -- our
# CSV extrapolates every card down to a synthetic Level 1 using the game's
# consistent ~10%/level growth formula). CURRENT_LEVEL_CAP is the one number
# that needs bumping whenever Supercell raises the level cap again (16 as of
# the Nov 2025 patch) -- everything else is derived from the API's own
# maxLevel per card, not a hardcoded rarity table.
CURRENT_LEVEL_CAP = 16


def api_level_to_csv_level(api_level: int, api_max_level: int) -> int:
    """Convert a player's card level as reported by the Clash Royale API
    (relative to that card's own maxLevel) into our stats CSV's absolute
    1-18 Level scale, for use with get_card_at_level()/analyze_deck()."""
    csv_level = api_level + (CURRENT_LEVEL_CAP - api_max_level)
    return max(1, min(18, csv_level))

@lru_cache(maxsize=1)
def _load_raw() -> pd.DataFrame:
    """Cached -- this file never changes while the server is running, but was
    being re-read from disk and re-parsed (CSV read + numeric coercion over
    ~30 columns) on EVERY call to get_card_types()/load_playable_cards()/etc,
    with no caching anywhere in this module. Usually masked by being called
    only once or twice per request; became an acute bug (2026-08-01) once
    /decks/counter started calling detect_weaknesses() ~170 times in a single
    request (once per candidate real deck) -- each one re-reading this CSV
    from scratch added up to 20+ seconds, blowing past the frontend's 15s
    axios timeout and silently failing to show any counter decks at all."""
    df = pd.read_csv(DATA_PATH, low_memory=False)
    # Replace NaN strings with actual NaN
    df.replace("NaN", np.nan, inplace=True)
    # Numeric columns
    numeric_cols = [
        "Level", "Hitpoints", "Damage", "DPS", "Crown Tower Damage",
        "Charge Damage", "Shield Hitpoints", "Death Damage", "Heal (per hit)",
        "Heal per Second", "Enchanted Damage", "Pellet Count", "Spawn Damage",
        "Jump Damage", "Shard Count", "Building Damage", "Dash Damage",
        "Zap Pack Damage", "Zap Pack DPS", "Hit Count",
        "Damage (2-4 targets)", "Crown Tower Damage (2-4 targets)",
        "Damage (5+ targets)", "Crown Tower Damage (5+ targets)",
        "Area Damage", "Combo Damage", "Air Form DPS", "Ground Form DPS"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_stats() -> pd.DataFrame:
    """Full stats table, all units and levels."""
    return _load_raw().copy()


def load_playable_cards() -> pd.DataFrame:
    """Only directly-playable cards (no sub-units), one row per card per level."""
    df = _load_raw()
    return df[~df["Unit"].isin(SUB_UNITS)].copy()


def get_card_list() -> list[str]:
    """Sorted list of all playable card names."""
    df = load_playable_cards()
    return sorted(df["Unit"].unique().tolist())


def get_card_at_level(card_name: str, level: int) -> pd.Series | None:
    """Return a single row for a card at a given level."""
    df = load_playable_cards()
    row = df[(df["Unit"] == card_name) & (df["Level"] == level)]
    return row.iloc[0] if not row.empty else None


def get_card_types() -> dict[str, str]:
    """Map card name -> Type."""
    df = load_playable_cards()
    return df.groupby("Unit")["Type"].first().to_dict()


def get_card_meta(column: str) -> dict[str, any]:
    """Map card name -> first non-null value of a column (for constant fields like Range)."""
    df = load_playable_cards()
    return df.groupby("Unit")[column].first().to_dict()


def load_card_reference() -> pd.DataFrame:
    """The hand-editable card_reference.csv: elixir, rarity, evolution/champion flags,
    roles, and the match-data id (blank for cards newer than the match dataset)."""
    df = pd.read_csv(CARD_REFERENCE_PATH, keep_default_na=False)
    df["match_id"] = pd.to_numeric(df["match_id"], errors="coerce")
    df["elixir"] = pd.to_numeric(df["elixir"], errors="coerce")
    df["is_champion"] = df["is_champion"].astype(str).str.lower() == "true"
    df["has_evolution"] = df["has_evolution"].astype(str).str.lower() == "true"
    if "has_hero" in df.columns:
        df["has_hero"] = df["has_hero"].astype(str).str.lower() == "true"
    return df


def get_elixir_costs() -> dict[str, int]:
    """Map card name -> elixir cost, from card_reference.csv."""
    ref = load_card_reference()
    return {
        row["card_name"]: int(row["elixir"])
        for _, row in ref.iterrows()
        if pd.notna(row["elixir"])
    }


def get_card_roles() -> dict[str, list[str]]:
    """Map role -> list of card names, from card_reference.csv's roles column
    (rebuilds the same shape as the old hardcoded CARD_ROLES dict)."""
    ref = load_card_reference()
    roles: dict[str, list[str]] = {}
    for _, row in ref.iterrows():
        for role in row["roles"].split(";"):
            role = role.strip()
            if role:
                roles.setdefault(role, []).append(row["card_name"])
    return roles


def get_evolution_info() -> dict[str, dict]:
    """Map card name -> {has_evolution, evolution_name} for cards with a known evolution."""
    ref = load_card_reference()
    return {
        row["card_name"]: {
            "has_evolution": bool(row["has_evolution"]),
            "evolution_name": row["evolution_name"],
        }
        for _, row in ref.iterrows()
        if row["has_evolution"]
    }


def get_evolution_stat_bonus() -> dict[str, float]:
    """Map card name -> HP bonus fraction (e.g. 0.25 for +25%) for the handful
    of evolutions with a confirmed, quantified flat stat bonus on top of the
    normal per-level curve (most evolutions are pure-ability, no stat change --
    only these have a real, sourced percentage)."""
    if not EVOLUTION_STAT_BONUS_PATH.exists():
        return {}
    df = pd.read_csv(EVOLUTION_STAT_BONUS_PATH)
    return {row["card_name"]: row["hp_bonus_pct"] / 100 for _, row in df.iterrows()}


def get_evolution_abilities() -> dict[str, dict]:
    """Map card name -> {ability_name, ability_description, confidence} from
    data/card_evolutions.csv. confidence is 'confirmed' (verified via web
    research against the card's real in-game ability) or 'unconfirmed' (the
    live API's maxEvolutionLevel confirms a real evolution exists, but no
    reliable source for its exact ability was found -- these are a handful of
    cards where search results kept surfacing unofficial fan concepts or a
    different, newer 'Hero' card system instead of the actual Evolution)."""
    if not CARD_EVOLUTIONS_PATH.exists():
        return {}
    df = pd.read_csv(CARD_EVOLUTIONS_PATH, keep_default_na=False)
    return {
        row["card_name"]: {
            "ability_name": row["ability_name"] or None,
            "ability_description": row["ability_description"],
            "confidence": row["confidence"],
        }
        for _, row in df.iterrows()
    }


def get_hero_abilities() -> dict[str, dict]:
    """Map card name -> {ability_name, ability_description, confidence} from
    data/card_heroes.csv -- the separate, newer "Hero" upgrade system
    (permanent unlock + its own ability, distinct from classic Evolutions;
    disambiguated by the live API's heroMedium vs evolutionMedium icon key,
    since maxEvolutionLevel alone doesn't tell them apart -- see
    scripts/build_card_reference.py)."""
    if not CARD_HEROES_PATH.exists():
        return {}
    df = pd.read_csv(CARD_HEROES_PATH, keep_default_na=False)
    return {
        row["card_name"]: {
            "ability_name": row["ability_name"] or None,
            "ability_description": row["ability_description"],
            "confidence": row["confidence"],
        }
        for _, row in df.iterrows()
    }


def get_card_match_id_map() -> tuple[dict[str, int], dict[int, str]]:
    """Return (name_to_id, id_to_name) maps for cards that appear in the match dataset
    (i.e. have a non-blank match_id in card_reference.csv)."""
    ref = load_card_reference()
    mapped = ref[ref["match_id"].notna()]
    name_to_id = dict(zip(mapped["card_name"], mapped["match_id"].astype(int)))
    id_to_name = {v: k for k, v in name_to_id.items()}
    return name_to_id, id_to_name
