import axios from 'axios'
import { getSessionId, getKnownPlayerTag } from './session'

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

// Attaches a stable per-browser session id (and the known player tag, if
// any) to every API call -- see utils/session.ts and main.py's activity-log
// middleware. Doesn't touch Authorization or anything auth-related.
api.interceptors.request.use((config) => {
  config.headers['X-Session-Id'] = getSessionId()
  const tag = getKnownPlayerTag()
  if (tag) config.headers['X-Player-Tag'] = tag
  return config
})

// Card types
export interface Card {
  name: string
  type: string
  rarity: string
  elixir_cost: number | null
  max_level: number
  card_id: number | null
  image_url: string | null
  range: string | null
  hit_speed: number | null
  has_evolution: boolean
  evolution_tiers: number
  evolution_name: string | null
  evolution_image_url: string | null
  evolution_ability_name: string | null
  evolution_ability_description: string | null
  evolution_confidence: 'confirmed' | 'unconfirmed' | null
  evolution_hp_bonus?: number
  has_hero: boolean
  hero_tiers: number
  hero_name: string | null
  hero_image_url: string | null
  hero_ability_name: string | null
  hero_ability_description: string | null
  hero_confidence: 'confirmed' | 'unconfirmed' | null
}

export interface CardStat {
  relative_level: number
  absolute_level: number
  hitpoints?: number
  damage?: number
  dps?: number
  crown_tower_damage?: number
  charge_damage?: number
  death_damage?: number
  shield_hitpoints?: number
}

export interface Player {
  tag: string
  name: string
  trophies: number
  best_trophies: number
  wins: number
  losses: number
  win_rate: number
  king_level: number
  clan: string | null
  unlocked_slots: { evolution_slots: number; hero_slots: number; wild_slots: number }
  current_deck: any[]
  cards: any[]
  current_tower_troop: any | null
  tower_troops: any[]
  global_rank: number | null
  best_global_rank: number | null
  season_trophies: number | null
  season_best_trophies: number | null
  path_of_legend_league: number | null
  seasonal_arena: { name: string | null; trophies: number | null; best_trophies: number | null } | null
}

// Card API
export const cardsApi = {
  getAll: (params?: { type?: string; rarity?: string; min_elixir?: number; max_elixir?: number }) =>
    api.get<{ items: Card[]; count: number }>('/cards', { params }).then(r => r.data),

  getDetail: (name: string, evolved = false) =>
    api.get<{ card: Card; stats: CardStat[] }>(`/cards/${encodeURIComponent(name)}`, { params: { evolved } }).then(r => r.data),

  getAtLevel: (name: string, level: number) =>
    api.get<CardStat>(`/cards/${encodeURIComponent(name)}/at-level`, { params: { relative_level: level } }).then(r => r.data),

  getProfile: (name: string) =>
    api.get(`/cards/${encodeURIComponent(name)}/profile`).then(r => r.data),

  getProfiles: (names: string[]) =>
    api.post<{ profiles: any[] }>('/cards/profiles', names).then(r => r.data.profiles),

  getRankings: (stat = 'DPS', per_elixir = false) =>
    api.get('/cards/rankings', { params: { stat, per_elixir } }).then(r => r.data),
}

// Player API -- apiKey is optional: the backend falls back to its own
// server-side CR_API_KEY when no Authorization header is sent at all (see
// players.py's get_api_key()), so real visitors never need their own
// Clash Royale developer key. The header is only sent when a caller
// explicitly supplies one (e.g. a power user working around rate limits).
export const playersApi = {
  getPlayer: (tag: string, apiKey?: string) =>
    api.get<Player>(`/players/${tag}`, {
      headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
    }).then(r => r.data),

  getBattles: (tag: string, apiKey?: string) =>
    api.get(`/players/${tag}/battles`, {
      headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
    }).then(r => r.data),

  // Real deck history from OUR OWN collected_battles.csv -- no CR API key
  // needed, this doesn't call the live API at all. Players run multiple
  // decks over time; this returns all of them with real win rates.
  getDeckHistory: (tag: string) =>
    api.get(`/players/${tag}/decks`).then(r => r.data),

  // Search-ahead over the app's own collected dataset (name or partial tag)
  // -- real feedback: "might help the player not to type the whole thing
  // in." No live CR API call, so no key/rate-limit concerns.
  search: (q: string, limit = 8): Promise<{ results: { tag: string; name: string | null }[] }> =>
    api.get('/players/search', { params: { q, limit } }).then(r => r.data),
}

// Rankings API -- official Supercell leaderboards, not our own collected
// data. Uses the server's own CR_API_KEY (same one the crawler/Player Lookup
// use) automatically, no key entry needed here.
export const rankingsApi = {
  locations: () => api.get('/rankings/locations').then(r => r.data),

  topPlayers: (locationId: number, limit = 50) =>
    api.get('/rankings/players', { params: { location_id: locationId, limit } }).then(r => r.data),

  topClans: (locationId: number, limit = 50) =>
    api.get('/rankings/clans', { params: { location_id: locationId, limit } }).then(r => r.data),

  searchTournaments: (name: string) =>
    api.get('/rankings/tournaments', { params: { name } }).then(r => r.data),

  getTournament: (tag: string) =>
    api.get(`/rankings/tournaments/${encodeURIComponent(tag.replace('#', ''))}`).then(r => r.data),

  searchClans: (name: string) =>
    api.get('/rankings/clans/search', { params: { name } }).then(r => r.data),

  getClan: (tag: string) =>
    api.get(`/rankings/clans/${encodeURIComponent(tag.replace('#', ''))}`).then(r => r.data),

  getClanWar: (tag: string) =>
    api.get(`/rankings/clans/${encodeURIComponent(tag.replace('#', ''))}/war`).then(r => r.data),
}

