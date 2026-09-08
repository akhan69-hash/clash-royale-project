import { useState, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Lock, Unlock } from 'lucide-react'
import { playersApi, decksApi, cardsApi, metaApi, coachingApi, synergyApi, Card } from '../utils/api'
import CardImage, { CardName } from '../components/CardImage'
import { useCardDetail } from '../contexts/CardDetailContext'
import CounterDecksList from '../components/CounterDecksList'
import Backdrop from '../components/Backdrop'
import PageArtBackdrop from '../components/PageArtBackdrop'
import Collapsible from '../components/Collapsible'
import TowerTroopSection from '../components/TowerTroopSection'
import SwipeCarousel from '../components/SwipeCarousel'
import FavoriteButton from '../components/FavoriteButton'
import { CopyDeckButton } from '../components/DeckBuilderKit'
import DeckStatsInline from '../components/DeckStatsInline'
import Pagination from '../components/Pagination'
import { friendlyPlayerError } from '../utils/friendlyError'
import TipsCarousel, { type Tip } from '../components/TipsCarousel'
import NoPlayerYet from '../components/NoPlayerYet'
import SectionSkeleton from '../components/SectionSkeleton'
import { addRecentPlayer, getDefaultPlayerTag } from '../utils/recentPlayers'
import SkeletonLoader from '../components/SkeletonLoader'

// Lowered from 10 -> 4 (2026-08-20): see PlayerPage.tsx's identical constant
// for the full reasoning (tall deck cards meant too much scrolling per page).
const MY_DECKS_PAGE_SIZE = 4

const DEV_UNLOCK_KEY = 'cr_coach_dev_unlock'

const ARENA_DECK_SORTS = [
  ['frequency', 'Most Played'],
  ['win_rate', 'Highest Win Rate'],
  ['synergy_score', 'Best Synergy'],
] as const

