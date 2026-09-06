"""
One-time historical data correction (2026-08-06).

Earlier the same day, split_evolution_hero_cards used the battlelog card
array's POSITION to guess which of Evolution/Hero was active for the 4
dual-capable cards (Knight, Musketeer, Wizard, Valkyrie). That guess was
later proven unreliable (battlelog card order isn't stable between battles
of the identical real deck) and removed -- see card_service
.split_evolution_hero_cards's current docstring. The fix was applied to the
CODE going forward, but every row of data/collected_battles.csv collected
BEFORE the fix still has the OLD, guessed Evolution/Hero classification
baked into its team_evolved_cards/team_hero_cards columns for these 4 cards
specifically. Simply re-running the retrain script does not correct this --
it only aggregates whatever's already in those columns.

This script retroactively corrects the full historical CSV without needing
to re-fetch anything from the API: for every row, any of the 4 dual-capable
card names found in an evolved_cards or hero_cards column is moved into the
matching ambiguous_cards column instead (merged, deduped). Every OTHER card
(the vast majority) is completely unaffected -- there was never any
ambiguity for single-capable cards.

Usage: python scripts/migrate_ambiguous_evo_hero.py
Safe to re-run: once dual-capable cards are no longer present in any
evolved/hero column, re-running is a no-op (verified via a dry-run count
printed before writing).
"""
import csv
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "cr_platform" / "backend"))

from services.card_service import get_evolution_hero_map  # noqa: E402
from services.battle_collector import COLLECTED_PATH, FIELDNAMES  # noqa: E402

DUAL_CAPABLE = {name for name, (has_evo, has_hero) in get_evolution_hero_map().items() if has_evo and has_hero}


def _fix_pair(evo_field: str, hero_field: str, ambig_field: str) -> tuple[str, str, str, bool]:
    evolved = [c for c in evo_field.split(";") if c]
    hero = [c for c in hero_field.split(";") if c]
    ambiguous = [c for c in ambig_field.split(";") if c]

    moved = False
    kept_evolved = []
    for c in evolved:
        if c in DUAL_CAPABLE:
            if c not in ambiguous:
                ambiguous.append(c)
            moved = True
        else:
            kept_evolved.append(c)

    kept_hero = []
    for c in hero:
        if c in DUAL_CAPABLE:
            if c not in ambiguous:
                ambiguous.append(c)
            moved = True
        else:
            kept_hero.append(c)

    return ";".join(kept_evolved), ";".join(kept_hero), ";".join(ambiguous), moved


def main():
    if not COLLECTED_PATH.exists():
        print("No collected_battles.csv found -- nothing to migrate.")
        return

    print(f"Dual-capable cards being corrected: {sorted(DUAL_CAPABLE)}")

    tmp_path = COLLECTED_PATH.with_suffix(".csv.migrating")
    total = 0
    rows_changed = 0
    t0 = time.time()

    with open(COLLECTED_PATH, encoding="utf-8", newline="") as fin, \
         open(tmp_path, "w", encoding="utf-8", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=FIELDNAMES)
        writer.writeheader()

        for row in reader:
            total += 1
            row_changed = False

            te, th, ta, changed1 = _fix_pair(
                row.get("team_evolved_cards", "") or "",
                row.get("team_hero_cards", "") or "",
                row.get("team_ambiguous_cards", "") or "",
            )
            if changed1:
                row["team_evolved_cards"], row["team_hero_cards"], row["team_ambiguous_cards"] = te, th, ta
                row_changed = True

            oe, oh, oa, changed2 = _fix_pair(
                row.get("opponent_evolved_cards", "") or "",
                row.get("opponent_hero_cards", "") or "",
                row.get("opponent_ambiguous_cards", "") or "",
            )
            if changed2:
                row["opponent_evolved_cards"], row["opponent_hero_cards"], row["opponent_ambiguous_cards"] = oe, oh, oa
                row_changed = True

            if row_changed:
                rows_changed += 1

            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})

            if total % 200000 == 0:
                print(f"  ...{total} rows processed ({rows_changed} corrected so far)")

    shutil.move(str(tmp_path), str(COLLECTED_PATH))
    print(f"Done in {round(time.time() - t0, 1)}s: {total} rows processed, {rows_changed} rows had a dual-capable "
          f"card moved from evolved/hero into ambiguous.")


if __name__ == "__main__":
    main()
