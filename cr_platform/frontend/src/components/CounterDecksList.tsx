import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import CardImage, { CardName } from './CardImage'
import { useCardDetail } from '../contexts/CardDetailContext'
import FavoriteButton from './FavoriteButton'
import Pagination from './Pagination'
import Collapsible from './Collapsible'
import TowerTroopSection from './TowerTroopSection'
import StrategyPicker from './StrategyPicker'
import { decksApi, metaApi } from '../utils/api'
import { formatStrategy } from '../utils/formatStrategy'

const COUNTER_SORTS = [
  ['reliability', '✓ Most Reliable'],
  ['frequency', '🔥 Most Played'],
  ['win_rate', '🏆 Highest Win Rate'],
  ['synergy_score', '🔗 Best Synergy'],
] as const

/**
 * Renders the response of POST /decks/counter -- prioritizing real decks that
 * have actually been played (and how often they won) against the opponent's
 * archetype (`tested_counter_decks`, from data/deck_matchups_live.csv) over
 * the old synthetic per-card-score assembly. Falls back to the single
 * `counter_deck` with a "not enough tested data yet" note when
 * `counter_deck_source === 'synthetic'`, so the honesty about data
 * availability is visible in the UI rather than silently blended in.
 *
 * Owns its own sort/strategy-filter/page state and re-fetches from
 * decksApi.counter itself once the user touches those controls -- the
 * `counters` prop only seeds the initial (page 1, default sort) view so
 * callers don't have to duplicate this logic themselves.
 */
