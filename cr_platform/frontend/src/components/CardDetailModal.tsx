import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import { cardsApi, Card } from '../utils/api'
import { RARITY_COLORS, CardName } from './CardImage'

interface Props {
  card: Card
  onClose: () => void
  /** Screen position of the thumbnail that was actually clicked to open this
   * card (see utils/cardClickOrigin.ts) -- when known, the modal grows out of
   * and shrinks back into that exact point instead of a generic centered
   * fade. Null for the few call sites that don't go through CardImage. */
  origin?: { centerX: number; centerY: number } | null
}

type ViewMode = 'base' | 'evolved' | 'hero'

// Real feedback (2026-08-22): "remove the graphs after clicking card,
// average arena level the card, usage, and more personal data about your
// card behavior using the specific card. No graphs or very tech stuff."
// This modal used to have a Stats tab (per-level HP/damage/DPS line charts
// + a scrollable level-by-level table) and a Role & Usage tab (win rate,
// presence rate, elixir efficiency, real synergy partners, per-arena usage
// breakdown, real Evolution/Hero usage split, counters/matchups) -- all
// real data, but a lot of it for a casual player just looking a card up.
// Cut down to what's actually simple and useful: what the card is, what its
// Evolution/Hero ability does in plain English, and (optionally) one single
// real win-rate number -- no charts, no tables, no per-arena/per-variant
// breakdowns.
//
// REMOVED 2026-09-08 (real feedback: "Remove the 3d tilt when clicking a
// card, fix that make it less laggy"): this used to be TiltCard, a
// mouse-move-driven rotateX/rotateY tilt. Real perf issue -- every single
// mousemove event (fires dozens of times/sec) triggered a React state
// update, which recomputed an inline boxShadow string (template-literal
// color math) AND fought a `transition-transform duration-150` that kept
// restarting mid-transition on each new value, on top of a second
// mouse-position-driven radial-gradient recompute for the glare overlay.
// That's a real, textbook unthrottled-mousemove jank pattern, not a vague
// "feels laggy" -- removed entirely rather than throttled/rAF'd, since the
// tilt wasn't the part of this modal real feedback was ever specifically
// asking to keep once it become a comfort issue. Static, still large,
// still real card art -- just no per-frame recomputation.
// No-border-line update (2026-09-07, real feedback: "No extra borders Just
// blur the background") -- the 3px rarity-colored ring around this card and
// the modal panel's own border below are both gone. The rarity color still
// reads clearly through a soft glow (boxShadow with no spread-hugging
// border) and the tinted backdrop gradient; separation from the rest of the
// page now comes entirely from the backdrop blur, not a drawn line.
function FocalCard({ src, alt, rarityColor, contain }: { src?: string | null; alt: string; rarityColor: string; contain: boolean }) {
  const [imgError, setImgError] = useState(false)
  useEffect(() => { setImgError(false) }, [src])

  return (
    <div className="mx-auto">
      <div
        className="relative w-40 h-52 rounded-2xl overflow-hidden"
        style={{
          boxShadow: `0 0 32px 6px ${rarityColor}55, 0 8px 30px rgba(0,0,0,0.5)`,
          background: `linear-gradient(160deg, ${rarityColor}22, ${rarityColor}55)`,
        }}
      >
        {imgError || !src ? (
          <div className="w-full h-full flex items-center justify-center text-white/70 text-sm">{alt}</div>
        ) : (
          <img src={src} alt={alt} className={`w-full h-full ${contain ? 'object-contain' : 'object-cover'}`}
            onError={() => setImgError(true)} draggable={false} />
        )}
      </div>
    </div>
  )
}