// Deck API
export const decksApi = {
  analyze: (cards: { name: string; relative_level: number }[]) =>
    api.post('/decks/analyze', { cards }).then(r => r.data),

  analyzeAbsolute: (cards: Record<string, number>) =>
    api.post('/decks/analyze-absolute', { cards }).then(r => r.data),

  // sort_by: reliability (default, Wilson-confidence + relevance blend) | frequency | win_rate | synergy_score
  counter: (
    cards: string[], cardLevels?: Record<string, number>,
    opts?: { page?: number; pageSize?: number; sortBy?: 'reliability' | 'frequency' | 'win_rate' | 'synergy_score'; strategy?: string },
  ) =>
    api.post('/decks/counter', { cards, card_levels: cardLevels }, {
      params: { page: opts?.page, page_size: opts?.pageSize, sort_by: opts?.sortBy, strategy: opts?.strategy },
    }).then(r => r.data),

  // Real counters for a whole STRATEGY (e.g. "Hog Rider (cycle)") instead of
  // one specific 8-card opponent deck -- pooled, more reliable games-played
  // numbers than a single exact-deck matchup. sort_by: frequency | win_rate.
  counterStrategy: (vsStrategy: string, page = 1, pageSize = 4, sortBy: 'frequency' | 'win_rate' = 'frequency') =>
    api.get('/decks/counter-strategy', { params: { vs_strategy: vsStrategy, page, page_size: pageSize, sort_by: sortBy } }).then(r => r.data),

  slotThresholds: () => api.get('/decks/slot-thresholds').then(r => r.data),
}

// Synergy API
export const synergyApi = {
  topPartners: (card: string, topN = 200) =>
    api.get(`/synergy/${encodeURIComponent(card)}`, { params: { top_n: topN } }).then(r => r.data),

  network: (cards: string[]) =>
    api.post('/synergy/network', cards).then(r => r.data),

  suggest: (cards: string[], topN = 12) =>
    api.post('/synergy/suggest', cards, { params: { top_n: topN } }).then(r => r.data),
}

// ML API -- entirely live-data-trained now; the 2023-dataset model and Elo
// (which had no live equivalent) have both been retired.
export const mlApi = {
  predict: (deckA: string[], deckB: string[]) =>
    api.post('/ml/predict', { deck_a: deckA, deck_b: deckB }).then(r => r.data),

  cardValue: (refLevel = 11) =>
    api.get('/ml/card-value', { params: { ref_level: refLevel } }).then(r => r.data),

  collectionStats: () => api.get('/ml/collection-stats').then(r => r.data),
}

// Meta API -- entirely live-data now; the 2023 Kaggle-snapshot baseline has
// been retired (card stats, deck archetypes, and their fallback tiers).
export const metaApi = {
  topCards: (sortBy: 'win_rate' | 'presence_rate' = 'win_rate', limit = 200) =>
    api.get('/meta/cards', { params: { sort_by: sortBy, limit } }).then(r => r.data),

  topDecks: (
    limit = 14, arena?: string, sortBy?: 'frequency' | 'win_rate' | 'cycle_cost' | 'synergy_score',
    card?: string, variant?: 'regular' | 'evolution' | 'hero' | 'evolved_or_hero',
    page?: number, strategy?: string,
  ) =>
    api.get('/meta/decks', { params: { limit, arena, sort_by: sortBy, card, variant, page, strategy } }).then(r => r.data),

  // Real deck strategies (primary win condition + flavor, e.g. "Hog Rider (cycle)")
  // with how many real decks/games back each one -- powers strategy filter dropdowns.
  deckStrategies: () => api.get('/meta/deck-strategies').then(r => r.data),

  arenas: () => api.get('/meta/arenas').then(r => r.data),

  arenaCards: (arena: string, limit = 30) =>
    api.get(`/meta/arenas/${encodeURIComponent(arena)}/cards`, { params: { limit } }).then(r => r.data),

  evolutionUsage: () =>
    api.get('/meta/evolution-usage').then(r => r.data),

  towerTroopUsage: () =>
    api.get('/meta/tower-troop-usage').then(r => r.data),

  elixirLeakStats: () =>
    api.get('/meta/elixir-leak-stats').then(r => r.data),
}

// Coaching API -- see cr_platform/backend/routers/coaching.py's docstring
// for exactly what is/isn't achievable from real data (card placement and
// live in-match trades still aren't -- everything else here is real).
export const coachingApi = {
  lossPatterns: (yourDeck: string[], losses: string[][]) =>
    api.post('/coaching/loss-patterns', { your_deck: yourDeck, losses }).then(r => r.data),

  arenaForTrophies: (trophies: number) =>
    api.get('/coaching/arena-for-trophies', { params: { trophies } }).then(r => r.data),

  elixirBenchmark: (cards: string[]) =>
    api.post('/coaching/elixir-benchmark', { cards }).then(r => r.data),
}

export const whatsNextApi = {
  get: () => api.get('/whats-next').then(r => r.data),
}

export default api
