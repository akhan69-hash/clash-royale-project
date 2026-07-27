import pandas as pd
import numpy as np
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data" / "clash_royale_master_stats.csv"
CARD_REFERENCE_PATH = Path(__file__).parent.parent / "data" / "card_reference.csv"

# Cards that are sub-units or spawned troops (not directly playable)
SUB_UNITS = {
    "Ram (Ram Rider)", "Rider (Ram Rider)", "Rascal Boy", "Rascal Girl",
    "Phoenix Egg", "Lava Pups", "Elixir Golemite", "Elixir Blob",
    "Golemite", "Bush Goblin", "Cursed Hog", "Goblin Brawler",
    "Monster (Goblinstein)", "Guardian (Little Prince)", "Goblin Machine Rocket"
}

def _load_raw() -> pd.DataFrame:
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
    return _load_raw()


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


def get_card_match_id_map() -> tuple[dict[str, int], dict[int, str]]:
    """Return (name_to_id, id_to_name) maps for cards that appear in the match dataset
    (i.e. have a non-blank match_id in card_reference.csv)."""
    ref = load_card_reference()
    mapped = ref[ref["match_id"].notna()]
    name_to_id = dict(zip(mapped["card_name"], mapped["match_id"].astype(int)))
    id_to_name = {v: k for k, v in name_to_id.items()}
    return name_to_id, id_to_name