export default function CardDetailModal({ card, onClose, origin }: Props) {
  const [view, setView] = useState<ViewMode>('base')
  // Some very recently-added Hero cards (Hero Valkyrie/Berserker, Season 86)
  // have a real heroMedium URL in the official catalog, but the actual image
  // file 404s on Supercell's own CDN (confirmed 2026-08-05) -- this can't be
  // caught by a null check since the URL string itself is valid-looking, only
  // the fetch fails at render time. Falls back to the base card art instead
  // of silently hiding the header image.
  const [headerImageFailed, setHeaderImageFailed] = useState(false)

  const { data } = useQuery({
    queryKey: ['card-detail', card.name, view === 'evolved'],
    queryFn: () => cardsApi.getDetail(card.name, view === 'evolved'),
  })
  const { data: profile } = useQuery({
    queryKey: ['card-profile', card.name],
    queryFn: () => cardsApi.getProfile(card.name),
  })

  const rarityColor = RARITY_COLORS[card.rarity] ?? RARITY_COLORS.Common

  const preferredHeaderImage = view === 'evolved' ? (card.evolution_image_url ?? card.image_url)
    : view === 'hero' ? (card.hero_image_url ?? card.image_url)
    : card.image_url
  useEffect(() => { setHeaderImageFailed(false) }, [preferredHeaderImage])
  const headerImage = headerImageFailed ? card.image_url : preferredHeaderImage
  // Real Evolution/Hero art (like every other card render in the app) has
  // its own baked-in frame and shows uncropped; plain base art fills the tile.
  const usingRealFrame = !headerImageFailed && (view === 'evolved' || view === 'hero') && headerImage !== card.image_url

  const viewOptions: { key: ViewMode; label: string; available: boolean }[] = [
    { key: 'base', label: 'Base', available: true },
    { key: 'evolved', label: '⬆ Evolved', available: card.has_evolution },
    { key: 'hero', label: '★ Hero', available: card.has_hero },
  ]

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50">
        {/* Backdrop -- a pure blur+dim fade, independent of the card's own
            grow/shrink animation below (real feedback 2026-09-07: "just blur
            the background and close just takes the 3d card back into where
            i clicked it from" -- two separate layers on purpose, so the
            background doesn't shrink along with the card). */}
        <motion.div className="absolute inset-0 bg-black/75 backdrop-blur-md"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}/>

        {/* Full-viewport layer that does the actual grow/shrink-to-origin
            animation. transformOrigin in raw viewport px works unmodified
            here because this layer itself spans the whole viewport (inset-0,
            its own top-left already at viewport (0,0)) -- no need to measure
            the panel's own rendered size/position to converge the scale on
            the exact spot the user clicked (see utils/cardClickOrigin.ts). */}
        <motion.div
          className="absolute inset-0 flex items-center justify-center p-4 pointer-events-none"
          style={{ transformOrigin: origin ? `${origin.centerX}px ${origin.centerY}px` : '50% 50%' }}
          initial={{ opacity: 0, scale: origin ? 0.06 : 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: origin ? 0.06 : 0.9 }}
          transition={{ type: 'spring', damping: 24, stiffness: 260 }}
        >
        {/* Modal panel -- no border line (real feedback: "No extra
            borders"); separation from the page comes from the backdrop blur
            layer above, not a drawn line here. Still a fixed-height flex
            column: the focal card stays put, only the info panel below it
            scrolls (see the big comment above). */}
        <div className="relative bg-bg-surface rounded-2xl shadow-card w-full max-w-lg max-h-[85vh] flex flex-col pointer-events-auto">
          <button onClick={onClose}
            className="absolute top-3 right-3 z-20 p-1.5 rounded-lg bg-black/40 hover:bg-black/70 text-white/80 hover:text-white transition-colors">
            <X size={18}/>
          </button>

          {/* Fixed top section -- the real focal point now, not a small
              header thumbnail. Doesn't scroll with the info below it. */}
          <div className="p-5 pb-4 shrink-0 text-center">
            <FocalCard src={headerImage} alt={card.name} rarityColor={rarityColor} contain={usingRealFrame} />
            <h2 className="text-xl mt-3"><CardName name={card.name} rarity={card.rarity} /></h2>

            {(card.has_evolution || card.has_hero) && (
              <div className="flex gap-1 justify-center mt-3">
                {viewOptions.filter(v => v.available).map(v => (
                  <button key={v.key} onClick={() => setView(v.key)}
                    className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors
                      ${view === v.key ? 'bg-accent text-white' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
                    {v.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Scrollable info panel -- everything else, "small lines of info"
              you scroll through independently of the tilting card above. */}
          <div className="overflow-y-auto px-5 pb-5 border-t border-border pt-4">
            <div className="flex items-center gap-2 flex-wrap justify-center mb-3">
              <span className="text-xs px-2 py-0.5 rounded-full bg-bg-card text-text-secondary">{card.type}</span>
              <span className="text-xs px-2 py-0.5 rounded-full" style={{ backgroundColor: rarityColor + '30', color: rarityColor }}>
                {card.rarity}
              </span>
              {profile?.live_stats?.win_rate != null && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-400/15 text-cyan-300">
                  🏆 {profile.live_stats.win_rate}% real win rate
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2">
              {[
                { label: 'Elixir', value: card.elixir_cost ?? '—' },
                { label: 'Max Level', value: card.max_level },
                { label: 'Range', value: card.range ?? '—' },
                { label: 'Hit Speed', value: card.hit_speed ? `${card.hit_speed}s` : '—' },
              ].map(({ label, value }) => (
                <div key={label} className="bg-bg-card rounded-lg p-2">
                  <div className="text-xs text-text-muted">{label}</div>
                  <div className="text-sm font-semibold text-white">{value}</div>
                </div>
              ))}
            </div>

            {/* Evolution details, shown when that view is active */}
            {view === 'evolved' && card.has_evolution && (
              <div className="mt-4">
                <div className="text-sm font-semibold text-cyan-300">
                  {card.evolution_name}
                  {card.evolution_ability_name && ` -- ${card.evolution_ability_name}`}
                </div>
                {card.evolution_ability_description ? (
                  <>
                    <div className="text-xs text-text-secondary mt-0.5">{card.evolution_ability_description}</div>
                    {card.evolution_confidence === 'unconfirmed' && (
                      <div className="text-xs text-yellow-400 mt-1">⚠ Unconfirmed -- verify in-game</div>
                    )}
                  </>
                ) : (
                  <div className="text-xs text-text-muted">
                    Evolutions grant a unique situational ability rather than a flat stat boost --
                    check in-game for this card's exact effect.
                  </div>
                )}
                {data?.card?.evolution_hp_bonus ? (
                  <div className="text-xs mt-2 px-2 py-1 rounded-lg bg-cyan-400/10 text-cyan-300 inline-block">
                    ⬆ +{Math.round(data.card.evolution_hp_bonus * 100)}% Hitpoints vs base (confirmed).
                  </div>
                ) : null}
              </div>
            )}

            {/* Hero details, shown when that view is active */}
            {view === 'hero' && card.has_hero && (
              <div className="mt-4">
                <div className="text-sm font-semibold text-gold">
                  {card.hero_name}
                  {card.hero_ability_name && ` -- ${card.hero_ability_name}`}
                </div>
                {card.hero_ability_description ? (
                  <>
                    <div className="text-xs text-text-secondary mt-0.5">{card.hero_ability_description}</div>
                    {card.hero_confidence === 'unconfirmed' && (
                      <div className="text-xs text-yellow-400 mt-1">⚠ Unconfirmed -- verify in-game</div>
                    )}
                  </>
                ) : (
                  <div className="text-xs text-text-muted">
                    Hero is a separate, permanent upgrade system from Evolution -- check in-game for this card's exact effect.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        </motion.div>
      </div>
    </AnimatePresence>
  )
}
