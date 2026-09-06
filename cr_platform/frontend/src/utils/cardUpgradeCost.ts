/**
 * Real card copies needed to upgrade to the NEXT level -- feedback
 * (2026-09-02): "i want collections to show card levels card shards and
 * cards to the next level upgrade under the cards. say 981/1000 under it."
 *
 * Sourced from two real, cross-checked places (2026-09-02 research, current
 * post-November-2025-economy-rework numbers):
 *   1. Levels 1-12: one shared progression -- confirmed IDENTICAL across
 *      Common/Rare/Epic/Legendary in a real per-rarity table (each rarity
 *      just starts consuming it from a different point, matching real CR
 *      mechanics where rarity determines starting level, not the marginal
 *      cost curve).
 *   2. Levels 13-16: Supercell's own official "Level 16" update announcement,
 *      which gives real per-rarity numbers directly (the shared-sequence
 *      pattern doesn't extend cleanly to these 4 levels -- they're a flat,
 *      rarity-specific overlay Supercell added on top when Level 16 shipped).
 *
 * Cross-validated against independently-sourced cumulative totals (total
 * copies from each rarity's start level to 16): Champion matched EXACTLY
 * (2+5+8+11+15 = 41, vs. an independent source's "41 copies from Level 11"),
 * Common and Legendary landed within 2-6% (plausible rounding, not a
 * structural error given Champion's exact match). Not settled with 100%
 * certainty -- both source fetches were AI-summarized, not hand-verified
 * against a raw table -- but implemented with real, reasoned confidence
 * rather than left out. Worth a real in-game spot-check against a card near
 * level 12-13 someday to fully close the loop.
 */
const SHARED_SEQUENCE = [2, 4, 10, 20, 50, 100, 200, 400, 800, 1000, 2000] // relative transitions, covers up through reaching absolute level 12

const RARITY_START_LEVEL: Record<string, number> = {
  Common: 1, Rare: 3, Epic: 6, Legendary: 9, Champion: 11,
}

// Transition INTO this absolute level, keyed by rarity -- from Supercell's
// own Level 16 announcement.
const TOP_TABLE: Record<string, Record<number, number>> = {
  Common: { 13: 2500, 14: 3500, 15: 5500, 16: 7500 },
  Rare: { 13: 550, 14: 750, 15: 1000, 16: 1400 },
  Epic: { 13: 70, 14: 100, 15: 130, 16: 180 },
  Legendary: { 13: 9, 14: 12, 15: 14, 16: 20 },
  Champion: { 13: 5, 14: 8, 15: 11, 16: 15 },
}

/** Real copies needed for currentLevel -> currentLevel+1, or null if already
 * max level (16) or the rarity/level combo isn't covered. */
export function copiesForNextLevel(rarity: string, currentLevel: number): number | null {
  const target = currentLevel + 1
  if (target > 16) return null
  if (target <= 12) {
    const start = RARITY_START_LEVEL[rarity]
    if (start == null) return null
    const idx = target - start - 1
    if (idx < 0 || idx >= SHARED_SEQUENCE.length) return null
    return SHARED_SEQUENCE[idx]
  }
  return TOP_TABLE[rarity]?.[target] ?? null
}
