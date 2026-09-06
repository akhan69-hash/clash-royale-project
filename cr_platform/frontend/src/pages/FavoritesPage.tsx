import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Star, Trash2 } from 'lucide-react'
import { cardsApi, decksApi, Card } from '../utils/api'
import { useFavoriteDecks, removeFavoriteDeck } from '../utils/favorites'
import CardImage from '../components/CardImage'
import { useCardDetail } from '../contexts/CardDetailContext'
import CounterDecksList from '../components/CounterDecksList'
import { CopyDeckButton } from '../components/DeckBuilderKit'
import TowerTroopSection from '../components/TowerTroopSection'
import Backdrop from '../components/Backdrop'

/**
 * Every deck favorited anywhere in the app (Top Decks, Counter Decks, My
 * Decks, a player's Current Deck) -- stored client-side, so this page is
 * just a reader over the same localStorage store FavoriteButton writes to.
 */
export default function FavoritesPage() {
  const { openCard } = useCardDetail()
  const favs = useFavoriteDecks()
  const entries = Object.entries(favs).sort((a, b) => b[1].saved_at.localeCompare(a[1].saved_at))
  const { data: allCards } = useQuery({ queryKey: ['cards'], queryFn: () => cardsApi.getAll() })
  const [counters, setCounters] = useState<Record<string, any>>({})

  const cardFor = (n: string) => allCards?.items?.find((c: Card) => c.name === n)
  const imageFor = (n: string) => cardFor(n)?.image_url
  const rarityFor = (n: string) => cardFor(n)?.rarity
  const evolutionImageFor = (n: string) => cardFor(n)?.evolution_image_url
  const heroImageFor = (n: string) => cardFor(n)?.hero_image_url

  const showCounters = async (key: string, cards: string[]) => {
    setCounters(prev => ({ ...prev, [key]: null }))
    const result = await decksApi.counter(cards)
    setCounters(prev => ({ ...prev, [key]: result }))
  }

  return (
    <div className="relative z-10 max-w-5xl mx-auto px-4 py-6">
      <Backdrop density={8} />
      <h1 className="text-2xl font-bold text-accent mb-1 flex items-center gap-2">
        <Star className="text-gold" fill="currentColor" size={22} /> Favorite Decks
      </h1>
      <p className="text-text-secondary text-sm mb-6">
        Decks you've starred from Top Decks, Counter Decks, or any player's deck history -- saved on this device.
      </p>

      {entries.length === 0 ? (
        <div className="bg-bg-surface border border-border rounded-xl p-8 text-center">
          <p className="text-text-secondary text-sm">
            No favorites yet -- tap the ☆ on any deck across the app (Analytics → Top Decks, Counter Decks, or a
            player's My Decks) to save it here.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-8">
          {entries.map(([key, d]) => {
            const evolvedCards = d.evolved_cards ?? []
            const heroCards = d.hero_cards ?? []
            const ambiguousCards = d.ambiguous_cards ?? []
            return (
            <div key={key} className="bg-bg-surface border border-border rounded-xl p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-text-muted truncate pr-2">{d.label ?? 'Favorite Deck'}</span>
                <div className="flex items-center gap-1 shrink-0">
                  <CopyDeckButton cards={d.cards} />
                  <button onClick={() => removeFavoriteDeck(d.cards)}
                    title="Remove from favorites"
                    className="text-text-muted hover:text-danger transition-colors p-1.5">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-2 mb-2 text-[11px] text-text-muted flex-wrap">
                {d.win_rate != null && <span className="text-cyan-300 font-semibold">{d.win_rate}% WR</span>}
                {d.frequency != null && (
                  <span>{d.wins != null ? `${d.wins}W / ${d.frequency}` : d.frequency.toLocaleString?.() ?? d.frequency} games</span>
                )}
                {d.avg_elixir != null && <span>avg {d.avg_elixir} elixir</span>}
                {d.cycle_cost != null && (
                  <span title="Combined elixir cost of the 4 cheapest cards in this deck -- lower means faster cycling back to your win condition">⚡ Cycle {d.cycle_cost}</span>
                )}
                {d.synergy_score != null && (
                  <span title="Average real card-pairing synergy across this deck's cards, from how those pairs have actually performed together in collected battles -- higher is better">🔗 Synergy {d.synergy_score}</span>
                )}
              </div>
              {/* 4-per-row on mobile (matching the real in-game deck display,
                  2 rows of 4) instead of squeezing all 8 into one row --
                  confirmed via a real mobile-viewport check that cards were
                  rendering too small to make out at grid-cols-8 on a phone. */}
              <div className="grid grid-cols-4 sm:grid-cols-8 gap-1 mb-2">
                {d.cards.map((name: string) => (
                  <CardImage key={name} name={name} imageUrl={imageFor(name)} rarity={rarityFor(name)} size="sm" showName={false} onClick={() => openCard(name)}
                    evolutionImageUrl={evolutionImageFor(name)} heroImageUrl={heroImageFor(name)}
                    isEvolved={d.evolved_cards ? evolvedCards.includes(name) : d.typical_evolution === name}
                    isHero={d.hero_cards ? heroCards.includes(name) : d.typical_hero === name}
                    isAmbiguous={ambiguousCards.includes(name)} />
                ))}
              </div>
              {(evolvedCards.length > 0 || heroCards.length > 0 || ambiguousCards.length > 0 || d.mvp_card) && (
                <div className="text-[10px] text-text-muted mb-2">
                  {evolvedCards.length > 0 && <>⬆ {evolvedCards.join(', ')} evolved</>}
                  {evolvedCards.length > 0 && (heroCards.length > 0 || ambiguousCards.length > 0) && ' · '}
                  {heroCards.length > 0 && <>★ {heroCards.join(', ')} hero'd</>}
                  {heroCards.length > 0 && ambiguousCards.length > 0 && ' · '}
                  {ambiguousCards.length > 0 && <>? {ambiguousCards.join(', ')} evolved-or-hero'd</>}
                  {d.mvp_card && <> · <span className="text-gold">★ MVP: {d.mvp_card}</span></>}
                </div>
              )}
              {!d.evolved_cards && (d.typical_evolution || d.typical_hero || d.mvp_card) && (
                <div className="text-[10px] text-text-muted mb-2">
                  {d.typical_evolution && <>⬆ {d.typical_evolution} evolved {d.evolution_rate_pct}% of the time</>}
                  {d.typical_evolution && d.typical_hero && ' · '}
                  {d.typical_hero && <>★ {d.typical_hero} hero'd {d.hero_rate_pct}% of the time</>}
                  {d.mvp_card && <> · <span className="text-gold">★ MVP: {d.mvp_card}</span></>}
                </div>
              )}
              <TowerTroopSection d={d} />
              <button onClick={() => showCounters(key, d.cards)}
                className="text-xs bg-accent/20 text-accent px-3 py-1.5 rounded-lg hover:bg-accent/30 transition-colors">
                Show counters for this deck
              </button>
              {key in counters && (
                <div className="mt-3">
                  <CounterDecksList title="Counters for this deck" deck={d.cards} counters={counters[key]} imageFor={imageFor} rarityFor={rarityFor}
                    hideWeaknesses evolutionImageFor={evolutionImageFor} heroImageFor={heroImageFor} />
                </div>
              )}
            </div>
          )})}
        </div>
      )}
    </div>
  )
}
