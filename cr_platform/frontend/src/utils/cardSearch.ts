/**
 * Shared card-name search used by Browse Cards, the deck-builder's card
 * picker, and the navbar's card search -- real feedback (2026-08-21): typing
 * "NOB" surfaced a card containing "nob" in the middle of its name (e.g.
 * "Arnob"-style) ahead of/alongside ones actually STARTING with what was
 * typed, which reads as irrelevant. A concrete real example in this app's
 * own card list: searching "Giant" plain substring-matches "Giant", "Giant
 * Skeleton", "Royal Giant", AND "Electro Giant" with no preference for the
 * ones that actually START with "Giant" -- alphabetical order even put
 * "Electro Giant" ahead of the plain "Giant" card. Prefix matches now always
 * rank first (each group kept alphabetical), so a query preferentially
 * surfaces the card whose name you actually started typing.
 */
export function searchCardsByName<T extends { name: string }>(cards: T[], query: string): T[] {
  const q = query.trim().toLowerCase()
  if (!q) return cards
  const startsWith: T[] = []
  const contains: T[] = []
  for (const c of cards) {
    const name = c.name.toLowerCase()
    if (name.startsWith(q)) startsWith.push(c)
    else if (name.includes(q)) contains.push(c)
  }
  return [...startsWith, ...contains]
}
