import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import CardImage, { CardName } from './CardImage'
import { useCardDetail } from '../contexts/CardDetailContext'
import Pagination from './Pagination'
import FavoriteButton from './FavoriteButton'
import TowerTroopSection from './TowerTroopSection'
import StrategyPicker from './StrategyPicker'
import { decksApi, metaApi } from '../utils/api'
import { formatStrategy } from '../utils/formatStrategy'

const SORTS = [
  ['frequency', '🔥 Most Played'],
  ['win_rate', '🏆 Highest Win Rate'],
] as const

/**
 * Real counters for a whole STRATEGY (e.g. "Hog Rider (cycle)"), picked
 * directly from a dropdown -- no need to build an opponent's exact 8-card
 * deck first (that's what the "vs a specific deck" mode above is for).
 * Numbers here are pooled across every real exact-deck variant of each
 * counter strategy (GET /decks/counter-strategy), so they run far larger
 * and more reliable than a single exact-deck matchup's real game count.
 */
export default function StrategyCounterBrowser({ cards }: { cards: any[] }) {
  const { openCard } = useCardDetail()
  const [vsStrategy, setVsStrategy] = useState('')
  const [sortBy, setSortBy] = useState<typeof SORTS[number][0]>('frequency')
  const [page, setPage] = useState(1)

  const { data: strategiesData } = useQuery({ queryKey: ['deck-strategies'], queryFn: () => metaApi.deckStrategies() })
  const strategies: any[] = strategiesData?.strategies ?? []

  const { data, isFetching } = useQuery({
    queryKey: ['counter-strategy', vsStrategy, sortBy, page],
    queryFn: () => decksApi.counterStrategy(vsStrategy, page, 4, sortBy),
    enabled: !!vsStrategy,
  })

  const imageFor = (name: string) => cards.find(c => c.name === name)?.image_url
  const rarityFor = (name: string) => cards.find(c => c.name === name)?.rarity
  const evolutionImageFor = (name: string) => cards.find(c => c.name === name)?.evolution_image_url
  const heroImageFor = (name: string) => cards.find(c => c.name === name)?.hero_image_url

  const setStrategyAndResetPage = (v: string) => { setVsStrategy(v); setPage(1) }
  const setSortAndResetPage = (v: typeof sortBy) => { setSortBy(v); setPage(1) }

  return (
    <div className="bg-bg-surface border border-border rounded-xl p-4">
      <h3 className="font-semibold text-white mb-1">🏷 Counters by Strategy</h3>
      <p className="text-text-muted text-xs mb-3">
        Pick the strategy you're facing -- real counter strategies, ranked by real games played pooled across
        every deck of that counter strategy (far more reliable than any single exact-deck matchup).
      </p>

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <div className="w-full sm:w-64">
          <StrategyPicker
            strategies={strategies.map((s: any) => ({ strategy: s.strategy, frequency: s.total_frequency }))}
            value={vsStrategy} onChange={setStrategyAndResetPage}
            placeholder="Search the strategy you're facing (hog, bait...)" />
        </div>
        {vsStrategy && (
          <div className="flex flex-wrap gap-1">
            {SORTS.map(([key, label]) => (
              <button key={key} onClick={() => setSortAndResetPage(key)}
                className={`px-2 py-1 rounded-lg text-[11px] font-medium transition-colors
                  ${sortBy === key ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      {!vsStrategy ? null : isFetching && !data ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-24 bg-bg-card rounded-lg animate-pulse" />)}
        </div>
      ) : data?.counters?.length > 0 ? (
        <>
          {data.total > 0 && (
            <Pagination page={page} pageSize={data.page_size ?? 10} total={data.total} onPageChange={setPage} className="mb-2" />
          )}
          <div className={`space-y-2 transition-opacity ${isFetching ? 'opacity-50' : ''}`}>
            {data.counters.map((c: any, i: number) => (
              <div key={i} className="bg-bg-card rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-semibold text-accent">🏷 {formatStrategy(c.strategy)}</span>
                  <span className="text-xs text-text-secondary">
                    <span className="text-cyan-300 font-semibold">{c.win_rate}% WR</span>
                    {' '}({c.wins.toLocaleString()}W / {c.frequency.toLocaleString()} real games, {c.deck_count.toLocaleString()} decks)
                  </span>
                </div>
                {c.representative_decks?.length > 0 && (
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {c.representative_decks.map((d: any, di: number) => (
                      <div key={di} className="bg-bg-surface rounded-lg p-2">
                        <div className="flex justify-end mb-1">
                          <FavoriteButton deck={{
                            cards: d.cards, label: `Counter: ${formatStrategy(c.strategy)} vs ${formatStrategy(data.vs_strategy)}`,
                            win_rate: d.win_rate, wins: d.wins, frequency: d.frequency, avg_elixir: d.avg_elixir,
                            typical_evolution: d.typical_evolution, typical_hero: d.typical_hero,
                            evolution_rate_pct: d.evolution_rate_pct, hero_rate_pct: d.hero_rate_pct,
                            ambiguous_cards: d.typical_ambiguous ? [d.typical_ambiguous] : undefined,
                            typical_tower_troop: d.typical_tower_troop, tower_troop_rate_pct: d.tower_troop_rate_pct,
                            tower_troop_win_rate_pct: d.tower_troop_win_rate_pct, tower_troop_image_url: d.tower_troop_image_url,
                          }} size={12} />
                        </div>
                        <div className="grid grid-cols-4 sm:grid-cols-8 gap-0.5 mb-1">
                          {d.cards.map((name: string) => (
                            <CardImage key={name} name={name} imageUrl={imageFor(name)} rarity={rarityFor(name)} size="xs" showName={false} onClick={() => openCard(name)}
                              evolutionImageUrl={evolutionImageFor(name)} heroImageUrl={heroImageFor(name)}
                              isEvolved={d.typical_evolution === name} isHero={d.typical_hero === name}
                              isAmbiguous={d.typical_ambiguous === name} />
                          ))}
                        </div>
                        <div className="text-[10px] text-text-muted">
                          {d.win_rate}% WR ({d.wins != null ? `${d.wins}W / ${d.frequency}` : d.frequency} games) · avg {d.avg_elixir} elixir
                          {d.estimated_win_rate != null && <> · 🤖 est. {d.estimated_win_rate}%</>}
                        </div>
                        <TowerTroopSection d={d} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
          {data.total > 0 && (
            <Pagination page={page} pageSize={data.page_size ?? 10} total={data.total} onPageChange={setPage} />
          )}
        </>
      ) : (
        <div className="bg-bg-card rounded-xl p-4 text-center">
          <p className="text-text-secondary text-sm">{data?.note ?? 'No real counters found for this strategy yet.'}</p>
        </div>
      )}
    </div>
  )
}
