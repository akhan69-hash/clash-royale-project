/**
 * Copy/paste a deck's 8 card names between any two deck-building surfaces on
 * the site -- real feedback (2026-08-22): "being able to copy and paste
 * entire decks from different pages to different pages on the site." Plain
 * comma-joined card names (not JSON) so a copied deck is also just readable
 * text if pasted somewhere else entirely.
 */
export function deckToClipboardText(cards: string[]): string {
  return cards.filter(Boolean).join(', ')
}

/** Parses clipboard text back into up to 8 real card names, validated
 * against the app's actual card list -- silently drops anything that isn't
 * a real card name (typos, stray text) rather than crashing on it. */
export function parseClipboardDeck(text: string, validNames: Set<string>): string[] {
  return text.split(',')
    .map(s => s.trim())
    .filter(name => validNames.has(name))
    .slice(0, 8)
}