export default function CounterDecksList({
  title, deck, counters, imageFor, rarityFor, weaknessLabels, hideWeaknesses, evolutionImageFor, heroImageFor,
}: {
  title: string; deck: string[]; counters: any
  imageFor: (name: string) => string | null | undefined
  rarityFor: (name: string) => string | null | undefined
  weaknessLabels?: Record<string, string>
  hideWeaknesses?: boolean
  evolutionImageFor?: (name: string) => string | null | undefined
  heroImageFor?: (name: string) => string | null | undefined
}) {
  const { openCard } = useCardDetail()
  const [sortBy, setSortBy] = useState<typeof COUNTER_SORTS[number][0]>('reliability')
  const [strategy, setStrategy] = useState('')
  const [page, setPage] = useState(1)
  const [liveCounters, setLiveCounters] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const { data: strategiesData } = useQuery({ queryKey: ['deck-strategies'], queryFn: () => metaApi.deckStrategies() })
  const strategies: any[] = strategiesData?.strategies ?? []

  // A genuinely new deck lookup (not just a sort/page tweak on the same one)
  // resets back to the parent-provided default view.
  const deckKey = deck.join(',')
  useEffect(() => {
    setLiveCounters(null)
    setSortBy('reliability')
    setStrategy('')
    setPage(1)
  }, [deckKey])

  const refetch = async (nextSortBy: typeof sortBy, nextStrategy: string, nextPage: number) => {
    if (!deck.length) return
    setLoading(true)
    try {
      setLiveCounters(await decksApi.counter(deck, undefined, { page: nextPage, sortBy: nextSortBy, strategy: nextStrategy || undefined }))
    } finally {
      setLoading(false)
    }
  }

  const active = liveCounters ?? counters
  if (!active) return null
  const hasTested = active.tested_counter_decks?.length > 0

  return (
    <div className="bg-bg-surface border border-border rounded-xl p-5">
      <h3 className="font-semibold text-white mb-1">{title}</h3>
      <div className="flex flex-wrap gap-1 mb-3">
        {deck.map(c => (
          <span key={c} className="text-xs px-2 py-0.5 rounded-full bg-bg-card">
            <CardName name={c} rarity={rarityFor(c) ?? undefined} />
          </span>
        ))}
      </div>

      {!hideWeaknesses && active.weaknesses?.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {active.weaknesses.map((w: string) => (
            <span key={w} className="text-xs px-2 py-1 rounded-lg bg-yellow-400/10 text-yellow-400">{weaknessLabels?.[w] ?? w.replace(/_/g, ' ')}</span>
          ))}
        </div>
      )}

      {(hasTested || liveCounters) && (
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <div className="flex flex-wrap gap-1">
            {COUNTER_SORTS.map(([key, label]) => (
              <button key={key} onClick={() => { setSortBy(key); setPage(1); refetch(key, strategy, 1) }}
                className={`px-2 py-1 rounded-lg text-[11px] font-medium transition-colors
                  ${sortBy === key ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
                {label}
              </button>
            ))}
          </div>
          <div className="w-full sm:w-48">
            <StrategyPicker strategies={strategies} value={strategy}
              onChange={v => { setStrategy(v); setPage(1); refetch(sortBy, v, 1) }} />
          </div>
        </div>
      )}

      {hasTested ? (
        <>
          <p className="text-xs text-cyan-300 mb-2">✓ Real decks players have used and won with vs {formatStrategy(active.vs_archetype)}</p>
          {active.total > 0 && (
            <Pagination page={page} pageSize={active.page_size ?? 10} total={active.total}
              onPageChange={p => { setPage(p); refetch(sortBy, strategy, p) }} className="mb-2" />
          )}
          <div className={`space-y-2 transition-opacity ${loading ? 'opacity-50' : ''}`}>
            {active.tested_counter_decks.map((d: any, i: number) => (
              <div key={i} className="bg-bg-card rounded-lg p-2">
                <div className="flex items-center justify-between mb-1">
                  {d.strategy && <span className="text-[10px] font-medium text-accent/80">🏷 {formatStrategy(d.strategy)}</span>}
                  <FavoriteButton deck={{
                    cards: d.cards, label: `Counter vs ${formatStrategy(active.vs_archetype)}`, win_rate: d.win_rate, wins: d.wins,
                    frequency: d.frequency, avg_elixir: d.avg_elixir, mvp_card: d.mvp_card,
                    typical_evolution: d.typical_evolution, typical_hero: d.typical_hero,
                    evolution_rate_pct: d.evolution_rate_pct, hero_rate_pct: d.hero_rate_pct,
                    ambiguous_cards: d.typical_ambiguous ? [d.typical_ambiguous] : undefined,
                    typical_tower_troop: d.typical_tower_troop, tower_troop_rate_pct: d.tower_troop_rate_pct,
                    tower_troop_win_rate_pct: d.tower_troop_win_rate_pct, tower_troop_image_url: d.tower_troop_image_url,
                  }} size={14} />
                </div>
                <div className="grid grid-cols-4 sm:grid-cols-8 gap-x-0.5 gap-y-2 mb-1">
                  {d.cards.map((name: string) => {
                    const detail = d.cards_detail?.find((cd: any) => cd.name === name)
                    const isMvp = d.mvp_card === name
                    return (
                      <div key={name} className={isMvp ? 'rounded ring-2 ring-gold' : ''}>
                        <CardImage name={name} imageUrl={imageFor(name) ?? undefined} rarity={rarityFor(name) ?? undefined} size="sm" showName={false} onClick={() => openCard(name)}
                          evolutionImageUrl={evolutionImageFor?.(name)} heroImageUrl={heroImageFor?.(name)}
                          isEvolved={d.typical_evolution === name} isHero={d.typical_hero === name}
                          isAmbiguous={d.typical_ambiguous === name} />
                        {detail?.win_rate != null && (
                          <div className={`text-center text-[9px] mt-1.5 ${isMvp ? 'text-gold font-bold' : 'text-text-muted'}`}
                            title={`${name}'s own real win rate across every real collected game it's appeared in (any deck) -- not specific to this deck. The highest one here is crowned deck MVP.`}>
                            {detail.win_rate}%
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
                <div className="text-[10px] text-text-muted mb-1">
                  {d.win_rate}% WR ({d.wins != null ? `${d.wins}W / ${d.frequency}` : d.frequency} real games) · avg {d.avg_elixir} elixir
                  {d.mvp_card && (
                    <> · <span className="text-gold" title="The card in this deck with the highest overall real win rate across all its games (any deck) -- the small % under each card above is that same per-card stat.">
                      ★ MVP: {d.mvp_card}
                    </span></>
                  )}
                </div>
                {/* Reliability/prediction/usage-rate/reasoning -- real and
                    useful, but genuinely advanced/secondary next to the
                    headline WR/games/MVP line above, so collapsed by default
                    (only players who want the deeper read need to click). */}
                {(d.strategy_games_played != null || d.estimated_win_rate != null || d.predicted_scoreline
                  || d.model_win_probability_pct != null || d.typical_evolution || d.typical_hero
                  || d.typical_ambiguous || d.typical_tower_troop || d.reasons?.length > 0) && (
                  <Collapsible title="More details" compact>
                    <TowerTroopSection d={d} />
                    {/* Reliability: this exact deck's own real win rate above can
                        be a thin sample (as low as MIN_MATCHUP_FREQUENCY real
                        games) -- shown alongside, never blended into, its real
                        strategy pooled across every variant and the Deck Quality
                        Model's composition-based estimate. */}
                    {(d.strategy_games_played != null || d.estimated_win_rate != null) && (
                      <div className="text-[10px] text-text-muted mb-1 flex flex-wrap gap-x-3 gap-y-0.5">
                        {d.strategy_games_played != null && (
                          <span title="This deck's real win rate, pooled with every other real deck sharing the same strategy (win condition + flavor)">
                            {formatStrategy(d.strategy)} overall: <span className="text-text-secondary font-medium">{d.strategy_win_rate}%</span> ({d.strategy_games_played.toLocaleString()} games)
                          </span>
                        )}
                        {d.estimated_win_rate != null && (
                          <span title="The Deck Quality Model's composition-based estimate -- learned from well-tested decks, applied here since this exact deck has too few real games to trust on its own">
                            🤖 Model estimate: <span className="text-text-secondary font-medium">{d.estimated_win_rate}%</span>
                          </span>
                        )}
                      </div>
                    )}
                    {(d.predicted_scoreline || d.model_win_probability_pct != null) && (
                      <div className="text-[10px] text-text-muted mb-1 bg-bg-surface/50 rounded px-1.5 py-1">
                        {d.predicted_scoreline && (
                          <div>
                            <span className="text-purple-300 font-medium">Predicted outcome:</span>{' '}
                            {d.predicted_scoreline.most_likely} ({d.predicted_scoreline.most_likely_pct}% of {d.predicted_scoreline.total_games} real games)
                            {d.predicted_scoreline.breakdown?.length > 1 && (
                              <span className="text-text-muted">
                                {' '}· also seen: {d.predicted_scoreline.breakdown.slice(1, 4).map((b: any) => `${b.score} (${b.pct}%)`).join(', ')}
                              </span>
                            )}
                          </div>
                        )}
                        {d.model_win_probability_pct != null && (
                          <div>
                            <span className="text-cyan-300 font-medium">Model prediction:</span>{' '}
                            {d.model_win_probability_pct}% chance to win vs this exact opponent deck
                          </div>
                        )}
                      </div>
                    )}
                    {(d.typical_evolution || d.typical_hero || d.typical_ambiguous) && (
                      <div className="text-[10px] text-text-muted mb-1">
                        {d.typical_evolution && <>⬆ {d.typical_evolution} evolved {d.evolution_rate_pct}% of the time</>}
                        {d.typical_evolution && (d.typical_hero || d.typical_ambiguous) && ' · '}
                        {d.typical_hero && <>★ {d.typical_hero} hero'd {d.hero_rate_pct}% of the time</>}
                        {d.typical_hero && d.typical_ambiguous && ' · '}
                        {d.typical_ambiguous && <>? {d.typical_ambiguous} evolved-or-hero'd {d.ambiguous_rate_pct}% of the time</>}
                      </div>
                    )}
                    {d.reasons?.length > 0 && (
                      <div className="text-[10px] text-cyan-300">
                        Why this works: {d.reasons.join('; ')}
                      </div>
                    )}
                  </Collapsible>
                )}
              </div>
            ))}
          </div>
          {active.total > 0 && (
            <Pagination page={page} pageSize={active.page_size ?? 10} total={active.total}
              onPageChange={p => { setPage(p); refetch(sortBy, strategy, p) }} />
          )}
        </>
      ) : (
        <>
          <p className="text-xs text-text-muted mb-2">
            {strategy
              ? `No real decks seen yet for strategy "${formatStrategy(strategy)}" vs this matchup -- try clearing the strategy filter.`
              : 'No widely-tested real deck data yet for this matchup -- suggested deck based on individual card counter scores instead.'}
          </p>
          {!strategy && (
            <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
              {active.counter_deck?.map((name: string) => (
                <CardImage key={name} name={name} imageUrl={imageFor(name) ?? undefined} rarity={rarityFor(name) ?? undefined} size="sm" onClick={() => openCard(name)} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
