import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ScatterChart, Scatter, ZAxis } from 'recharts'
import { cardsApi, mlApi, metaApi, Card } from '../utils/api'
import CardImage, { CardName } from '../components/CardImage'
import DataHealthBanner from '../components/DataHealthBanner'
import { useCardDetail } from '../contexts/CardDetailContext'
import Collapsible from '../components/Collapsible'
import Backdrop from '../components/Backdrop'
import FavoriteButton from '../components/FavoriteButton'
import TowerTroopSection from '../components/TowerTroopSection'
import StrategyPicker from '../components/StrategyPicker'
import Pagination from '../components/Pagination'
import { useTabParam } from '../utils/useTabParam'
import { formatStrategy } from '../utils/formatStrategy'

export default function AnalyticsPage() {
  const navigate = useNavigate()
  // Real feedback (2026-08-27): "win predictor should not be part of
  // analytics right? maybe part of build and analyze" -- moved to
  // DeckLabPage.tsx (/build?tab=predictor), redesigned there into a real
  // multi-deck comparison instead of a fixed Deck A/Deck B pair. Old
  // ?tab=predict links/bookmarks redirect there instead of silently
  // landing on nothing.
  const [tab, setTab] = useTabParam<'meta' | 'arena' | 'decks' | 'evolution' | 'predict' | 'value'>('meta')
  useEffect(() => {
    if (tab === 'predict') navigate('/build?tab=predictor', { replace: true })
  }, [tab, navigate])

  return (
    <div className="relative z-10 max-w-6xl mx-auto px-4 py-6">
      <Backdrop density={8} />
      <h1 className="text-2xl font-bold text-accent mb-1">Analytics</h1>
      <p className="text-text-secondary text-sm mb-4">
        Meta trends, top decks, and card value -- all from real, live-collected battles.
      </p>

      <DataHealthBanner />

      <div className="flex gap-1 mb-5 flex-wrap">
        {([
          ['meta', '📊 Meta Trends'],
          ['arena', '🏟 By Arena'],
          ['decks', '🃏 Top Decks'],
          ['evolution', '⬆ Evolution & Hero'],
          ['value', '💎 Card Value'],
        ] as const).map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors
              ${tab === t ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'meta' && <MetaTab />}
      {tab === 'arena' && <ArenaTab />}
      {tab === 'decks' && <DecksTab />}
      {tab === 'evolution' && <EvolutionUsageTab />}
      {tab === 'value' && <CardValueTab />}
    </div>
  )
}

function ArenaTab() {
  const [selectedArena, setSelectedArena] = useState<string | null>(null)
  const { openCard } = useCardDetail()
  const { data: arenasData } = useQuery({ queryKey: ['arenas'], queryFn: () => metaApi.arenas() })
  const arenas: string[] = arenasData?.arenas ?? []

  const { data: arenaCardsData, isLoading } = useQuery({
    queryKey: ['arena-cards', selectedArena],
    queryFn: () => metaApi.arenaCards(selectedArena!),
    enabled: !!selectedArena,
  })

  return (
    <div>
      <p className="text-text-secondary text-sm mb-1">
        Pick an arena to see its most-used cards from real, current battles.
      </p>
      <p className="text-text-muted text-xs mb-3">
        ⚠ Trophy count alone doesn't reliably show what an account has unlocked -- veteran players pass through low
        trophy ranges constantly (season resets, deliberate trophy-dropping), bringing fully-leveled decks with
        them, which is why late-unlocking cards can still appear in early arenas. Battles collected from here on
        also capture average card level and filter out obvious veteran accounts from low arenas, but that can only
        improve accuracy going forward, not retroactively -- check the average level shown below against what a
        real new player would have.
      </p>
      <div className="flex flex-wrap gap-1 mb-5 max-h-40 overflow-y-auto pr-1">
        {arenas.map(arena => (
          <button key={arena} onClick={() => setSelectedArena(arena)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
              ${selectedArena === arena ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
            {arena}
          </button>
        ))}
      </div>

      {!selectedArena ? (
        <div className="bg-bg-surface border border-border rounded-xl p-6 text-center">
          <p className="text-text-secondary text-sm">Select an arena above to see its most-used cards.</p>
        </div>
      ) : isLoading ? (
        <div className="h-64 bg-bg-surface rounded-xl animate-pulse" />
      ) : arenaCardsData?.cards?.length > 0 ? (
        <div className="bg-bg-surface border border-cyan-400/30 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-white">{selectedArena}</h3>
            {arenaCardsData?.arena_avg_level != null && (
              <span className="text-xs text-text-muted">Avg card level here: <span className="text-cyan-300 font-semibold">{arenaCardsData.arena_avg_level}</span></span>
            )}
          </div>
          <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-2 max-h-96 overflow-y-auto pr-1">
            {arenaCardsData.cards.map((c: any) => (
              <div key={c.name} onClick={() => openCard(c.name)} className="cursor-pointer">
                <CardImage name={c.name} imageUrl={c.image_url} rarity={c.rarity} elixir={c.elixir} size="sm" />
                <div className="text-center text-[10px] text-cyan-300 mt-0.5">{c.win_rate}% WR</div>
                <div className="text-center text-[9px] text-text-muted">{c.times_used}x</div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="bg-bg-surface border border-border rounded-xl p-6 text-center">
          <p className="text-text-secondary text-sm">
            {arenaCardsData?.note ?? 'No battles seen yet for this arena.'}
          </p>
        </div>
      )}
    </div>
  )
}

const META_PAGE_SIZE = 25

function MetaTab() {
  const [sortBy, setSortBy] = useState<'win_rate' | 'presence_rate'>('win_rate')
  const [page, setPage] = useState(1)
  const { openCard } = useCardDetail()

  const { data: cardsData, isLoading, isError } = useQuery({
    queryKey: ['meta-cards', sortBy],
    queryFn: () => metaApi.topCards(sortBy, 200),
  })
  const pageCards = (cardsData?.cards ?? []).slice((page - 1) * META_PAGE_SIZE, page * META_PAGE_SIZE)

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-white">🔴 Live Meta (growing)</h2>
        <div className="flex gap-1">
          {(['win_rate', 'presence_rate'] as const).map(s => (
            <button key={s} onClick={() => { setSortBy(s); setPage(1) }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
                ${sortBy === s ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
              {s === 'win_rate' ? 'Win Rate' : 'Presence Rate'}
            </button>
          ))}
        </div>
      </div>
      {cardsData?.collection && (
        <p className="text-text-secondary text-xs mb-3">
          {cardsData.collection.total_battles.toLocaleString()} real battles collected ·{' '}
          {cardsData.collection.unique_players + cardsData.collection.unique_opponents} players seen ·{' '}
          {cardsData.collection.unique_decks_seen?.toLocaleString()} unique decks seen ·{' '}
          {cardsData.collection.earliest?.slice(0, 8)}–{cardsData.collection.latest?.slice(0, 8)}
        </p>
      )}

      {isLoading ? (
        <div className="h-64 bg-bg-surface rounded-xl animate-pulse mb-8" />
      ) : isError ? (
        // Real bug fixed (2026-09-09): a failed request used to fall through
        // to the "not enough collected battles" branch below (cardsData is
        // undefined either way), which is honestly misleading -- there's
        // real data, the request just failed. Says so plainly instead.
        <div className="bg-bg-surface border border-danger/30 rounded-xl p-6 text-center mb-8">
          <p className="text-text-primary text-sm font-medium mb-1">Couldn&apos;t load the live meta right now.</p>
          <p className="text-text-muted text-xs">This is a real request failure, not a lack of data — try refreshing.</p>
        </div>
      ) : cardsData?.cards?.length > 0 ? (
        <div className="bg-bg-surface border border-cyan-400/30 rounded-xl p-4 mb-8">
          <p className="text-text-muted text-xs mb-2">
            Showing all {cardsData.cards.length} cards with live data · click a row for full stats, evolution &amp; hero details.
          </p>
          <Pagination page={page} pageSize={META_PAGE_SIZE} total={cardsData.cards.length} onPageChange={setPage} className="mb-2" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 text-text-muted font-medium text-xs">Card</th>
                  <th className="text-left py-2 text-text-muted font-medium text-xs">Rarity</th>
                  <th className="text-right py-2 text-text-muted font-medium text-xs">Elixir</th>
                  <th className="text-right py-2 text-text-muted font-medium text-xs">Win Rate</th>
                  <th className="text-right py-2 text-text-muted font-medium text-xs">Presence</th>
                  <th className="text-right py-2 text-text-muted font-medium text-xs">Times Used</th>
                </tr>
              </thead>
              <tbody>
                {pageCards.map((c: any) => (
                  <tr key={c.name} onClick={() => openCard(c.name)}
                    className="border-b border-border/50 hover:bg-bg-card/50 cursor-pointer">
                    {/* flex-wrap: without it, a card with BOTH badges (the 4
                        dual-capable cards) doesn't have room to stay on one
                        line on a narrow viewport -- confirmed via a real
                        mobile-viewport sweep that the HERO badge was
                        overflowing this cell and rendering on top of the
                        Rarity column's text next to it. Wrapping lets the
                        badges drop to a second line inside this same cell
                        instead of spilling into the neighbor. */}
                    <td className="py-1.5 text-text-primary font-medium flex items-center flex-wrap gap-1.5 gap-y-0.5">
                      {c.image_url && <img src={c.image_url} alt="" className="w-6 h-6 object-contain shrink-0" />}
                      <CardName name={c.name} rarity={c.rarity} className="text-sm" />
                      {c.has_evolution && <span className="text-[9px] px-1 rounded bg-cyan-400/20 text-cyan-300 shrink-0">EVO</span>}
                      {c.has_hero && <span className="text-[9px] px-1 rounded bg-gold/20 text-gold shrink-0">HERO</span>}
                    </td>
                    <td className="py-1.5 text-text-secondary text-xs">{c.rarity ?? '—'}</td>
                    <td className="py-1.5 text-right text-text-secondary">{c.elixir ?? '—'}</td>
                    <td className="py-1.5 text-right text-cyan-300">{c.win_rate}%</td>
                    <td className="py-1.5 text-right text-text-secondary">{c.presence_rate}%</td>
                    <td className="py-1.5 text-right text-text-secondary">{c.times_used}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={META_PAGE_SIZE} total={cardsData.cards.length} onPageChange={setPage} />
        </div>
      ) : (
        <div className="bg-bg-surface border border-border rounded-xl p-6 text-center mb-8">
          <p className="text-text-secondary text-sm">
            {cardsData?.note ?? 'Not enough collected battles yet for a live view (need 500+).'} Keep using Player
            Lookup, or run <code className="text-cyan-300">scripts/crawl_battles.py</code>, to grow it.
          </p>
        </div>
      )}
    </div>
  )
}

const DECK_SORTS = [
  ['frequency', '🔥 Most Played'],
  ['win_rate', '🏆 Highest Win Rate'],
  ['cycle_cost', '⚡ Cheapest Cycle'],
  ['synergy_score', '🔗 Best Synergy'],
] as const

const VARIANT_FILTER_OPTIONS = [
  ['regular', 'Regular'],
  ['evolution', '⬆ Evolved'],
  ['hero', '★ Hero'],
  ['evolved_or_hero', "? Evo or Hero"],
] as const

function DecksTab() {
  const { openCard } = useCardDetail()
  const [arena, setArena] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<typeof DECK_SORTS[number][0]>('frequency')
  const [filterCard, setFilterCard] = useState<string>('')
  const [filterVariant, setFilterVariant] = useState<typeof VARIANT_FILTER_OPTIONS[number][0] | null>(null)
  const [strategy, setStrategy] = useState<string>('')
  const [page, setPage] = useState(1)
  const { data: arenasData } = useQuery({ queryKey: ['arenas'], queryFn: () => metaApi.arenas() })
  const { data: strategiesData } = useQuery({ queryKey: ['deck-strategies'], queryFn: () => metaApi.deckStrategies() })
  const { data, isLoading } = useQuery({
    queryKey: ['meta-decks', arena, sortBy, filterCard, filterVariant, strategy, page],
    queryFn: () => metaApi.topDecks(20, arena ?? undefined, sortBy, filterCard || undefined, filterVariant ?? undefined, page, strategy || undefined),
  })
  const { data: allCards } = useQuery({ queryKey: ['cards'], queryFn: () => cardsApi.getAll() })
  const arenas: string[] = arenasData?.arenas ?? []
  const strategies: any[] = strategiesData?.strategies ?? []

  // Any filter/sort change invalidates the current page -- always land back
  // on page 1 rather than potentially showing an out-of-range empty page.
  const setArenaAndResetPage = (v: string | null) => { setArena(v); setPage(1) }
  const setSortByAndResetPage = (v: typeof DECK_SORTS[number][0]) => { setSortBy(v); setPage(1) }
  const setStrategyAndResetPage = (v: string) => { setStrategy(v); setPage(1) }

  const cardFor = (n: string) => allCards?.items?.find((c: Card) => c.name === n)
  const imageFor = (n: string) => cardFor(n)?.image_url
  const rarityFor = (n: string) => cardFor(n)?.rarity

  const filterCardMeta = filterCard ? cardFor(filterCard) : null
  const filterCardHasVariants = !!(filterCardMeta?.has_evolution || filterCardMeta?.has_hero)
  const sortedCardOptions = [...(allCards?.items ?? [])].sort((a: Card, b: Card) => a.name.localeCompare(b.name))

  return (
    <div>
      <p className="text-text-secondary text-sm mb-3">
        Real 8-card decks other players are actually using, from live battles.
      </p>

      <div className="flex flex-wrap gap-1 mb-3">
        {DECK_SORTS.map(([key, label]) => (
          <button key={key} onClick={() => setSortByAndResetPage(key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
              ${sortBy === key ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
            {label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-1 mb-5 max-h-32 overflow-y-auto pr-1">
        <button onClick={() => setArenaAndResetPage(null)}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
            ${arena === null ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
          All Time
        </button>
        {arenas.map(a => (
          <button key={a} onClick={() => setArenaAndResetPage(a)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
              ${arena === a ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
            {a}
          </button>
        ))}
      </div>

      {/* Filter Top Decks down to only decks featuring a specific card (and,
          for Evolution/Hero-capable cards, a specific real variant -- e.g.
          "show me decks where Knight is real-typically Hero'd") or a real
          strategy (primary win condition + flavor, e.g. "Hog Rider (cycle)"). */}
      <div className="bg-bg-surface border border-border rounded-xl p-3 mb-5 flex flex-wrap items-center gap-2">
        <span className="text-xs text-text-muted shrink-0">🔍 Filter by card:</span>
        <select value={filterCard} onChange={e => { setFilterCard(e.target.value); setFilterVariant(null); setPage(1) }}
          className="bg-bg-card border border-border rounded-lg px-2 py-1.5 text-xs text-text-primary focus:outline-none focus:border-accent">
          <option value="">Any card</option>
          {sortedCardOptions.map((c: Card) => (
            <option key={c.name} value={c.name}>{c.name}</option>
          ))}
        </select>
        {filterCard && filterCardHasVariants && (
          <div className="flex flex-wrap gap-1">
            {VARIANT_FILTER_OPTIONS
              .filter(([key]) => key !== 'evolution' || filterCardMeta?.has_evolution)
              .filter(([key]) => key !== 'hero' || filterCardMeta?.has_hero)
              .filter(([key]) => key !== 'evolved_or_hero' || (filterCardMeta?.has_evolution && filterCardMeta?.has_hero))
              .map(([key, label]) => (
                <button key={key} onClick={() => { setFilterVariant(filterVariant === key ? null : key); setPage(1) }}
                  className={`px-2 py-1 rounded-lg text-[11px] font-medium transition-colors
                    ${filterVariant === key ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
                  {label}
                </button>
              ))}
          </div>
        )}
        {filterCard && (
          <button onClick={() => { setFilterCard(''); setFilterVariant(null); setPage(1) }}
            className="text-[11px] text-text-muted hover:text-danger">✕ Clear</button>
        )}

        <span className="text-xs text-text-muted shrink-0 ml-2">🏷 Strategy:</span>
        <div className="w-full sm:w-56">
          <StrategyPicker
            strategies={strategies.map((s: any) => ({ strategy: s.strategy, frequency: s.total_frequency }))}
            value={strategy} onChange={setStrategyAndResetPage} />
        </div>
        {strategy && (
          <button onClick={() => setStrategyAndResetPage('')}
            className="text-[11px] text-text-muted hover:text-danger ml-auto">✕ Clear</button>
        )}
      </div>

      {data?.total > 0 && (
        <Pagination page={page} pageSize={data.page_size ?? 20} total={data.total} onPageChange={setPage} className="mb-3" />
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-40 bg-bg-surface rounded-xl animate-pulse" />)}
        </div>
      ) : data?.decks?.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {data.decks.map((d: any, i: number) => (
            <div key={i} className="bg-bg-surface border border-border rounded-xl p-4">
              {d.strategy && (
                <div className="text-[10px] font-medium text-accent/80 mb-1">🏷 {formatStrategy(d.strategy)}</div>
              )}
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-text-muted">
                  {d.wins != null ? `${d.wins.toLocaleString()}W / ${d.frequency.toLocaleString()}` : d.frequency.toLocaleString()} seen · avg {d.avg_elixir} elixir
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-cyan-300">{d.win_rate}% WR</span>
                  <FavoriteButton deck={{
                    cards: d.cards, label: 'Top Decks', win_rate: d.win_rate, wins: d.wins, frequency: d.frequency,
                    avg_elixir: d.avg_elixir, cycle_cost: d.cycle_cost, synergy_score: d.synergy_score,
                    typical_evolution: d.typical_evolution, typical_hero: d.typical_hero,
                    evolution_rate_pct: d.evolution_rate_pct, hero_rate_pct: d.hero_rate_pct,
                    typical_tower_troop: d.typical_tower_troop, tower_troop_rate_pct: d.tower_troop_rate_pct,
                    tower_troop_win_rate_pct: d.tower_troop_win_rate_pct, tower_troop_image_url: d.tower_troop_image_url,
                  }} />
                </div>
              </div>
              <div className="flex items-center justify-between mb-2 text-[10px] text-text-muted">
                <span>
                  <span title="Combined elixir cost of the 4 cheapest cards in this deck -- lower means faster cycling back to your win condition">⚡ Cycle {d.cycle_cost}</span>
                  {d.synergy_score != null && <> · <span title="Average real card-pairing synergy across this deck's cards, from how those pairs have actually performed together in collected battles -- higher is better">🔗 Synergy {d.synergy_score}</span></>}
                </span>
              </div>
              <div className="grid grid-cols-4 sm:grid-cols-8 gap-1 mb-1">
                {d.cards.map((name: string) => {
                  const card = cardFor(name)
                  return (
                    <div key={name} onClick={() => openCard(name)} className="cursor-pointer">
                      <CardImage name={name} imageUrl={imageFor(name)} rarity={rarityFor(name)} size="xs" showName={false}
                        evolutionImageUrl={card?.evolution_image_url} heroImageUrl={card?.hero_image_url}
                        isEvolved={d.typical_evolution === name} isHero={d.typical_hero === name}
                        isAmbiguous={d.typical_ambiguous === name} />
                    </div>
                  )
                })}
              </div>
              {(d.typical_evolution || d.typical_hero || d.typical_ambiguous || d.typical_tower_troop || d.strategy_games_played != null || d.estimated_win_rate != null) && (
                <Collapsible title="More details" compact>
                  <TowerTroopSection d={d} />
                  {(d.typical_evolution || d.typical_hero || d.typical_ambiguous) && (
                    <div className="text-[10px] text-text-muted mb-1">
                      {d.typical_evolution && <>⬆ {d.typical_evolution} evolved {d.evolution_rate_pct}% of the time</>}
                      {d.typical_evolution && (d.typical_hero || d.typical_ambiguous) && ' · '}
                      {d.typical_hero && <>★ {d.typical_hero} hero'd {d.hero_rate_pct}% of the time</>}
                      {d.typical_hero && d.typical_ambiguous && ' · '}
                      {d.typical_ambiguous && <>? {d.typical_ambiguous} evolved-or-hero'd {d.ambiguous_rate_pct}% of the time</>}
                    </div>
                  )}
                  {/* Reliability: this exact deck's own real win rate is shown up
                      top, but with as few as a handful of real games it's thin
                      evidence on its own -- shown here alongside (never blended
                      into) two more real/estimated numbers: this deck's real
                      strategy pooled across every variant of it, and the Deck
                      Quality Model's composition-based estimate. */}
                  {(d.strategy_games_played != null || d.estimated_win_rate != null) && (
                    <div className="text-[10px] text-text-muted flex flex-wrap gap-x-3 gap-y-0.5">
                      {d.strategy_games_played != null && (
                        <span title="This deck's real win rate, pooled with every other real deck sharing the same strategy (win condition + flavor)">
                          🏷 {formatStrategy(d.strategy)} overall: <span className="text-text-secondary font-medium">{d.strategy_win_rate}%</span> ({d.strategy_games_played.toLocaleString()} games)
                        </span>
                      )}
                      {d.estimated_win_rate != null && (
                        <span title="The Deck Quality Model's composition-based estimate -- learned from well-tested decks, applied here since this exact deck has too few real games to trust on its own">
                          🤖 Model estimate: <span className="text-text-secondary font-medium">{d.estimated_win_rate}%</span>
                        </span>
                      )}
                    </div>
                  )}
                </Collapsible>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-bg-surface border border-border rounded-xl p-6 text-center">
          <p className="text-text-secondary text-sm">{data?.note ?? 'Not enough live battles yet for deck archetypes.'}</p>
        </div>
      )}

      {data?.total > 0 && (
        <Pagination page={page} pageSize={data.page_size ?? 20} total={data.total} onPageChange={setPage} />
      )}
    </div>
  )
}

const VARIANT_LABEL: Record<string, { label: string; className: string }> = {
  regular: { label: 'REGULAR', className: 'bg-bg-card text-text-secondary' },
  evolution: { label: 'EVO', className: 'bg-cyan-400/20 text-cyan-300' },
  hero: { label: 'HERO', className: 'bg-gold/20 text-gold' },
  evolved_or_hero: { label: 'EVO OR HERO', className: 'bg-gradient-to-r from-purple-400/20 to-gold/20 text-purple-300' },
}

const VARIANT_PAGE_SIZE = 20

function VariantUsageTable({ title, description, rows, borderClass, openCard }: {
  title: string; description: string; rows: any[]; borderClass: string; openCard: (name: string) => void
}) {
  const [page, setPage] = useState(1)
  const pageRows = rows.slice((page - 1) * VARIANT_PAGE_SIZE, page * VARIANT_PAGE_SIZE)
  return (
    <div className="mb-5">
      <h3 className="text-sm font-semibold text-white mb-1">{title}</h3>
      <p className="text-text-secondary text-xs mb-3">{description}</p>
      {rows.length > 0 ? (
        <div className={`bg-bg-surface border ${borderClass} rounded-xl p-4`}>
          <Pagination page={page} pageSize={VARIANT_PAGE_SIZE} total={rows.length} onPageChange={setPage} className="mb-3" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 text-text-muted font-medium text-xs">Card</th>
                  <th className="text-left py-2 text-text-muted font-medium text-xs">Variant</th>
                  <th className="text-right py-2 text-text-muted font-medium text-xs">Share of Uses</th>
                  <th className="text-right py-2 text-text-muted font-medium text-xs">Times Used</th>
                  <th className="text-right py-2 text-text-muted font-medium text-xs">Win Rate</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((v: any, i: number) => (
                  <tr key={`${v.name}-${v.kind}-${i}`} onClick={() => openCard(v.name)}
                    className="border-b border-border/50 hover:bg-bg-card/50 cursor-pointer">
                    <td className="py-1.5 text-text-primary font-medium">
                      <div className="flex items-center gap-2">
                        <CardImage name={v.name} imageUrl={v.base_image_url} rarity={v.rarity} size="xs" showName={false} magnify={false}
                          evolutionImageUrl={v.evolution_image_url} heroImageUrl={v.hero_image_url}
                          isEvolved={v.kind === 'evolution'} isHero={v.kind === 'hero'} isAmbiguous={v.kind === 'evolved_or_hero'} />
                        <CardName name={v.name} rarity={v.rarity} className="text-sm" />
                      </div>
                    </td>
                    <td className="py-1.5 text-text-secondary text-xs">
                      <span className={`text-[9px] px-1 rounded ${VARIANT_LABEL[v.kind]?.className}`}>
                        {VARIANT_LABEL[v.kind]?.label ?? v.kind}
                      </span>
                    </td>
                    <td className="py-1.5 text-right text-cyan-300 font-semibold">{v.active_rate_pct}%</td>
                    <td className="py-1.5 text-right text-text-secondary">{v.times_used.toLocaleString()}</td>
                    <td className="py-1.5 text-right text-text-secondary">{v.win_rate_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={VARIANT_PAGE_SIZE} total={rows.length} onPageChange={setPage} />
        </div>
      ) : (
        <div className="bg-bg-surface border border-border rounded-xl p-6 text-center">
          <p className="text-text-secondary text-sm">Not enough battles collected for this yet.</p>
        </div>
      )}
    </div>
  )
}

function EvolutionUsageTab() {
  const { openCard } = useCardDetail()
  const { data, isLoading } = useQuery({ queryKey: ['evolution-usage'], queryFn: () => metaApi.evolutionUsage() })

  // Two separate, real-data tables -- Evolution (the classic chip-based
  // system) and Hero (the newer permanent-upgrade system) are different
  // systems with different cards capable of each, so they're kept apart
  // rather than interleaved in one combined list. A dual-capable card
  // (Knight, Musketeer, Wizard, Valkyrie) legitimately appears in BOTH
  // tables -- each with its own real Regular-vs-that-variant comparison,
  // since "regular" usage is tracked once per card but is the right
  // baseline for both systems.
  const evoRows = (data?.cards ?? []).flatMap((c: any) => {
    if (!c.variants.some((v: any) => v.kind === 'evolution')) return []
    return c.variants
      .filter((v: any) => v.kind === 'regular' || v.kind === 'evolution')
      .map((v: any) => ({ ...v, name: c.name, rarity: c.rarity }))
  })
  const heroRows = (data?.cards ?? []).flatMap((c: any) => {
    if (!c.variants.some((v: any) => v.kind === 'hero')) return []
    return c.variants
      .filter((v: any) => v.kind === 'regular' || v.kind === 'hero')
      .map((v: any) => ({ ...v, name: c.name, rarity: c.rarity }))
  })
  // Dual-capable cards (Knight/Musketeer/Wizard/Valkyrie): real match data
  // can't tell Evolution from Hero for these (see card_service
  // .split_evolution_hero_cards's docstring), so their active usage shows up
  // as its own honest "evolved_or_hero" kind rather than a guessed evolution
  // or hero pick -- these cards won't have a plain 'evolution'/'hero' row at
  // all, so they'd silently vanish from both tables above without this one.
  const ambigRows = (data?.cards ?? []).flatMap((c: any) => {
    if (!c.variants.some((v: any) => v.kind === 'evolved_or_hero')) return []
    return c.variants
      .filter((v: any) => v.kind === 'regular' || v.kind === 'evolved_or_hero')
      .map((v: any) => ({ ...v, name: c.name, rarity: c.rarity }))
  })

  return (
    <div>
      <p className="text-text-secondary text-sm mb-4">
        How often each Evolution/Hero card is actually played Regular vs Evolved vs Hero'd, from real recent battles.
      </p>

      {isLoading ? (
        <div className="h-64 bg-bg-surface rounded-xl animate-pulse" />
      ) : (
        <>
          <VariantUsageTable
            title="⬆ Evolution Usage"
            description="Regular vs Evolved, for every card with a classic (chip-based) Evolution."
            rows={evoRows} borderClass="border-purple-400/30" openCard={openCard}
          />
          <VariantUsageTable
            title="★ Hero Usage"
            description="Regular vs Hero'd, for every card with the newer permanent Hero upgrade."
            rows={heroRows} borderClass="border-gold/30" openCard={openCard}
          />
          <VariantUsageTable
            title="? Evolved or Hero'd (Undetermined)"
            description="For the 4 dual-capable cards (Knight, Musketeer, Wizard, Valkyrie): confirmed real usage as Evolution OR Hero, but real match data genuinely can't tell which for these -- shown honestly as one combined bucket instead of guessing."
            rows={ambigRows} borderClass="border-cyan-400/30" openCard={openCard}
          />
        </>
      )}

      <div className="mt-5">
        <TowerTroopUsageSection />
      </div>
    </div>
  )
}

function TowerTroopUsageSection() {
  const { data, isLoading } = useQuery({ queryKey: ['tower-troop-usage'], queryFn: () => metaApi.towerTroopUsage() })

  return (
    <Collapsible title="🏰 King Tower Troop Usage">
      <p className="text-text-secondary text-xs mb-3">
        Which King Tower Troop real players actually use, and how well it does -- from the battlelog's real
        per-match supportCards field. Only counts battles collected since this tracking was added (2026-08-01).
      </p>
      {isLoading ? (
        <div className="h-32 bg-bg-surface rounded-xl animate-pulse" />
      ) : data?.tower_troops?.length > 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {data.tower_troops.map((t: any) => (
            <div key={t.name} className="bg-bg-card rounded-lg p-3 text-center">
              {t.image_url && <img src={t.image_url} alt="" className="w-8 h-8 object-contain mx-auto mb-1" />}
              <div className="text-text-primary text-xs font-medium truncate">{t.name}</div>
              <div className="text-cyan-300 font-bold">{t.win_rate}%</div>
              <div className="text-text-muted text-[10px]">{t.times_used.toLocaleString()} uses</div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-text-secondary text-sm">{data?.note ?? 'Not enough battles collected since tower troop tracking was added yet.'}</p>
      )}
    </Collapsible>
  )
}

function CardValueTab() {
  const [refLevel, setRefLevel] = useState(11)
  const { data, isLoading } = useQuery({
    queryKey: ['card-value', refLevel],
    queryFn: () => mlApi.cardValue(refLevel),
  })

  return (
    <div>
      <label className="text-sm text-text-secondary block mb-2">
        Reference level: <span className="text-accent font-semibold">{refLevel}</span>
      </label>
      <input type="range" min={1} max={18} value={refLevel} onChange={e => setRefLevel(Number(e.target.value))}
        className="w-64 mb-5 accent-gold" />

      <p className="text-text-muted text-xs mb-4 max-w-2xl">
        Efficiency = (Hitpoints + DPS×4) / Elixir — a rough "stat output per elixir" measure.
        Win Rate is the real, live-collected signal. These are two independent signals, not blended together.
      </p>

      {isLoading ? (
        <div className="h-96 bg-bg-surface rounded-xl animate-pulse" />
      ) : (
        <div className="bg-bg-surface border border-border rounded-xl p-4">
          <ResponsiveContainer width="100%" height={350}>
            <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#4A2E2E" />
              <XAxis type="number" dataKey="efficiency" name="Efficiency" tick={{ fill: '#8A7568', fontSize: 11 }} />
              <YAxis type="number" dataKey="win_rate" name="Win Rate" tick={{ fill: '#8A7568', fontSize: 11 }}
                domain={[0.4, 0.6]} />
              <ZAxis type="number" dataKey="elixir" range={[40, 200]} />
              <Tooltip contentStyle={{ background: '#2B1C1C', border: '1px solid #4A2E2E', borderRadius: 8 }}
                cursor={{ strokeDasharray: '3 3' }}
                content={({ payload }) => {
                  if (!payload?.length) return null
                  const d = payload[0].payload
                  return (
                    <div className="bg-bg-card border border-border rounded-lg p-2 text-xs">
                      <div className="font-semibold"><CardName name={d.card_name} rarity={d.rarity} /></div>
                      <div className="text-text-secondary">Efficiency: {d.efficiency}</div>
                      {d.win_rate && <div className="text-text-secondary">Win Rate: {(d.win_rate * 100).toFixed(1)}%</div>}
                      <div className="text-text-muted">Elixir: {d.elixir}</div>
                    </div>
                  )
                }} />
              <Scatter data={data?.cards ?? []} fill="#F5A623" fillOpacity={0.7} />
            </ScatterChart>
          </ResponsiveContainer>

          <div className="mt-4 overflow-x-auto max-h-96 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-bg-surface">
                <tr className="border-b border-border">
                  <th className="text-left py-2 text-text-muted font-medium text-xs">Card</th>
                  <th className="text-right py-2 text-text-muted font-medium text-xs">Elixir</th>
                  <th className="text-left py-2 text-text-muted font-medium text-xs">Rarity</th>
                  <th className="text-right py-2 text-text-muted font-medium text-xs">Efficiency</th>
                  <th className="text-right py-2 text-text-muted font-medium text-xs">Win Rate</th>
                </tr>
              </thead>
              <tbody>
                {(data?.cards ?? []).map((c: any) => (
                  <tr key={c.card_name} className="border-b border-border/50">
                    <td className="py-1.5"><CardName name={c.card_name} rarity={c.rarity} className="text-sm" /></td>
                    <td className="py-1.5 text-right text-text-secondary">{c.elixir}</td>
                    <td className="py-1.5 text-text-secondary">{c.rarity}</td>
                    <td className="py-1.5 text-right text-accent font-semibold">{c.efficiency}</td>
                    <td className="py-1.5 text-right text-text-secondary">
                      {c.win_rate ? `${(c.win_rate * 100).toFixed(2)}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
