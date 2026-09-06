"""
Arena trophy-threshold table, used to bucket real battles by (approximate)
skill/progression range for the Analytics "by Arena" view and for showing a
player their own specific real arena/league.

Sourced from community references (Fandom Arenas wiki + guide sites), cross-
checked for internal consistency (names + smooth trophy progression), NOT
from the official API -- the API doesn't expose a simple "arena" field, only
per-battle trophy counts. Flagged as approximate rather than exact because
the trophy road itself has been reworked multiple times.

EXPANDED 2026-08-06: the table previously stopped at 7,500 trophies with
everything above lumped into one "Arena 20+ - Legendary Arena and beyond"
bucket -- real players well past 7,500 (routinely 8,000-15,000+) were all
shown that same generic label regardless of how far past it they actually
were. Re-sourced the real progression above that point: Arena 20 (Boot
Camp, added June 2023) at 7,500 is followed by 4 more named arenas (21-24),
then 5 "Seasonal Arena" slots (rotating design/rewards, not individually
named) up to 15,000. Above 15,000, Path of Legends was renamed "Ranked" in
the June 2026 update and became step-based (win moves you up a step, loss
moves you down, not a simple cumulative trophy threshold) across 7 leagues
(Master I -> Ultimate Champion) -- there's no honest single trophy number
to bucket further within Ranked, so 15,000+ is left as one clearly-labeled
"Ranked" bucket rather than fabricating fake sub-thresholds for it."""

ARENA_TABLE = [
    (0, "Arena 1 - Goblin Stadium"),
    (300, "Arena 2 - Bone Pit"),
    (600, "Arena 3 - Barbarian Bowl"),
    (1000, "Arena 4 - Spell Valley"),
    (1300, "Arena 5 - Builder's Workshop"),
    (1600, "Arena 6 - P.E.K.K.A's Playhouse"),
    (2000, "Arena 7 - Royal Arena"),
    (2300, "Arena 8 - Frozen Peak"),
    (2600, "Arena 9 - Jungle Arena"),
    (3000, "Arena 10 - Hog Mountain"),
    (3400, "Arena 11 - Electro Valley"),
    (3800, "Arena 12 - Spooky Town"),
    (4200, "Arena 13 - Rascal's Hideout"),
    (4600, "Arena 14 - Serenity Peak"),
    (5000, "Arena 15 - Miner's Mine"),
    (5500, "Arena 16 - Executioner's Kitchen"),
    (6000, "Arena 17 - Royal Crypt"),
    (6500, "Arena 18 - Silent Sanctuary"),
    (7000, "Arena 19 - Dragon Spa"),
    (7500, "Arena 20 - Boot Camp"),
    (8000, "Arena 21 - Clash Fest"),
    (8500, "Arena 22 - PANCAKES!"),
    (9000, "Arena 23 - Valkalla"),
    (9500, "Arena 24 - Legendary Arena"),
    (10000, "Seasonal Arena 1"),
    (11000, "Seasonal Arena 2"),
    (12000, "Seasonal Arena 3"),
    (13500, "Seasonal Arena 4"),
    (15000, "Ranked (Master I and above)"),
]


def get_arena_for_trophies(trophies: int | float | None) -> str | None:
    """Returns the highest arena name whose threshold the trophy count clears,
    or None if trophies is missing/invalid."""
    if trophies is None:
        return None
    try:
        trophies = float(trophies)
    except (TypeError, ValueError):
        return None

    result = ARENA_TABLE[0][1]
    for threshold, name in ARENA_TABLE:
        if trophies >= threshold:
            result = name
        else:
            break
    return result


def get_arena_options() -> list[str]:
    return [name for _, name in ARENA_TABLE]
