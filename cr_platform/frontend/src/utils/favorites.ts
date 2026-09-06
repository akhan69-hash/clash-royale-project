import { useEffect, useState } from 'react'

/**
 * Favorite decks, stored client-side (localStorage) so they work the same
 * way everywhere a deck is rendered -- Top Decks, Counter Decks, My Decks --
 * without needing a backend user account system. A deck's identity is its
 * card set regardless of slot order (deckKey sorts before joining), so the
 * same 8 cards favorited from two different pages collapse into one entry.
 */
export interface FavoriteDeck {
  cards: string[]
  label?: string
  // Aggregate tables (Top Decks, Counter Decks) still report a single
  // statistically "typical" evolved/hero card with a rate; personal deck
  // history (My Decks) reports the exact real cards for that precise group
  // instead (see battle_collector.get_player_deck_history) -- both shapes
  // are kept so favorites saved from either source render correctly.
  typical_evolution?: string | null
  typical_hero?: string | null
  evolution_rate_pct?: number | null
  hero_rate_pct?: number | null
  evolved_cards?: string[] | null
  hero_cards?: string[] | null
  // Dual-capable cards (Knight/Musketeer/Wizard/Valkyrie) confirmed active
  // but Evolution-vs-Hero undeterminable from real match data.
  ambiguous_cards?: string[] | null
  // Real King Tower Troop most-often played with this exact deck (see
  // scripts/retrain_from_collected.py's _typical_tower_troop / TowerTroopSection.tsx).
  typical_tower_troop?: string | null
  tower_troop_rate_pct?: number | null
  tower_troop_win_rate_pct?: number | null
  tower_troop_image_url?: string | null
  win_rate?: number | null
  wins?: number | null
  frequency?: number | null
  avg_elixir?: number | null
  cycle_cost?: number | null
  synergy_score?: number | null
  mvp_card?: string | null
  saved_at: string
}

const STORAGE_KEY = 'cr_favorite_decks'
const EVENT_NAME = 'cr-favorites-changed'

export function deckKey(cards: string[]): string {
  return [...cards].filter(Boolean).sort().join('|')
}

export function getFavoriteDecks(): Record<string, FavoriteDeck> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')
  } catch {
    return {}
  }
}

function saveFavoriteDecks(favs: Record<string, FavoriteDeck>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(favs))
  window.dispatchEvent(new Event(EVENT_NAME))
}

export function isFavoriteDeck(cards: string[]): boolean {
  return deckKey(cards) in getFavoriteDecks()
}

export function toggleFavoriteDeck(deck: Omit<FavoriteDeck, 'saved_at'>) {
  const favs = getFavoriteDecks()
  const key = deckKey(deck.cards)
  if (key in favs) {
    delete favs[key]
  } else {
    favs[key] = { ...deck, saved_at: new Date().toISOString() }
  }
  saveFavoriteDecks(favs)
}

export function removeFavoriteDeck(cards: string[]) {
  const favs = getFavoriteDecks()
  delete favs[deckKey(cards)]
  saveFavoriteDecks(favs)
}

/** Re-renders on any favorite change, including from a different component
 * on the same page (custom event) or a different tab (storage event). */
export function useFavoriteDecks(): Record<string, FavoriteDeck> {
  const [favs, setFavs] = useState(getFavoriteDecks())
  useEffect(() => {
    const onChange = () => setFavs(getFavoriteDecks())
    window.addEventListener(EVENT_NAME, onChange)
    window.addEventListener('storage', onChange)
    return () => {
      window.removeEventListener(EVENT_NAME, onChange)
      window.removeEventListener('storage', onChange)
    }
  }, [])
  return favs
}
