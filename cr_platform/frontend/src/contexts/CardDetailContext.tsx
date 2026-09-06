import { createContext, useContext, useState, useMemo, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { cardsApi, Card } from '../utils/api'
import CardDetailModal from '../components/CardDetailModal'

/**
 * Global "click any card, anywhere, to see its details" provider -- mounted
 * once at the app root (see App.tsx) so every page shares one CardDetailModal
 * instance instead of each page re-implementing its own
 * `useState<Card | null>` + inline modal render (the pattern this replaces,
 * previously duplicated across DeckLabPage and 4 AnalyticsPage tabs).
 *
 * Looks the card up by name from the same `cardsApi.getAll()` cache every
 * page already queries (react-query dedupes this to one real network
 * request), so any caller only needs the card's name, not the full `Card`
 * object -- important since most call sites (CoachingPage/PlayerPage/
 * FavoritesPage/CounterDecksList/StrategyCounterBrowser deck grids) only
 * ever had the name string to begin with.
 */
const CardDetailCtx = createContext<{ openCard: (name: string) => void } | null>(null)

export function CardDetailProvider({ children }: { children: ReactNode }) {
  const [openName, setOpenName] = useState<string | null>(null)
  const { data } = useQuery({ queryKey: ['cards'], queryFn: () => cardsApi.getAll() })

  const card: Card | undefined = useMemo(
    () => (openName ? data?.items?.find((c: Card) => c.name === openName) : undefined),
    [openName, data],
  )

  return (
    <CardDetailCtx.Provider value={{ openCard: setOpenName }}>
      {children}
      {card && <CardDetailModal card={card} onClose={() => setOpenName(null)} />}
    </CardDetailCtx.Provider>
  )
}

/** `const { openCard } = useCardDetail(); ... onClick={() => openCard(name)}` */
export function useCardDetail() {
  const ctx = useContext(CardDetailCtx)
  if (!ctx) throw new Error('useCardDetail must be used within CardDetailProvider')
  return ctx
}
