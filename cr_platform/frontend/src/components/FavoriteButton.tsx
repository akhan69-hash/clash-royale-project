import { useState } from 'react'
import { Star, Copy, Check } from 'lucide-react'
import { FavoriteDeck, deckKey, toggleFavoriteDeck, useFavoriteDecks } from '../utils/favorites'
import { deckToClipboardText } from '../utils/deckClipboard'

/** Star toggle reused on every deck card across the app (Top Decks, Counter
 * Decks, My Decks) -- always looks at the shared localStorage favorites
 * store so its filled/outline state stays correct no matter which page
 * favorited this exact deck first.
 *
 * A prior round (2026-08-21) made mobile require a double-tap (Instagram-
 * style) to guard against accidental single taps -- real feedback
 * (2026-08-22): "favorites function doesn't seem to work." Reverted: the
 * double-tap window likely lost the race against mobile browsers' own
 * native double-tap-to-zoom gesture (no `touch-action` was set to disable
 * it), and even when it didn't, "tap once, nothing visibly happens except a
 * faint pulse, tap again" reads as broken to a real user. A single
 * tap/click, the same on every device, is simply the reliable choice here
 * -- occasional mis-taps are a smaller cost than "the feature doesn't work."
 *
 * Also now bundles a "Copy deck" button right next to the star -- real
 * feedback (2026-08-22): "being able to copy and paste entire decks from
 * different pages to different pages on the site." Every place that already
 * renders a favorite star gets this for free without needing its own
 * call-site change; the matching "Paste" side lives in DeckBuilderKit's
 * PasteDeckButton, used on the actual deck-building pages. */
export default function FavoriteButton({ deck, size = 16, className = '' }: {
  deck: Omit<FavoriteDeck, 'saved_at'>; size?: number; className?: string
}) {
  const favs = useFavoriteDecks()
  const active = deckKey(deck.cards) in favs
  const [copied, setCopied] = useState(false)

  const copyDeck = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await navigator.clipboard.writeText(deckToClipboardText(deck.cards))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard API can be denied/unavailable (older browsers, insecure
      // context) -- fails silently rather than throwing in the user's face
      // over a small convenience feature.
    }
  }

  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <button
        onClick={copyDeck}
        title={copied ? 'Copied!' : 'Copy this deck'}
        className="shrink-0 text-text-muted hover:text-cyan-300 transition-colors"
      >
        {copied ? <Check size={size} className="text-cyan-300" /> : <Copy size={size} />}
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); toggleFavoriteDeck(deck) }}
        title={active ? 'Remove from favorites' : 'Save to favorites'}
        className={`shrink-0 transition-colors ${active ? 'text-gold' : 'text-text-muted hover:text-gold'}`}
      >
        <Star size={size} fill={active ? 'currentColor' : 'none'} />
      </button>
    </span>
  )
}
