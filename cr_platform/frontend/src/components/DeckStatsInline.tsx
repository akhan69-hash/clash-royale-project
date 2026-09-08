import { useQuery } from '@tanstack/react-query'
import { metaApi } from '../utils/api'

/**
 * Real feedback (2026-09-07): "My deck and Opponent deck does not have copy
 * and paste option. Plus win rate and usage does not show on those decks."
 * Current Deck (PlayerPage) and a selected battle's Opponent Deck just
 * render whatever the live API/battlelog returned -- no win-rate/usage at
 * all, unlike every other deck display in the app (Top Decks, Counter
 * Decks, My Decks) which all draw from real deck_archetypes_live.csv stats.
 * This looks that same exact deck up by card set (GET /meta/deck-lookup)
 * and shows a compact win-rate/usage line -- honestly says nothing when
 * this exact 8-card set hasn't been seen enough times to have real stats,
 * rather than a fabricated number.
 */
export default function DeckStatsInline({ cards }: { cards: string[] }) {
  const { data, isLoading } = useQuery({
    queryKey: ['deck-lookup', [...cards].sort().join(',')],
    queryFn: () => metaApi.deckLookup(cards),
    enabled: cards.length === 8,
  })

  if (isLoading) return <span className="text-text-muted text-xs">Looking up real stats...</span>
  if (!data?.found) return null

  return (
    <div className="flex items-center gap-3 text-xs flex-wrap">
      <span className="text-cyan-300 font-semibold">{data.win_rate}% WR</span>
      <span className="text-text-muted">
        {data.wins != null ? `${data.wins}W / ${data.frequency}` : data.frequency} real games
      </span>
      <span className="text-text-muted" title="Combined elixir cost of the 4 cheapest cards -- lower means faster cycling back to your win condition">
        ⚡ Cycle {data.cycle_cost}
      </span>
    </div>
  )
}