function ArenaDeckSortButtons({ sortBy, onChange }: {
  sortBy: 'frequency' | 'win_rate' | 'synergy_score'; onChange: (v: 'frequency' | 'win_rate' | 'synergy_score') => void
}) {
  return (
    <div className="flex flex-wrap gap-1 mb-3">
      {ARENA_DECK_SORTS.map(([key, label]) => (
        <button key={key} onClick={() => onChange(key)}
          className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors
            ${sortBy === key ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
          {label}
        </button>
      ))}
    </div>
  )
}

// A single deck card, styled consistently with Analytics' Top Decks / Favorites
// -- reused for "What's winning at your arena" and "Trophy Push" so both look
// like real, professional deck cards (real frames, win rate, cycle, evo/hero)
// instead of the previous bare card-icon-grid-plus-one-line treatment.
function ArenaDeckCard({ d, imageFor, rarityFor, evolutionImageFor, heroImageFor }: {
  d: any
  imageFor: (n: string) => string | null | undefined
  rarityFor: (n: string) => string | null | undefined
  evolutionImageFor: (n: string) => string | null | undefined
  heroImageFor: (n: string) => string | null | undefined
}) {
  const { openCard } = useCardDetail()
  return (
    <div className="bg-bg-card rounded-lg p-2.5">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-text-muted">{d.frequency?.toLocaleString()} games · avg {d.avg_elixir} elixir</span>
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold text-cyan-300">{d.win_rate}% WR</span>
          <FavoriteButton deck={{
            cards: d.cards, label: 'Arena Deck', win_rate: d.win_rate, wins: d.wins, frequency: d.frequency,
            avg_elixir: d.avg_elixir, cycle_cost: d.cycle_cost, synergy_score: d.synergy_score,
            typical_evolution: d.typical_evolution, typical_hero: d.typical_hero,
            evolution_rate_pct: d.evolution_rate_pct, hero_rate_pct: d.hero_rate_pct,
            ambiguous_cards: d.typical_ambiguous ? [d.typical_ambiguous] : undefined,
            typical_tower_troop: d.typical_tower_troop, tower_troop_rate_pct: d.tower_troop_rate_pct,
            tower_troop_win_rate_pct: d.tower_troop_win_rate_pct, tower_troop_image_url: d.tower_troop_image_url,
          }} size={12} />
        </div>
      </div>
      <div className="text-[9px] text-text-muted mb-1.5">
        <span title="Combined elixir cost of the 4 cheapest cards in this deck -- lower means faster cycling back to your win condition">⚡ Cycle {d.cycle_cost}</span>
        {d.synergy_score != null && <> · <span title="Average real card-pairing synergy across this deck's cards, from how those pairs have actually performed together in collected battles -- higher is better">🔗 Synergy {d.synergy_score}</span></>}
      </div>
      <div className="grid grid-cols-4 sm:grid-cols-8 gap-0.5">
        {d.cards.map((n: string) => (
          <CardImage key={n} name={n} imageUrl={imageFor(n)} rarity={rarityFor(n) ?? undefined} size="xs" showName={false}
            evolutionImageUrl={evolutionImageFor(n)} heroImageUrl={heroImageFor(n)} onClick={() => openCard(n)}
            isEvolved={d.typical_evolution === n} isHero={d.typical_hero === n} isAmbiguous={d.typical_ambiguous === n} />
        ))}
      </div>
      {(d.typical_evolution || d.typical_hero || d.typical_ambiguous) && (
        <div className="text-[9px] text-text-muted mt-1">
          {d.typical_evolution && <>⬆ {d.typical_evolution} evolved {d.evolution_rate_pct}%</>}
          {d.typical_evolution && (d.typical_hero || d.typical_ambiguous) && ' · '}
          {d.typical_hero && <>★ {d.typical_hero} hero'd {d.hero_rate_pct}%</>}
          {d.typical_hero && d.typical_ambiguous && ' · '}
          {d.typical_ambiguous && <>? {d.typical_ambiguous} evo-or-hero'd {d.ambiguous_rate_pct}%</>}
        </div>
      )}
      <TowerTroopSection d={d} />
    </div>
  )
}

// Deck Health stays free -- everything past it is a preview of a planned
// subscription tier: blurred with a lock overlay, unlockable right now via
// this dev-only button (no real payment/auth wired up yet, this is just the
// UI shape for when that lands).
function PremiumGate({ unlocked, onUnlock, children }: { unlocked: boolean; onUnlock: () => void; children: React.ReactNode }) {
  if (unlocked) return <>{children}</>
  return (
    <div className="relative max-h-[28rem] overflow-hidden rounded-xl">
      <div className="pointer-events-none select-none blur-md opacity-60 space-y-5">{children}</div>
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-bg-primary/50">
        <div className="bg-bg-surface border border-gold/40 rounded-xl px-5 py-4 text-center shadow-card">
          <Lock size={20} className="text-gold mx-auto mb-2" />
          <p className="text-sm font-semibold text-white mb-1">Full coaching is a planned premium feature</p>
          <p className="text-xs text-text-muted mb-3 max-w-xs">Loss patterns, counters, trophy push, and upgrade priorities will be part of a subscription later.</p>
          {/* Dev-only unlock button hidden for now (2026-08-20, per user request) --
              it's not something a real visitor should see/use before there's an
              actual paywall behind it. Logic kept fully intact (onUnlock/unlocked
              state, localStorage flag) so it's a one-line revert to bring back for
              local testing -- just remove this guard. */}
          {false && (
            <button onClick={onUnlock}
              className="bg-gold hover:bg-gold-hover text-bg-primary font-bold px-4 py-2 rounded-xl text-sm flex items-center gap-2 mx-auto">
              <Unlock size={14} /> Unlock (Developer)
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// Shortened + an icon per term (2026-08-20, real feedback: "less texts less
// technical more understanding for regular people") -- these used to be full
// sentences with parenthetical card-name examples; now short enough to scan.
const GLOSSARY = [
  { icon: '⚔️', term: 'Win Condition', def: 'The card that actually wins you the game by hitting towers (Hog Rider, Giant...).' },
  { icon: '💜', term: 'Elixir Trade', def: 'Spending less than your opponent in a fight -- you come out ahead.' },
  { icon: '💥', term: 'Swarm Clear', def: 'A card that wipes out cheap groups of troops in one hit.' },
  { icon: '🎯', term: 'Tank Killer', def: 'A card built to melt big, tanky troops fast.' },
  { icon: '🔄', term: 'Cycle', def: 'Cheap cards that get you back to your win condition faster.' },
  { icon: '🎣', term: 'Bait', def: "A card played to lure out the opponent's spell first." },
  { icon: '🏹', term: 'Siege', def: 'A deck built around a building that chips the tower from range.' },
]

function ConceptsGlossary() {
  return (
    <Collapsible title="📖 Core Concepts">
      <div className="space-y-2">
        {GLOSSARY.map(t => (
          <div key={t.term} className="flex items-start gap-1.5">
            <span className="shrink-0">{t.icon}</span>
            <div>
              <span className="text-xs font-semibold text-accent">{t.term}: </span>
              <span className="text-xs text-text-secondary">{t.def}</span>
            </div>
          </div>
        ))}
      </div>
    </Collapsible>
  )
}

export default function CoachingPage() {
  const { openCard } = useCardDetail()
  const { tag: urlTag } = useParams()
  const navigate = useNavigate()
  const [apiKey, setApiKey] = useState(localStorage.getItem('cr_api_key') ?? '')
  // Derived straight from the route param, not its own state -- see
  // PlayerPage.tsx's identical comment for the real bug this avoids
  // (searchTag used to only ever advance via the now-removed in-page search
  // form, so navigating here any other way silently never loaded the tag).
  const searchTag = (urlTag ?? '').replace('#', '')
  // Real feedback (2026-09-01): "the player searched should be saved and
  // carried into when visiting different pages like coach or build." The
  // same remembered-tag mechanism PlayerPage.tsx already uses -- a bare
  // /coach visit (no tag in the URL) redirects to whichever player was most
  // recently looked up anywhere in the app, instead of landing on an empty
  // NoPlayerYet state every time.
  useEffect(() => {
    if (!urlTag) {
      const remembered = getDefaultPlayerTag()
      if (remembered) navigate(`/coach/${remembered}`, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlTag])
  const [counters, setCounters] = useState<any>(null)
  const [favDeckCounters, setFavDeckCounters] = useState<any>(null)
  const [unlocked, setUnlocked] = useState(() => localStorage.getItem(DEV_UNLOCK_KEY) === '1')
  const [myDecksSort, setMyDecksSort] = useState<'win_rate' | 'times_played' | 'synergy_score'>('win_rate')
  const [myDecksPage, setMyDecksPage] = useState(1)
  // "Real decks for your Evolutions & Heroes" gallery -- collapsed to the
  // top 4 of each per default so a player who owns many variants doesn't
  // get an overwhelming wall of deck cards; "Show N more" reveals the rest.
  const [showAllEvoHeroDecks, setShowAllEvoHeroDecks] = useState(false)
  const myDecksTopRef = useRef<HTMLDivElement>(null)
  const unlock = () => { localStorage.setItem(DEV_UNLOCK_KEY, '1'); setUnlocked(true) }

  useEffect(() => {
    setCounters(null)
    setFavDeckCounters(null)
    setMyDecksPage(1)
  }, [searchTag])

  const { data, isLoading, error } = useQuery({
    queryKey: ['coach-player', searchTag, apiKey],
    queryFn: () => playersApi.getPlayer(searchTag, apiKey || undefined),
    enabled: !!searchTag,
  })
  if (data?.tag) addRecentPlayer(data.tag, data.name ?? null)
  const { data: battlesData } = useQuery({
    queryKey: ['coach-battles', searchTag, apiKey],
    queryFn: () => playersApi.getBattles(searchTag, apiKey || undefined),
    enabled: !!searchTag,
  })
  const { data: allCards } = useQuery({ queryKey: ['cards'], queryFn: () => cardsApi.getAll() })
  const imageFor = (n: string) => allCards?.items?.find((c: Card) => c.name === n)?.image_url
  // Coach's own visual identity (2026-09-07, new-season theme + "every
  // feature will have its own identity and art and font" pass) -- crimson,
  // Collapsible's own existing token for "tips/guidance/advisory content"
  // (exactly what this page is), distinct from Player Lookup's royale blue.
  // Hero Ice Wizard's real new ability (added this same session) as the
  // signature blurred art here, distinct from Player's Minion Giant.
  const COACH_ACCENT = '#C23B3B'
  const coachArtUrl = allCards?.items?.find((c: Card) => c.name === 'Ice Wizard')?.hero_image_url
    ?? allCards?.items?.find((c: Card) => c.name === 'Ice Wizard')?.image_url
  const rarityFor = (n: string) => allCards?.items?.find((c: Card) => c.name === n)?.rarity
  const evolutionImageFor = (n: string) => allCards?.items?.find((c: Card) => c.name === n)?.evolution_image_url
  const heroImageFor = (n: string) => allCards?.items?.find((c: Card) => c.name === n)?.hero_image_url

  const deckNames: string[] = (data?.current_deck ?? []).map((c: any) => c.name)
  const levelByName: Record<string, number> = {}
  for (const c of data?.cards ?? []) levelByName[c.name] = c.absolute_level
  const deckAbsLevels: Record<string, number> = Object.fromEntries(deckNames.map(n => [n, levelByName[n] ?? 11]))
  // Real per-slot Evolution/Hero status for the currently-equipped deck (see
  // players.py's get_player() -- currentDeck carries real evolutionLevel,
  // same as battlelog entries do).
  const evolvedInCurrentDeck = new Set((data?.current_deck ?? []).filter((c: any) => c.is_evolved).map((c: any) => c.name))
  const heroInCurrentDeck = new Set((data?.current_deck ?? []).filter((c: any) => c.is_hero).map((c: any) => c.name))
  const ambiguousInCurrentDeck = new Set((data?.current_deck ?? []).filter((c: any) => c.is_ambiguous).map((c: any) => c.name))

  // 1. Deck Health
  const { data: deckHealth } = useQuery({
    queryKey: ['coach-deck-health', deckNames.join(',')],
    queryFn: () => decksApi.analyzeAbsolute(deckAbsLevels),
    enabled: deckNames.length === 8,
  })

  // Real elixir-leaked average (Supercell's own elixirLeaked field, captured
  // per real battle since 2026-08-01 -- previously assumed unavailable and
  // has since been corrected).
  const elixirLeakedBattles = (battlesData?.battles ?? []).filter((b: any) => b.your_elixir_leaked != null)
  const avgElixirLeaked = elixirLeakedBattles.length > 0
    ? elixirLeakedBattles.reduce((sum: number, b: any) => sum + b.your_elixir_leaked, 0) / elixirLeakedBattles.length
    : null

  // 2. Loss Patterns -- purely real match-summary data
  const lossDecks: string[][] = (battlesData?.battles ?? [])
    .filter((b: any) => b.result === 'Loss')
    .map((b: any) => b.opponent_deck)
    .filter((d: string[]) => d?.length === 8)

  const { data: lossPatterns } = useQuery({
    queryKey: ['coach-loss-patterns', deckNames.join(','), lossDecks.length],
    queryFn: () => coachingApi.lossPatterns(deckNames, lossDecks),
    enabled: deckNames.length === 8 && lossDecks.length > 0,
  })

  // 3. Counters -- against a real opponent deck matching the top loss archetype
  const topArchetypeCard = lossPatterns?.top_archetypes?.[0]?.archetype?.split(' (')[0]
  const representativeLossDeck = lossDecks.find(d => d.includes(topArchetypeCard)) ?? lossDecks[0]
  const loadCounters = async () => {
    if (representativeLossDeck) setCounters(await decksApi.counter(representativeLossDeck))
  }

  // 4. Trophy Push
  const { data: arenaInfo } = useQuery({
    queryKey: ['coach-arena', data?.trophies],
    queryFn: () => coachingApi.arenaForTrophies(data?.trophies ?? 0),
    enabled: data?.trophies != null,
  })
  const { data: nextArenaCards } = useQuery({
    queryKey: ['coach-next-arena-cards', arenaInfo?.next_arena],
    queryFn: () => metaApi.arenaCards(arenaInfo.next_arena, 12),
    enabled: !!arenaInfo?.next_arena,
  })
  const [nextArenaSort, setNextArenaSort] = useState<'frequency' | 'win_rate' | 'synergy_score'>('frequency')
  const { data: nextArenaDecks } = useQuery({
    queryKey: ['coach-next-arena-decks', arenaInfo?.next_arena, nextArenaSort],
    queryFn: () => metaApi.topDecks(6, arenaInfo.next_arena, nextArenaSort),
    enabled: !!arenaInfo?.next_arena,
  })

  // "What top players in your arena are actually running" -- individually
  // fetching top-ranked players' decks live would be slow and undermine the
  // smoothness goal; real aggregated match data from everyone currently
  // playing at your arena bucket is the fast, honest equivalent, already
  // backed by real collected battles.
  const [currentArenaSort, setCurrentArenaSort] = useState<'frequency' | 'win_rate' | 'synergy_score'>('frequency')
  const { data: currentArenaDecks, isLoading: currentArenaDecksLoading } = useQuery({
    queryKey: ['coach-current-arena-decks', arenaInfo?.arena, currentArenaSort],
    queryFn: () => metaApi.topDecks(8, arenaInfo.arena, currentArenaSort),
    enabled: !!arenaInfo?.arena,
  })

  // Real card levels typical of your own arena bucket, to compare against
  // your own deck's real average level -- a genuinely new, free insight:
  // are you under/over-leveled relative to where you're actually playing.
  const { data: currentArenaCards, isLoading: arenaCardsLoading } = useQuery({
    queryKey: ['coach-current-arena-cards', arenaInfo?.arena],
    queryFn: () => metaApi.arenaCards(arenaInfo.arena),
    enabled: !!arenaInfo?.arena,
  })
  const myDeckAvgLevel = deckNames.length === 8
    ? Math.round((deckNames.reduce((sum, n) => sum + (levelByName[n] ?? 0), 0) / 8) * 10) / 10
    : null

  // Real pairwise synergy for the exact 8 cards in the player's current deck
  // (see routers/synergy.py's /synergy/network, already built for the
  // Synergy Graph page) -- surfaces the single weakest real-data pairing in
  // THIS specific deck, a genuinely personalized insight beyond generic tips.
  const { data: synergyNetwork, isLoading: synergyLoading } = useQuery({
    queryKey: ['coach-synergy-network', deckNames.join(',')],
    queryFn: () => synergyApi.network(deckNames),
    enabled: deckNames.length === 8,
  })
  const weakestSynergyPair = (() => {
    if (!synergyNetwork?.matrix) return null
    let worst: { a: string; b: string; score: number } | null = null
    for (let i = 0; i < deckNames.length; i++) {
      for (let j = i + 1; j < deckNames.length; j++) {
        const a = deckNames[i], b = deckNames[j]
        const score = synergyNetwork.matrix[i]?.[b]
        if (score == null) continue
        if (!worst || score < worst.score) worst = { a, b, score }
      }
    }
    return worst
  })()
  // Same real matrix, the other direction -- real feedback (2026-08-21):
  // "maybe add good pairing that goes with the current deck... for eg maybe
  // firecracker with golem (obv if its from the real data)." Mirrors
  // weakestSynergyPair exactly, just picking the highest real score instead
  // of the lowest.
  const bestSynergyPair = (() => {
    if (!synergyNetwork?.matrix) return null
    let best: { a: string; b: string; score: number } | null = null
    for (let i = 0; i < deckNames.length; i++) {
      for (let j = i + 1; j < deckNames.length; j++) {
        const a = deckNames[i], b = deckNames[j]
        const score = synergyNetwork.matrix[i]?.[b]
        if (score == null) continue
        if (!best || score > best.score) best = { a, b, score }
      }
    }
    return best
  })()

  // A general meta pulse -- what's actually winning across ALL real
  // collected battles right now, regardless of this player's own arena/deck.
  // Distinct from "what's winning at your arena" above (that's arena-scoped;
  // this is the overall picture, for broader context/inspiration).
  const { data: metaPulse, isLoading: metaPulseLoading } = useQuery({
    queryKey: ['coach-meta-pulse'],
    queryFn: () => metaApi.topDecks(3, undefined, 'win_rate'),
  })

  // "Decks that use your owned Evolutions/Heroes" -- real feedback
  // (2026-08-23): "your owned hero used deck owned evo used decks, that
  // uses all your evos/heros or most of them and also has proper win rate."
  // For each Evolution/Hero shard this player actually owns (data.cards'
  // real owns_evolution_shards/owns_hero_unlock), finds the single real
  // best-win-rate deck that plays it as that exact variant (GET
  // /meta/decks?card=X&variant=evolution|hero, same real endpoint "decks
  // using Hero Knight specifically" already used elsewhere).
  //
  // REVISED (2026-08-28): "make more decks from my evo decks my hero decks
  // ones that use all my evos or heros or even most of it" -- this used to
  // collapse every owned card's result down to a single overall best deck
  // (`.sort()[0]`), so a player who owns 6 evolutions only ever saw ONE
  // suggested deck. A real game rule caps this at one active evolution slot
  // and one hero slot per deck (see DeckBuilderKit's SLOT_ROLE), so no
  // single deck can ever "use all" a player's evolutions at once -- the
  // honest way to cover most of a player's owned collection is a real deck
  // PER owned card instead, deduped where two different owned cards happen
  // to point at the same top deck. Real, not invented: every candidate deck
  // is still an exact-deck real-battle aggregate row, same reliability
  // floor as the rest of Top Decks -- this only changes how many of them
  // are shown, not where they come from.
  const ownedEvolutionNames = (data?.cards ?? []).filter((c: any) => c.owns_evolution_shards).map((c: any) => c.name)
  const ownedHeroNames = (data?.cards ?? []).filter((c: any) => c.owns_hero_unlock).map((c: any) => c.name)
  const { data: ownedVariantDecks } = useQuery({
    queryKey: ['coach-owned-variant-decks', ownedEvolutionNames.join(','), ownedHeroNames.join(',')],
    queryFn: async () => {
      const [evoResults, heroResults] = await Promise.all([
        Promise.all(ownedEvolutionNames.map((name: string) =>
          metaApi.topDecks(1, undefined, 'win_rate', name, 'evolution').then((r: any) => r.decks?.[0] ?? null))),
        Promise.all(ownedHeroNames.map((name: string) =>
          metaApi.topDecks(1, undefined, 'win_rate', name, 'hero').then((r: any) => r.decks?.[0] ?? null))),
      ])
      // Real deck identity (its 8 cards, order-independent) is the dedupe
      // key -- two different owned cards can legitimately point at the same
      // top deck (e.g. it plays both as Evolution AND Hero-capable teammates),
      // which should only ever appear once in the gallery.
      const dedupeByDeck = (results: any[]) => {
        const seen = new Set<string>()
        const out: any[] = []
        for (const d of results) {
          if (!d) continue
          const key = [...(d.cards ?? [])].sort().join(';')
          if (seen.has(key)) continue
          seen.add(key)
          out.push(d)
        }
        return out.sort((a, b) => b.win_rate - a.win_rate)
      }
      const topEvoDecks = dedupeByDeck(evoResults)
      const topHeroDecks = dedupeByDeck(heroResults)
      return { topEvoDecks, topHeroDecks, bestEvo: topEvoDecks[0] ?? null, bestHero: topHeroDecks[0] ?? null }
    },
    enabled: ownedEvolutionNames.length > 0 || ownedHeroNames.length > 0,
  })

  // 5. Card Level Priorities -- real profile per deck card, real levels-to-max, no invented score.
  // One bulk request instead of 8 separate round trips (this used to be the
  // biggest chunk of Coaching's load time).
  const { data: cardProfiles, isLoading: cardProfilesLoading } = useQuery({
    queryKey: ['coach-card-profiles', deckNames.join(',')],
    queryFn: () => cardsApi.getProfiles(deckNames),
    enabled: deckNames.length === 8,
  })
  const levelPriorities = (cardProfiles ?? [])
    .map((p: any) => {
      const meta = data?.cards?.find((c: any) => c.name === p.name)
      return { ...p, levels_to_max: meta?.levels_to_max, pct_to_max: meta?.pct_to_max }
    })
    .sort((a: any, b: any) => (b.levels_to_max ?? 0) - (a.levels_to_max ?? 0))

  // Free quick tips -- real per-card win rates + real Evolution/Hero usage
  // rates, already fetched for the gated Upgrade Priorities table below, but
  // a MVP/weak-link/evo-hero highlight is useful on its own and doesn't need
  // to be locked behind the paywall preview to be worth showing.
  const cardsWithRealWinRate = (cardProfiles ?? []).filter((p: any) => p.live_stats?.win_rate != null)
  const deckMvp = cardsWithRealWinRate.length > 0
    ? cardsWithRealWinRate.reduce((a: any, b: any) => (b.live_stats.win_rate > a.live_stats.win_rate ? b : a))
    : null
  const deckWeakLink = cardsWithRealWinRate.length > 0
    ? cardsWithRealWinRate.reduce((a: any, b: any) => (b.live_stats.win_rate < a.live_stats.win_rate ? b : a))
    : null
  // Ownership + deck-relevance aware Evolution/Hero recommendation. Used to
  // be two separate tip sources: one recommended evolving/hero'ing ANY deck
  // card with real variant data regardless of whether the player actually
  // owned the shards for it, the other listed EVERY owned dual-capable card
  // app-wide regardless of whether it was even in this deck -- together
  // capable of producing many overlapping/irrelevant tips. Real feedback
  // (2026-08-20): "just assuming the user does not have it and giving him
  // tips is not efficient." Now: only cards genuinely in the current deck,
  // that the player genuinely owns the shards/unlock for (data.cards, see
  // players.py's cards_enriched), that aren't already slotted that way --
  // one tip per card, max, picking whichever owned-but-unused variant has
  // the better real win rate.
  const evoHeroActionableTips = deckNames
    .map((name: string) => {
      const profile = (cardProfiles ?? []).find((p: any) => p.name === name)
      const variants = profile?.real_evolution_hero_usage?.variants
      const ownership = (data?.cards ?? []).find((c: any) => c.name === name)
      if (!variants || !ownership) return null
      const candidates: Array<'evolution' | 'hero' | 'evolved_or_hero'> = []
      if (ownership.owns_evolution_shards && !evolvedInCurrentDeck.has(name) && variants.evolution) candidates.push('evolution')
      if (ownership.owns_hero_unlock && !heroInCurrentDeck.has(name) && variants.hero) candidates.push('hero')
      if (ownership.owns_evolution_shards && ownership.owns_hero_unlock
        && !evolvedInCurrentDeck.has(name) && !heroInCurrentDeck.has(name) && variants.evolved_or_hero) {
        candidates.push('evolved_or_hero')
      }
      if (candidates.length === 0) return null
      const best = candidates.reduce((a, b) => (variants[b].win_rate_pct > variants[a].win_rate_pct ? b : a))
      return { name, kind: best, ...variants[best] }
    })
    .filter(Boolean) as any[]

  const { data: elixirBenchmark, isLoading: elixirBenchmarkLoading } = useQuery({
    queryKey: ['coach-elixir-benchmark', deckNames.join(',')],
    queryFn: () => coachingApi.elixirBenchmark(deckNames),
    enabled: deckNames.length === 8,
  })

  // Real deck history -- every deck this player has actually used, each with
  // its own real win rate/synergy/MVP (see players.py's /decks). Previously
  // only surfaced on Player Lookup; belongs in Coach too since "which of my
  // decks actually performs best" is exactly the kind of question coaching
  // should answer, not just the single currently-equipped deck's health.
  const { data: deckHistoryData, isLoading: deckHistoryLoading } = useQuery({
    queryKey: ['coach-deck-history', searchTag],
    queryFn: () => playersApi.getDeckHistory(searchTag),
    enabled: !!searchTag,
  })

  // "Players with a deck like yours" swap suggestion -- a genuinely new
  // recommendation type (real feedback, 2026-08-20): "if most users are
  // using a certain card for the player's similar strategy and deck maybe
  // recommend that with more win rate or better synergy," rather than only
  // ever describing the player's OWN current cards back to them. Looks
  // through real decks already fetched for this page (what's winning at
  // this player's own arena, and app-wide) for one that shares 7 of the
  // current deck's 8 cards -- i.e. exactly one single-card swap -- with a
  // meaningfully better real win rate than the player's own tracked result
  // with this exact deck (falls back to a flat 55% bar if that deck hasn't
  // been played enough to have its own tracked win rate yet).
  const myTrackedDeck = (deckHistoryData?.decks ?? [])
    .find((d: any) => d.cards?.length === deckNames.length && d.cards.every((n: string) => deckNames.includes(n)))
  const similarDeckSwap = (() => {
    if (deckNames.length !== 8) return null
    const pool = [...(currentArenaDecks?.decks ?? []), ...(metaPulse?.decks ?? [])]
    const mySet = new Set(deckNames)
    const winRateThreshold = (myTrackedDeck?.win_rate ?? 52) + 3
    let best: { addCard: string; removeCard: string; winRate: number } | null = null
    for (const d of pool) {
      const theirCards: string[] = d.cards ?? []
      if (theirCards.length !== 8) continue
      const theirSet = new Set(theirCards)
      const removeCard = deckNames.find(n => !theirSet.has(n))
      const addCards = theirCards.filter(n => !mySet.has(n))
      if (!removeCard || addCards.length !== 1 || d.win_rate == null) continue
      if (d.win_rate > winRateThreshold && (!best || d.win_rate > best.winRate)) {
        best = { addCard: addCards[0], removeCard, winRate: d.win_rate }
      }
    }
    return best
  })()

  // "Your Strongest Deck" -- real feedback (2026-08-22): "give me a deck
  // that involves those cards across my deck for the counter of my
  // opponents 25 games, a favourite cards deck but with higher win rates
  // and possible strategies to climb." Built entirely from real data
  // already on this page, no invented scoring:
  //  1. Your own most-played cards, weighted by real times_played across
  //     your tracked deck history -- "favorite" in the literal sense of
  //     what you actually keep playing, not a guess.
  //  2. The single real deck you've actually played with the best real win
  //     rate, among ones that use most of those favorite cards (falls back
  //     to your best deck overall if none clears that bar).
  //  3. The single card you've faced most across your recent real battles
  //     -- the API itself only returns ~25 recent battles per player,
  //     matching "your opponents 25 games" almost exactly -- as the basis
  //     for a real counter suggestion (same decksApi.counter already used
  //     for Loss Patterns above, just against a different representative deck).
  const favoriteCards = (() => {
    const freq: Record<string, number> = {}
    for (const d of deckHistoryData?.decks ?? []) {
      for (const c of d.cards ?? []) freq[c] = (freq[c] ?? 0) + (d.times_played ?? 1)
    }
    return Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([name]) => name)
  })()
  const bestFavoriteDeck = (() => {
    const decks = deckHistoryData?.decks ?? []
    if (decks.length === 0) return null
    const withFavorites = decks
      .map((d: any) => ({ ...d, favoriteOverlap: (d.cards ?? []).filter((c: string) => favoriteCards.includes(c)).length }))
      .filter((d: any) => d.favoriteOverlap >= Math.min(3, favoriteCards.length))
      .sort((a: any, b: any) => (b.win_rate ?? 0) - (a.win_rate ?? 0))
    return withFavorites[0] ?? [...decks].sort((a: any, b: any) => (b.win_rate ?? 0) - (a.win_rate ?? 0))[0] ?? null
  })()
  const mostFacedOpponentCard = (() => {
    const freq: Record<string, number> = {}
    for (const b of battlesData?.battles ?? []) {
      for (const c of b.opponent_deck ?? []) freq[c] = (freq[c] ?? 0) + 1
    }
    const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1])
    return sorted[0] as [string, number] | undefined
  })()
  const representativeFacedDeck = (battlesData?.battles ?? [])
    .find((b: any) => b.opponent_deck?.includes(mostFacedOpponentCard?.[0]))?.opponent_deck as string[] | undefined
  const loadFavDeckCounters = async () => {
    if (representativeFacedDeck) setFavDeckCounters(await decksApi.counter(representativeFacedDeck))
  }

  // Same real data as before, reshaped into swipeable cards instead of a
  // wall of paragraphs -- each tip now SHOWS the card it's about (real
  // feedback: "if vines is the weakest link, show the vines card rather
  // than writing all this down"). Deck-level stats with no single card to
  // feature (elixir benchmark, level comparison) just render without one.
  //
  // Real bug found via Playwright (2026-08-20): the 4 queries these tips
  // depend on (card profiles, synergy network, elixir benchmark, arena
  // cards) resolve at different real times, so quickTips used to get built
  // and rendered PARTIALLY on an early render (e.g. only the synergy/elixir/
  // level tips, since those happened to resolve first), then have the
  // card-profile-dependent tips (MVP, Weakest Link, ...) prepended in front
  // a moment later once that query settled. React kept the earlier tips'
  // DOM nodes (stable `id` keys) and just moved them later in the row, and
  // the browser's CSS Scroll Snap re-snapped the container to keep the
  // already-visible card in view -- so the carousel would silently jump
  // away from the true first tip to whatever used to be first, on a
  // majority of real page loads. Waiting for every contributing query to
  // settle before building/rendering quickTips at all means it only ever
  // appears once, fully-formed, in its final order -- no reordering, no
  // jump, confirmed via a real repeat-load Playwright check.
  const quickTipsLoading = deckNames.length === 8
    && (cardProfilesLoading || synergyLoading || elixirBenchmarkLoading || arenaCardsLoading
      || currentArenaDecksLoading || metaPulseLoading || deckHistoryLoading)
  const quickTips: Tip[] = []
  if (deckMvp) {
    quickTips.push({
      id: 'mvp', icon: '★', label: 'Your MVP', accentClass: 'text-gold',
      cards: [deckMvp.name], imageFor, rarityFor, onCardClick: openCard,
      caption: `${deckMvp.live_stats.win_rate}% real win rate across all collected games.`,
    })
  }
  if (deckWeakLink && deckWeakLink.name !== deckMvp?.name) {
    quickTips.push({
      id: 'weak-link', icon: '⚠', label: 'Weakest Link', accentClass: 'text-yellow-400',
      cards: [deckWeakLink.name], imageFor, rarityFor, onCardClick: openCard,
      caption: `${deckWeakLink.live_stats.win_rate}% real win rate -- the softest link in your deck right now.`,
    })
  }
  for (const t of evoHeroActionableTips) {
    quickTips.push({
      id: `evohero-${t.name}-${t.kind}`, icon: t.kind === 'hero' ? '★' : t.kind === 'evolved_or_hero' ? '?' : '⬆',
      label: t.kind === 'hero' ? 'Hero Available' : t.kind === 'evolved_or_hero' ? 'Evolve or Hero' : 'Evolution Available',
      accentClass: 'text-purple-300', cards: [t.name], imageFor, rarityFor, onCardClick: openCard,
      caption: `You own the shards for this -- real players who use it as ${t.kind === 'hero' ? 'Hero' : t.kind === 'evolved_or_hero' ? 'Evolution or Hero' : 'Evolution'} win ${t.win_rate_pct}% of the time. It isn't slotted that way in your current deck.`,
    })
  }
  if (similarDeckSwap) {
    quickTips.push({
      id: 'similar-swap', icon: '🔁', label: 'Try This Swap', accentClass: 'text-cyan-300',
      cards: [similarDeckSwap.addCard], imageFor, rarityFor, onCardClick: openCard,
      caption: `Players with a deck like yours run ${similarDeckSwap.addCard} instead of ${similarDeckSwap.removeCard} -- ${similarDeckSwap.winRate}% real win rate.`,
    })
  }
  if (bestSynergyPair && bestSynergyPair.score > 0) {
    quickTips.push({
      id: 'best-synergy', icon: '🔗', label: 'Best Pairing', accentClass: 'text-cyan-300',
      cards: [bestSynergyPair.a, bestSynergyPair.b], imageFor, rarityFor, onCardClick: openCard,
      caption: `Synergy score ${bestSynergyPair.score} -- these two perform above average together in real games.`,
    })
  }
  if (weakestSynergyPair && !(weakestSynergyPair.a === bestSynergyPair?.a && weakestSynergyPair.b === bestSynergyPair?.b)) {
    quickTips.push({
      id: 'weak-synergy', icon: '🔗', label: 'Weakest Pairing', accentClass: 'text-yellow-400',
      cards: [weakestSynergyPair.a, weakestSynergyPair.b], imageFor, rarityFor, onCardClick: openCard,
      caption: `Synergy score ${weakestSynergyPair.score} -- these two underperform together in real games.`,
    })
  }
  if (elixirBenchmark?.avg_elixir_leaked != null) {
    quickTips.push({
      id: 'elixir-benchmark', icon: '💧', label: 'Elixir Benchmark', accentClass: 'text-accent',
      imageFor, rarityFor,
      caption: `Real ${elixirBenchmark.archetype} decks average ${elixirBenchmark.avg_elixir_leaked} elixir leaked/game`
        + (avgElixirLeaked != null ? ` -- you're averaging ${avgElixirLeaked.toFixed(1)}.` : '.'),
    })
  }
  if (myDeckAvgLevel != null && currentArenaCards?.arena_avg_level != null) {
    quickTips.push({
      id: 'card-levels', icon: '📊', label: 'Card Levels', accentClass: 'text-accent',
      imageFor, rarityFor,
      caption: `Your deck averages level ${myDeckAvgLevel} vs ${currentArenaCards.arena_avg_level} for real players at ${arenaInfo?.arena}`
        + (myDeckAvgLevel < currentArenaCards.arena_avg_level ? ' -- you may be under-leveled for this bracket.'
          : myDeckAvgLevel > currentArenaCards.arena_avg_level ? ' -- you are ahead on levels for this bracket.' : ' -- right in line.'),
    })
  }

  return (
    <div className="relative z-10 max-w-5xl mx-auto px-4 py-6">
      <Backdrop density={10} />
      <PageArtBackdrop imageUrl={coachArtUrl} accent={COACH_ACCENT} />
      <h1 className="text-2xl flex items-baseline gap-2 mb-1">
        <span className="font-display tracking-wide" style={{ color: COACH_ACCENT }}>🎓 Coach</span>
      </h1>
      <p className="text-text-secondary text-sm mb-6">
        Personal coaching built entirely from your real profile, real battle history, and the live meta.
      </p>

      {/* Real feedback (2026-08-26): "Remove player tag search bar for all
          features inside the app and add a universal search bar for it" --
          see PlayerPage.tsx's identical comment. Only the optional API key
          setting remains here. */}
      <Collapsible title="⚙ Using your own CR API key? (optional)" defaultOpen={false}>
        <input value={apiKey} onChange={e => { setApiKey(e.target.value); if (e.target.value) localStorage.setItem('cr_api_key', e.target.value) }}
          type="password" placeholder="CR API Key (optional)"
          className="w-full max-w-sm bg-bg-card border border-border rounded-xl px-4 py-2.5
          text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent text-sm"/>
        <p className="text-text-muted text-xs mt-2">
          Only needed if you're hitting rate limits and want to use your own (get one at developer.clashroyale.com).
        </p>
      </Collapsible>

      {/* Real feedback (2026-08-27): "Coach has top player behaviors as
          default and other informative stuff that can kind of coach the
          player" -- before this, everything below (including the glossary
          and general meta pulse, both real and genuinely useful without a
          specific player) was gated behind a real player search. Real
          strategy content that doesn't need personal data shouldn't wait
          for one. */}
      {!searchTag && (
        <div className="mt-4 space-y-5">
          <NoPlayerYet context="coach" />
          {metaPulse?.decks?.length > 0 && (
            <Collapsible tempting icon="📈" title="Top Real Decks Winning Right Now" accent="gold" persistKey="coach-top-decks-preview"
              teaser="See the live meta before you even look up a player">
              <p className="text-text-muted text-xs mb-3">
                What's actually working across every real collected battle -- look up your own player tag above for personalized coaching on top of this.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {metaPulse.decks.slice(0, 4).map((d: any, i: number) => (
                  <ArenaDeckCard key={i} d={d} imageFor={imageFor} rarityFor={rarityFor}
                    evolutionImageFor={evolutionImageFor} heroImageFor={heroImageFor} />
                ))}
              </div>
            </Collapsible>
          )}
          <ConceptsGlossary />
        </div>
      )}

      {isLoading && <SkeletonLoader label="Loading your profile..." />}
      {error && (
        <div className="text-center py-12">
          <p className="text-text-primary font-medium mb-1">{friendlyPlayerError(error)}</p>
          <p className="text-text-muted text-xs">Double-check the tag (including the #) and try again.</p>
        </div>
      )}

      {data && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-5">
          <div className="bg-bg-surface border border-border rounded-xl p-4 flex items-center justify-between">
            <div>
              <div className="text-lg font-bold text-white">{data.name}</div>
              <div className="text-text-muted text-xs">{data.tag} · 🏆 {data.trophies?.toLocaleString()} (best {data.best_trophies?.toLocaleString()})</div>
            </div>
            {arenaInfo && <div className="text-xs text-cyan-300">{arenaInfo.arena}</div>}
          </div>

          {/* Current-arena real meta -- fast stand-in for "what top players in
              your arena play," built from real aggregated battles rather than
              slow live per-player lookups */}
          {currentArenaDecksLoading && (
            <div className="bg-bg-surface border border-border rounded-xl p-5">
              <SectionSkeleton rows={2} label="Loading your arena's real decks..." />
            </div>
          )}
          {currentArenaDecks?.decks?.length > 0 && (
            <Collapsible tempting icon="🏟️" title={`What's Winning at ${arenaInfo?.arena} Right Now`} accent="gold" persistKey="coach-arena-decks"
              teaser="Real decks other players in your own arena are using">
              <p className="text-text-muted text-xs mb-3">Real decks from real battles at your arena -- swipe or use the arrows to go through them one at a time.</p>
              <ArenaDeckSortButtons sortBy={currentArenaSort} onChange={setCurrentArenaSort} />
              <SwipeCarousel items={currentArenaDecks.decks} keyFor={(_d, i) => i}>
                {(d: any) => (
                  <div className="px-0.5">
                    <ArenaDeckCard d={d} imageFor={imageFor} rarityFor={rarityFor}
                      evolutionImageFor={evolutionImageFor} heroImageFor={heroImageFor} />
                  </div>
                )}
              </SwipeCarousel>
            </Collapsible>
          )}

          {/* 1. Deck Health */}
          {deckHealth && (
            <Collapsible title="Deck Health Check" accent="royale" persistKey="coach-deck-health" defaultOpen>
              <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
                <DeckStatsInline cards={deckNames} />
                <CopyDeckButton cards={deckNames} />
              </div>
              <div className="grid grid-cols-4 sm:grid-cols-8 gap-2 mb-3">
                {deckNames.map(n => (
                  <CardImage key={n} name={n} imageUrl={imageFor(n)} rarity={rarityFor(n)} onClick={() => openCard(n)}
                    evolutionImageUrl={evolutionImageFor(n)} heroImageUrl={heroImageFor(n)}
                    isEvolved={evolvedInCurrentDeck.has(n)} isHero={heroInCurrentDeck.has(n)}
                    isAmbiguous={ambiguousInCurrentDeck.has(n)}
                    level={levelByName[n]} size="sm" />
                ))}
              </div>
              <div className={`grid ${avgElixirLeaked != null ? 'grid-cols-3' : 'grid-cols-2'} gap-2 mb-3`}>
                <div className="bg-bg-card rounded-lg p-2 text-center">
                  <div className="text-accent font-bold">{deckHealth.avg_elixir}</div>
                  <div className="text-text-muted text-xs">Avg Elixir</div>
                </div>
                <div className="bg-bg-card rounded-lg p-2 text-center" title="Combined elixir cost of the 4 cheapest cards in this deck -- lower means faster cycling back to your win condition">
                  <div className="text-accent font-bold">{deckHealth.cycle_cost}</div>
                  <div className="text-text-muted text-xs">Cycle Cost</div>
                </div>
                {avgElixirLeaked != null && (
                  <div className="bg-bg-card rounded-lg p-2 text-center">
                    <div className="text-accent font-bold">{avgElixirLeaked.toFixed(1)}</div>
                    <div className="text-text-muted text-xs">Avg Elixir Leaked ({elixirLeakedBattles.length} real battles)</div>
                  </div>
                )}
              </div>
              {deckHealth.warnings?.map((w: string, i: number) => (
                <div key={i} className="text-xs text-yellow-400 bg-yellow-400/10 rounded-lg p-2 mb-1">{w}</div>
              ))}
            </Collapsible>
          )}

          {/* My Decks -- every real deck this player has used, not just their
              single currently-equipped one, each with a real win rate,
              synergy score, and MVP card so they can see which of their own
              decks is actually working best. */}
          {deckHistoryLoading && (
            <div className="bg-bg-surface border border-border rounded-xl p-5">
              <SectionSkeleton rows={2} label="Loading your real deck history..." />
            </div>
          )}
          {deckHistoryData?.decks?.length > 0 && (
            <div ref={myDecksTopRef}>
            <Collapsible title={`Your Decks (${deckHistoryData.decks.length})`} accent="royale" persistKey="coach-your-decks" defaultOpen>
              <p className="text-text-muted text-xs mb-3">
                Every deck you've actually played across your collected battle history -- if one of these beats your
                current deck's win rate, that's a real signal worth switching to. A deck played with a Hero/Evolved
                card counts as a different real deck from the same 8 cards played regular.
              </p>
              <div className="flex flex-wrap gap-1 mb-3">
                {([
                  ['win_rate', 'Highest Win Rate'],
                  ['times_played', 'Most Played'],
                  ['synergy_score', 'Best Synergy'],
                ] as const).map(([key, label]) => (
                  <button key={key} onClick={() => { setMyDecksSort(key); setMyDecksPage(1) }}
                    className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors
                      ${myDecksSort === key ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
                    {label}
                  </button>
                ))}
              </div>
              <Pagination page={myDecksPage} pageSize={MY_DECKS_PAGE_SIZE} total={deckHistoryData.decks.length}
                onPageChange={setMyDecksPage} scrollTargetRef={myDecksTopRef} className="mb-3" />
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {[...deckHistoryData.decks].sort((a: any, b: any) => (b[myDecksSort] ?? 0) - (a[myDecksSort] ?? 0))
                  .slice((myDecksPage - 1) * MY_DECKS_PAGE_SIZE, myDecksPage * MY_DECKS_PAGE_SIZE)
                  .map((d: any, i: number) => (
                  <div key={i} className="bg-bg-card rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-text-muted">{d.wins != null ? `${d.wins}W / ${d.times_played}` : d.times_played} games · avg {d.avg_elixir} elixir</span>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-cyan-300">{d.win_rate}% WR</span>
                        <FavoriteButton deck={{
                          cards: d.cards, label: `${data.name}'s Deck`, win_rate: d.win_rate, wins: d.wins, frequency: d.times_played,
                          avg_elixir: d.avg_elixir, cycle_cost: d.cycle_cost, synergy_score: d.synergy_score, mvp_card: d.mvp_card,
                          evolved_cards: d.evolved_cards, hero_cards: d.hero_cards, ambiguous_cards: d.ambiguous_cards,
                          typical_tower_troop: d.typical_tower_troop, tower_troop_rate_pct: d.tower_troop_rate_pct,
                          tower_troop_win_rate_pct: d.tower_troop_win_rate_pct, tower_troop_image_url: d.tower_troop_image_url,
                        }} size={14} />
                      </div>
                    </div>
                    <div className="text-[10px] text-text-muted mb-2">
                      <span title="Combined elixir cost of the 4 cheapest cards in this deck -- lower means faster cycling back to your win condition">⚡ Cycle {d.cycle_cost}</span>
                      {d.synergy_score != null && <> · <span title="Average real card-pairing synergy across this deck's cards, from how those pairs have actually performed together in collected battles -- higher is better">🔗 Synergy {d.synergy_score}</span></>}
                      {d.mvp_card && <> · <span className="text-gold">★ MVP: {d.mvp_card}</span></>}
                    </div>
                    <div className="grid grid-cols-4 sm:grid-cols-8 gap-0.5">
                      {d.cards.map((name: string) => (
                        <CardImage key={name} name={name} imageUrl={imageFor(name)} rarity={rarityFor(name)} size="xs" showName={false}
                          evolutionImageUrl={evolutionImageFor(name)} heroImageUrl={heroImageFor(name)} onClick={() => openCard(name)}
                          isEvolved={d.evolved_cards?.includes(name)} isHero={d.hero_cards?.includes(name)}
                          isAmbiguous={d.ambiguous_cards?.includes(name)} />
                      ))}
                    </div>
                    {!d.variant_known && (
                      <div className="text-[10px] text-text-muted italic mt-1">Evolution/Hero data not available for these older battles</div>
                    )}
                    <TowerTroopSection d={d} />
                  </div>
                ))}
              </div>
              <Pagination page={myDecksPage} pageSize={MY_DECKS_PAGE_SIZE} total={deckHistoryData.decks.length}
                onPageChange={setMyDecksPage} scrollTargetRef={myDecksTopRef} />
            </Collapsible>
            </div>
          )}

          {/* "Your Strongest Deck" -- real feedback (2026-08-22): "give me a
              deck that involves those cards across my deck for the counter
              of my opponents 25 games, a favourite cards deck but with
              higher win rates and possible strategies to climb." See the
              favoriteCards/bestFavoriteDeck/mostFacedOpponentCard block
              above for exactly how this is computed (all real, no invented
              scoring). */}
          {bestFavoriteDeck && (
            <div className="bg-bg-surface border border-royale/40 rounded-xl p-5">
              <div className="flex items-center justify-between mb-1">
                <h3 className="font-semibold text-royale">🌟 Your Strongest Deck</h3>
                <FavoriteButton deck={{
                  cards: bestFavoriteDeck.cards, label: `${data.name}'s Strongest Deck`,
                  win_rate: bestFavoriteDeck.win_rate, wins: bestFavoriteDeck.wins, frequency: bestFavoriteDeck.times_played,
                  avg_elixir: bestFavoriteDeck.avg_elixir, cycle_cost: bestFavoriteDeck.cycle_cost,
                  synergy_score: bestFavoriteDeck.synergy_score, mvp_card: bestFavoriteDeck.mvp_card,
                  evolved_cards: bestFavoriteDeck.evolved_cards, hero_cards: bestFavoriteDeck.hero_cards,
                  ambiguous_cards: bestFavoriteDeck.ambiguous_cards,
                  typical_tower_troop: bestFavoriteDeck.typical_tower_troop, tower_troop_rate_pct: bestFavoriteDeck.tower_troop_rate_pct,
                  tower_troop_win_rate_pct: bestFavoriteDeck.tower_troop_win_rate_pct, tower_troop_image_url: bestFavoriteDeck.tower_troop_image_url,
                }} size={16} />
              </div>
              <p className="text-text-muted text-xs mb-3">
                Your best real win rate ({bestFavoriteDeck.win_rate}%, {bestFavoriteDeck.times_played} games) among decks
                built from cards you actually play most{favoriteCards.length > 0 && <>: {favoriteCards.slice(0, 3).join(', ')}</>}.
              </p>
              <div className="grid grid-cols-4 sm:grid-cols-8 gap-1 mb-2">
                {bestFavoriteDeck.cards.map((name: string) => (
                  <CardImage key={name} name={name} imageUrl={imageFor(name)} rarity={rarityFor(name)} size="xs" showName={false}
                    evolutionImageUrl={evolutionImageFor(name)} heroImageUrl={heroImageFor(name)} onClick={() => openCard(name)}
                    isEvolved={bestFavoriteDeck.evolved_cards?.includes(name)} isHero={bestFavoriteDeck.hero_cards?.includes(name)}
                    isAmbiguous={bestFavoriteDeck.ambiguous_cards?.includes(name)} />
                ))}
              </div>
              <TowerTroopSection d={bestFavoriteDeck} />

              {mostFacedOpponentCard && (
                <div className="border-t border-border pt-3 mt-2">
                  <p className="text-text-secondary text-xs mb-2">
                    You've faced <span className="text-danger font-medium">{mostFacedOpponentCard[0]}</span> in{' '}
                    {mostFacedOpponentCard[1]} of your last {battlesData?.battles?.length ?? 0} real games -- here's what
                    beats it, to climb with this deck.
                  </p>
                  <button onClick={loadFavDeckCounters}
                    className="bg-accent hover:bg-accent-hover text-bg-primary font-bold px-4 py-2 rounded-xl text-sm">
                    Show counters for what I'm facing
                  </button>
                </div>
              )}
              {favDeckCounters && (
                <div className="mt-3">
                  <CounterDecksList title="Counters for what you're facing most"
                    deck={representativeFacedDeck ?? []} counters={favDeckCounters} imageFor={imageFor} rarityFor={rarityFor}
                    evolutionImageFor={evolutionImageFor} heroImageFor={heroImageFor} />
                </div>
              )}
            </div>
          )}

          {/* Real feedback (2026-08-23, revised 2026-08-28): "your owned hero
              used deck owned evo used decks, that uses all your evos/heros
              or most of them and also has proper win rate." See the
              ownedVariantDecks query above -- one real card per owned
              Evolution/Hero variant (a real game rule caps any single deck
              to one evolution + one hero slot, so covering "most of" a
              player's collection means several decks, not one). */}
          {((ownedVariantDecks?.topEvoDecks?.length ?? 0) > 0 || (ownedVariantDecks?.topHeroDecks?.length ?? 0) > 0) && (() => {
            const EVO_HERO_PREVIEW_COUNT = 4
            const evoDecks = ownedVariantDecks!.topEvoDecks as any[]
            const heroDecks = ownedVariantDecks!.topHeroDecks as any[]
            const totalDecks = evoDecks.length + heroDecks.length
            const hasMore = totalDecks > EVO_HERO_PREVIEW_COUNT * 2
            const shownEvo = showAllEvoHeroDecks ? evoDecks : evoDecks.slice(0, EVO_HERO_PREVIEW_COUNT)
            const shownHero = showAllEvoHeroDecks ? heroDecks : heroDecks.slice(0, EVO_HERO_PREVIEW_COUNT)
            return (
              <Collapsible tempting icon="🃏" title="Real Decks for Your Evolutions & Heroes" accent="royale" persistKey="coach-evo-hero-decks"
                teaser={`The best deck for each of your ${totalDecks} owned Evolution/Hero variants`}>
                <p className="text-text-muted text-xs mb-3">
                  The best real win-rate deck for each Evolution/Hero variant you actually own shards/unlocks for --
                  {' '}{evoDecks.length} evolution deck{evoDecks.length === 1 ? '' : 's'} and {heroDecks.length} hero deck{heroDecks.length === 1 ? '' : 's'}.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {shownEvo.map((d: any) => (
                    <div key={`evo-${d.deck ?? d.typical_evolution}`}>
                      <div className="text-[10px] font-medium text-cyan-300 mb-1">⬆ Best deck for your {d.typical_evolution} Evolution</div>
                      <ArenaDeckCard d={d} imageFor={imageFor} rarityFor={rarityFor}
                        evolutionImageFor={evolutionImageFor} heroImageFor={heroImageFor} />
                    </div>
                  ))}
                  {shownHero.map((d: any) => (
                    <div key={`hero-${d.deck ?? d.typical_hero}`}>
                      <div className="text-[10px] font-medium text-gold mb-1">★ Best deck for your {d.typical_hero} Hero</div>
                      <ArenaDeckCard d={d} imageFor={imageFor} rarityFor={rarityFor}
                        evolutionImageFor={evolutionImageFor} heroImageFor={heroImageFor} />
                    </div>
                  ))}
                </div>
                {hasMore && (
                  <button onClick={() => setShowAllEvoHeroDecks(v => !v)}
                    className="mt-3 text-xs font-medium text-accent hover:text-accent-hover">
                    {showAllEvoHeroDecks ? 'Show fewer' : `Show ${totalDecks - EVO_HERO_PREVIEW_COUNT * 2} more`}
                  </button>
                )}
              </Collapsible>
            )
          })()}

          {/* Free quick tips -- real per-card win rates + real Evolution/Hero
              usage rates + a real elixir-leak benchmark, all genuinely useful
              on their own without needing the full gated breakdown below.
              Swipeable card-per-tip (2026-08-20, real feedback: "make it a
              fun feature that player can swipe" + "show the card being
              talked about rather than writing all this down") -- see
              TipsCarousel.tsx and the quickTips array built above. */}
          {quickTipsLoading ? (
            <div className="bg-bg-surface border border-royale/40 rounded-xl p-5">
              <h3 className="font-semibold text-royale mb-3">💡 Quick Real-Data Tips</h3>
              <div className="flex gap-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="w-[78%] sm:w-52 h-40 bg-bg-card rounded-xl animate-pulse shrink-0" />
                ))}
              </div>
            </div>
          ) : quickTips.length > 0 && (
            <Collapsible tempting icon="💡" title="Quick Real-Data Tips" accent="royale" persistKey="coach-quick-tips"
              teaser="Real per-card win rates and elixir-leak benchmarks, swipeable">
              <TipsCarousel tips={quickTips} />
            </Collapsible>
          )}

          {/* General meta pulse -- what's winning across ALL real collected
              battles right now, regardless of this player's own arena/deck --
              broader context/inspiration, distinct from the arena-scoped
              "what's winning at your arena" section above. */}
          {metaPulseLoading && (
            <div className="bg-bg-surface border border-border rounded-xl p-5">
              <SectionSkeleton rows={2} label="Loading the live meta..." />
            </div>
          )}
          {metaPulse?.decks?.length > 0 && (
            <Collapsible tempting icon="🌐" title="Meta Pulse: Real Decks Winning Most Right Now" accent="gold" persistKey="coach-meta-pulse"
              teaser="Top real decks app-wide, beyond just your own arena">
              <p className="text-text-muted text-xs mb-3">
                Top real decks app-wide, for inspiration beyond your own arena.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                {metaPulse.decks.map((d: any, i: number) => (
                  <div key={i} className="bg-bg-card rounded-lg p-2">
                    <div className="grid grid-cols-4 sm:grid-cols-8 gap-0.5 mb-1">
                      {d.cards.map((n: string) => (
                        <CardImage key={n} name={n} imageUrl={imageFor(n)} rarity={rarityFor(n)} size="xs" showName={false} onClick={() => openCard(n)} />
                      ))}
                    </div>
                    <div className="text-[10px] text-text-muted">{d.win_rate}% WR · {d.frequency.toLocaleString()} games</div>
                  </div>
                ))}
              </div>
            </Collapsible>
          )}

          {/* 2-5. Loss Patterns / Counters / Trophy Push / Upgrade Priorities --
              the deep-dive coaching, gated behind the planned premium tier */}
          <PremiumGate unlocked={unlocked} onUnlock={unlock}>
          {lossPatterns && lossPatterns.total_losses > 0 && (
            <Collapsible tempting icon="💥" title={`Loss Patterns: Last ${lossPatterns.total_losses} Real Losses`} accent="crimson" persistKey="coach-loss-patterns"
              teaser="What you're actually losing to, ranked by how often">
              <p className="text-text-muted text-xs mb-3">
                From your last {lossPatterns.total_losses} real losses -- what you're actually losing to.
              </p>
              <div className="space-y-1.5 mb-3">
                {lossPatterns.top_archetypes.map((a: any) => (
                  <div key={a.archetype} className="flex items-center justify-between text-sm bg-bg-card rounded-lg px-3 py-2">
                    <span className="text-text-primary">{a.archetype}</span>
                    <span className="text-cyan-300 font-semibold">{a.count} ({a.pct}%)</span>
                  </div>
                ))}
              </div>
              {/* Was one long semicolon-joined sentence ("X beats your Y (3x); A
                  beats your B (2x); ...") -- real feedback: less text, more
                  visual. Small card-icon pairs read at a glance instead. */}
              {lossPatterns.top_hard_counters?.length > 0 && (
                <div className="mb-3">
                  <div className="text-xs font-medium text-danger mb-1.5">Recurring bad matchups</div>
                  <div className="flex flex-col gap-1">
                    {lossPatterns.top_hard_counters.slice(0, 4).map((h: any, i: number) => (
                      <div key={i} className="flex items-center gap-1.5 text-xs bg-bg-card rounded-lg px-2 py-1.5">
                        <CardImage name={h.opponent_card} imageUrl={imageFor(h.opponent_card)} rarity={rarityFor(h.opponent_card)} size="xs" showName={false} />
                        <span className="text-text-muted">beats</span>
                        <CardImage name={h.your_card} imageUrl={imageFor(h.your_card)} rarity={rarityFor(h.your_card)} size="xs" showName={false} />
                        <span className="text-text-muted ml-auto shrink-0">{h.count}x</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <button onClick={loadCounters}
                className="bg-accent hover:bg-accent-hover text-bg-primary font-bold px-4 py-2 rounded-xl text-sm">
                Show counters for this
              </button>
            </Collapsible>
          )}

          {/* 3. Counters */}
          {counters && (
            <CounterDecksList title="Counters for what's beating you"
              deck={representativeLossDeck ?? []} counters={counters} imageFor={imageFor} rarityFor={rarityFor}
              evolutionImageFor={evolutionImageFor} heroImageFor={heroImageFor} />
          )}

          {/* 4. Trophy Push */}
          {arenaInfo && !arenaInfo.next_arena && (
            <div className="bg-bg-surface border border-border rounded-xl p-5 text-center">
              <p className="text-sm text-gold font-semibold">🏆 You've reached the top arena bucket -- nowhere higher to push!</p>
            </div>
          )}
          {arenaInfo?.next_arena && (
            <Collapsible tempting icon="🏆" title={`Trophy Push: ${arenaInfo.arena} → ${arenaInfo.next_arena}`} accent="success" persistKey="coach-trophy-push"
              teaser="What's actually common one arena up, from real battles">
              <p className="text-text-muted text-xs mb-3">What's actually common one arena up, from real battles.</p>
              {nextArenaCards?.cards?.length > 0 && (
                <div className="grid grid-cols-4 sm:grid-cols-6 gap-2 mb-4">
                  {nextArenaCards.cards.slice(0, 12).map((c: any) => (
                    <div key={c.name}>
                      <CardImage name={c.name} imageUrl={c.image_url} rarity={c.rarity} elixir={c.elixir} size="xs" onClick={() => openCard(c.name)} />
                      <div className="text-center text-[9px] text-cyan-300 mt-0.5">{c.win_rate}%</div>
                    </div>
                  ))}
                </div>
              )}
              {nextArenaDecks?.decks?.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-text-secondary mb-2">Real decks up there:</div>
                  <ArenaDeckSortButtons sortBy={nextArenaSort} onChange={setNextArenaSort} />
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {nextArenaDecks.decks.map((d: any, i: number) => (
                      <ArenaDeckCard key={i} d={d} imageFor={imageFor} rarityFor={rarityFor}
                        evolutionImageFor={evolutionImageFor} heroImageFor={heroImageFor} />
                    ))}
                  </div>
                </div>
              )}
            </Collapsible>
          )}

          {/* 5. Card Level Priorities */}
          {levelPriorities.length > 0 && (
            <Collapsible tempting icon="⬆️" title="Upgrade Priorities" accent="success" persistKey="coach-upgrade-priorities"
              teaser="Which of your deck's cards to level up first">
              <p className="text-text-muted text-xs mb-3">Your deck's cards, furthest from max level first -- weigh against real win rate/efficiency yourself.</p>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-2 text-text-muted font-medium text-xs">Card</th>
                    <th className="text-right py-2 text-text-muted font-medium text-xs">Levels to Max</th>
                    <th className="text-right py-2 text-text-muted font-medium text-xs">Real Win Rate</th>
                    <th className="text-right py-2 text-text-muted font-medium text-xs">Efficiency</th>
                  </tr>
                </thead>
                <tbody>
                  {levelPriorities.map((p: any) => (
                    <tr key={p.name} className="border-b border-border/50">
                      <td className="py-1.5"><CardName name={p.name} rarity={rarityFor(p.name)} className="text-sm" /></td>
                      <td className="py-1.5 text-right text-text-secondary">{p.levels_to_max ?? '—'}</td>
                      <td className="py-1.5 text-right text-cyan-300">{p.live_stats?.win_rate != null ? `${p.live_stats.win_rate}%` : '—'}</td>
                      <td className="py-1.5 text-right text-accent">{p.efficiency ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Collapsible>
          )}
          </PremiumGate>

          <ConceptsGlossary />
        </motion.div>
      )}
    </div>
  )
}
