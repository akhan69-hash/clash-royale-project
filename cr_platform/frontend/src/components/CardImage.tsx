import { useState, useEffect, useRef, type DragEvent } from 'react'

export const RARITY_COLORS: Record<string, string> = {
  Common: '#8B7355',
  Rare: '#5B87C2',
  Epic: '#9B59B6',
  Legendary: '#F39C12',
  Champion: '#E74C3C',
}

const RARITY_GRADIENTS: Record<string, string> = {
  Common: 'linear-gradient(160deg, #4a4335, #8B7355)',
  Rare: 'linear-gradient(160deg, #2d4566, #5B87C2)',
  Epic: 'linear-gradient(160deg, #4a2d61, #9B59B6)',
  Legendary: 'linear-gradient(160deg, #7a5108, #F39C12)',
  Champion: 'linear-gradient(160deg, #7a2318, #E74C3C)',
}

// Glow color behind the letterboxed real Evolution/Hero art (see below) --
// not a fake frame, just a tinted backdrop so the transparent margins around
// the real card-frame image aren't stark black.
const EVO_GLOW_BG = 'radial-gradient(circle, #3a1f5c, #1a0d2e)'
const HERO_GLOW_BG = 'radial-gradient(circle, #6b4f10, #2a1f08)'
const EVO_HERO_GLOW_BG = 'radial-gradient(circle, #4a3560, #1f1508)'

interface CardImageProps {
  name: string
  imageUrl?: string | null
  evolutionImageUrl?: string | null
  heroImageUrl?: string | null
  rarity?: string
  elixir?: number | null
  level?: number | null
  hitpoints?: number | null
  dps?: number | null
  hasEvolution?: boolean
  hasHero?: boolean
  isEvolved?: boolean
  isHero?: boolean
  /** Confirmed actively Evolution- or Hero-slotted in a real match, but
   * which of the two can't be told apart from real match data (dual-capable
   * cards only -- Knight/Musketeer/Wizard/Valkyrie). Deliberately does NOT
   * render the real evolution/hero art (would be guessing which one), just
   * the base card art with a distinct two-tone "?" indicator. */
  isAmbiguous?: boolean
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  onClick?: () => void
  /** For contexts where onClick is already spoken for (deck-building
   * toggle/select/drag) -- renders a small "ⓘ" badge that opens the card
   * detail modal without disturbing the primary click. Omit `onClick`
   * entirely and this isn't needed; the two are mutually exclusive in every
   * real call site today (either the card is clickable-to-select, or it's
   * clickable-to-detail, never both on the same element). */
  onInfoClick?: () => void
  selected?: boolean
  showStats?: boolean
  showName?: boolean
  /** For dense grids (Browse Cards, the deck-builder's card picker) where a
   * permanent bottom name banner has no real room to be legible at a small
   * tile size -- real feedback (2026-08-21), pointing at the real in-game
   * collection view: cards there show no name at all in the grid, only on
   * selection. Suppresses the permanent banner and instead shows the full
   * name as a centered overlay while the card is hovered (desktop), pressed
   * (touch), or being dragged -- "when you click/touch/drag the picture, it
   * will show the name." Ignored if `showName` is false. */
  nameOnInteraction?: boolean
  draggable?: boolean
  /** Fires when a drag starts on this card, before the native dataTransfer
   * setup below -- lets a parent (e.g. DeckSlots) remember which slot a
   * drag originated from, for move/swap logic on drop. */
  onDragStart?: () => void
  onDragEnd?: (e: DragEvent) => void
  magnify?: boolean
  /** Real owned copy count, shown as a small "{ownedCount}/{copiesNeeded}"
   * line under the tile -- added 2026-09-02 to fold Collection's old
   * standalone "Your Card Levels" grid into the card-picker tiles instead of
   * keeping two separate displays of the same real data (see
   * utils/cardUpgradeCost.ts for where copiesNeeded comes from). Omit
   * copiesNeeded (leave it undefined/null) for a max-level card -- there's
   * no "next level" to count toward. */
  ownedCount?: number | null
  copiesNeeded?: number | null
  /** True when ownedCount is genuinely close to copiesNeeded (caller decides
   * the threshold) -- renders a small warning badge in the one corner
   * nothing else claims (bottom-left; elixir/crest/info/level already own
   * the other three). */
  upgradeClose?: boolean
}

// Portrait aspect ratio, like the real in-game card frame, instead of a square icon tile.
const SIZE_MAP = {
  xs: 'w-10 h-14',
  sm: 'w-16 h-20',
  md: 'w-24 h-32',
  lg: 'w-28 h-36',
  xl: 'w-36 h-48',
}

// Name-plaque text scales with tile size -- bigger/bolder than a plain label
// so the rarity color it's drawn in (see below) actually reads at a glance.
const NAME_SIZE_MAP = {
  xs: 'text-[9px]',
  sm: 'text-[11px]',
  md: 'text-xs',
  lg: 'text-sm',
  xl: 'text-base',
}

// "Cards expand like bubbles when moving the cursor around them" -- a
// dock-style magnify effect: every CardImage tracks cursor distance to its
// own center and scales up smoothly the closer the cursor gets, easing back
// to 1x once the cursor moves away. Runs off a single shared rAF-throttled
// mousemove listener per instance; DOM writes go through React state, but
// React bails out re-rendering when the computed scale is unchanged (e.g.
// every card outside the radius keeps returning 1), so idle cards don't
// re-render on every mouse move.
const MAGNIFY_RADIUS = 110
const MAGNIFY_MAX_BOOST = 0.22

function useMagnify(enabled: boolean) {
  const ref = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(1)

  useEffect(() => {
    // Every CardImage on the page registers its own window-level mousemove
    // listener when this is on -- fine for a handful of cards, but a real
    // perf problem on dense grids (Browse Cards / the deck-builder picker
    // render 100+ at once) since each one runs getBoundingClientRect + a
    // distance calc on every mouse move. It's also a pure desktop hover
    // effect -- there's no cursor to track on a touchscreen -- so it was
    // silently costing every mobile visitor for zero visual benefit, which
    // is very likely part of "rendering not fast enough." Gating on a real
    // hover+fine-pointer capability check kills the listener entirely on
    // touch devices and keeps it only where it actually does something.
    if (!enabled || !window.matchMedia('(hover: hover) and (pointer: fine)').matches) return
    let raf = 0
    const onMove = (e: MouseEvent) => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        const el = ref.current
        if (!el) return
        const rect = el.getBoundingClientRect()
        const cx = rect.left + rect.width / 2
        const cy = rect.top + rect.height / 2
        const dist = Math.hypot(e.clientX - cx, e.clientY - cy)
        const next = dist < MAGNIFY_RADIUS ? 1 + (1 - dist / MAGNIFY_RADIUS) * MAGNIFY_MAX_BOOST : 1
        setScale(prev => (Math.abs(prev - next) > 0.005 ? next : prev))
      })
    }
    window.addEventListener('mousemove', onMove)
    return () => {
      window.removeEventListener('mousemove', onMove)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [enabled])

  return { ref, scale: enabled ? scale : 1 }
}

export default function CardImage({
  name, imageUrl, evolutionImageUrl, heroImageUrl, rarity = 'Common', elixir, level, hitpoints, dps,
  hasEvolution = false, hasHero = false, isEvolved = false, isHero = false, isAmbiguous = false,
  size = 'md', onClick, onInfoClick, selected = false, showStats = false, showName = true, draggable = false,
  nameOnInteraction = false,
  onDragStart, onDragEnd,
  magnify = true,
  ownedCount, copiesNeeded, upgradeClose = false,
}: CardImageProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [pressed, setPressed] = useState(false)
  // Real bug found 2026-08-26 (reported as "the cards wheel scrollable still
  // scrolls over everything on the page"): a real Playwright touch-swipe
  // test against production confirmed the card-picker grid's OWN scrollTop
  // never moved on a touch drag inside it -- the page scrolled instead,
  // even though the exact same box scrolled correctly under a real desktop
  // mouse-wheel test. Root cause -- native HTML `draggable="true"` was set
  // unconditionally on every card (for desktop drag-to-slot). Mobile Chrome
  // has to decide whether a touch-and-move on a draggable element is a drag
  // gesture or a scroll gesture, and its real, documented behavior is to
  // suppress the container's native scroll to check for a drag first --
  // exactly the reproduced symptom. Native HTML5 drag-and-drop doesn't work
  // via touch anyway (touch users already place cards via tap/click, which
  // still works either way), so `draggable` now only turns on for devices
  // that actually have a real mouse (same hover+fine-pointer check
  // useMagnify above already uses) -- touch devices get their native scroll
  // back with zero loss of functionality.
  const [canDrag] = useState(() => typeof window !== 'undefined'
    && window.matchMedia('(hover: hover) and (pointer: fine)').matches)
  const dragEnabled = draggable && canDrag
  const rarityColor = RARITY_COLORS[rarity] ?? RARITY_COLORS.Common
  const bothActive = isEvolved && isHero
  const { ref: magnifyRef, scale } = useMagnify(magnify)

  // The Evolution/Hero API art (evolutionImageUrl/heroImageUrl) is the REAL
  // in-game card -- it already has the accurate shimmer frame and gem/crown
  // badge baked into the image itself. Earlier this just recolored the
  // background behind the plain BASE art and drew a fake CSS border on top,
  // which is why it didn't look like the game -- there's no CSS frame to
  // build here, just show the real asset.
  const preferredUrl = bothActive ? (heroImageUrl ?? evolutionImageUrl)
    : isHero ? heroImageUrl
      : isEvolved ? evolutionImageUrl
        : null

  // Some very recently-added Hero cards (confirmed 2026-08-05: Hero Valkyrie,
  // Hero Berserker) have a real heroMedium URL in the official API's own card
  // catalog, but the actual image file 404s on Supercell's asset CDN -- the
  // art just hasn't been published yet even though the API already points to
  // it. Retrying the SAME broken URL forever would show nothing at all, so
  // this steps down a real fallback chain instead: preferred art -> base card
  // art -> (only if even that fails) plain initials. `specialArtFailed`
  // resets whenever the preferred URL itself changes (different card/variant)
  // so a fresh candidate always gets its own chance to load.
  const [specialArtFailed, setSpecialArtFailed] = useState(false)
  useEffect(() => { setSpecialArtFailed(false) }, [preferredUrl])
  const usingRealFrame = !!preferredUrl && !specialArtFailed
  const displayUrl = usingRealFrame ? preferredUrl : imageUrl

  const [imgError, setImgError] = useState(false)
  useEffect(() => { setImgError(false) }, [displayUrl])

  const backdrop = bothActive ? EVO_HERO_GLOW_BG
    : isHero ? HERO_GLOW_BG
      : isEvolved ? EVO_GLOW_BG
        : isAmbiguous ? EVO_HERO_GLOW_BG
          : RARITY_GRADIENTS[rarity] ?? RARITY_GRADIENTS.Common

  // Only draw our own frame (border + inset ring) for the plain rarity view --
  // once we're showing the real Evolution/Hero card art, that art already IS
  // the frame, and an extra CSS border on top just double-frames it.
  // Ambiguous never uses real art (see isAmbiguous prop doc), so it always
  // falls into this branch -- a distinct two-tone glow (not a solid purple
  // or solid gold) signals "special but which one is unknown."
  //
  // Base (plain-rarity) cards used to get a flat GOLD outer border
  // regardless of rarity, with the actual rarity color only as a subtle
  // 2px INSET ring -- real feedback (2026-08-21): "there is no extra frame
  // to show the type of card... the name is colored that way and it is not
  // very relevant." Relying on small colored name text as the primary
  // rarity signal doesn't hold up in dense grids where the name may not
  // even be shown by default (see nameOnInteraction below) -- the frame
  // itself now IS the rarity color (an outer glow + border), a much more
  // obvious at-a-glance signal that doesn't depend on reading text at all.
  const glow = usingRealFrame
    ? (bothActive
        ? '0 0 14px 4px rgba(212,175,55,0.5), 0 0 14px 4px rgba(180,60,255,0.4)'
        : isHero ? '0 0 14px 4px rgba(212,175,55,0.55)' : '0 0 14px 4px rgba(180,60,255,0.55)')
    : isAmbiguous
      ? '0 0 14px 4px rgba(212,175,55,0.4), 0 0 14px 4px rgba(180,60,255,0.4)'
      : hasEvolution && hasHero
        ? '0 0 0 2px #D4AF37, 0 0 0 4px #C084FC'
        : `0 0 8px 1px ${rarityColor}90`

  return (
    <div
      onClick={onClick}
      draggable={dragEnabled}
      onDragStart={dragEnabled ? (e) => {
        setIsDragging(true)
        e.dataTransfer.setData('text/plain', name)
        e.dataTransfer.effectAllowed = 'copy'
        onDragStart?.()
      } : undefined}
      onDragEnd={dragEnabled ? (e) => { setIsDragging(false); onDragEnd?.(e) } : undefined}
      onMouseEnter={nameOnInteraction ? () => setPressed(true) : undefined}
      onMouseLeave={nameOnInteraction ? () => setPressed(false) : undefined}
      onTouchStart={nameOnInteraction ? () => setPressed(true) : undefined}
      onTouchEnd={nameOnInteraction ? () => setTimeout(() => setPressed(false), 600) : undefined}
      className={`
        relative flex flex-col items-center transition-all duration-150 ease-out
        ${onClick ? 'cursor-pointer' : ''}
        ${dragEnabled ? 'cursor-grab active:cursor-grabbing' : ''}
        ${selected ? 'ring-2 ring-accent shadow-glow' : ''}
        ${isDragging ? 'opacity-40' : ''}
      `}
      style={{ transform: `scale(${isDragging ? scale * 0.92 : scale})`, zIndex: scale > 1.01 ? 30 : undefined }}
    >
      <div
        ref={magnifyRef}
        className={`relative ${SIZE_MAP[size]} rounded-lg overflow-hidden shrink-0`}
        style={{
          background: backdrop,
          borderWidth: usingRealFrame ? 0 : 3,
          borderStyle: 'solid',
          // Gold stays reserved for "this card has an Evolution/Hero/
          // ambiguous angle going on" (matches the crest badges/glow used
          // for those below) -- the plain case's border is the rarity color
          // itself now, not gold, so rarity reads from the frame shape at a
          // glance instead of needing gold-vs-not-gold plus a subtle inset ring.
          borderColor: usingRealFrame || isAmbiguous || (hasEvolution && hasHero) ? '#D4AF37' : rarityColor,
          boxShadow: glow,
        }}
      >
        {/* Elixir droplet -- the real in-game shape (round top, pointed bottom),
            not a plain diamond. Classic CSS teardrop: round 3 corners, square the
            4th, then rotate 45°. Purple is the real in-game elixir color
            regardless of season. Skipped on real Evolution/Hero art, which
            already shows its own cost badge. */}
        {elixir != null && !usingRealFrame && (
          <div className="absolute -top-1 -left-1 z-20 w-6 h-6 flex items-center justify-center">
            <div className="absolute inset-0 rounded-[50%_50%_50%_0] rotate-45 shadow"
              style={{ background: 'radial-gradient(circle at 35% 30%, #C77DFF, #7B2FBE 60%, #5A1F94)' }} />
            <span className="relative text-white text-[11px] font-bold" style={{ textShadow: '0 1px 1px rgba(0,0,0,0.6)' }}>{elixir}</span>
          </div>
        )}

        {/* Confirmed active but Evolution-vs-Hero genuinely undeterminable --
            a two-tone "?" badge, deliberately distinct from both the pure
            purple Evolution glow and pure gold Hero glow, so it can't be
            mistaken for a confident answer. */}
        {isAmbiguous && (
          <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 z-20">
            <div className="w-4 h-4 rounded-full shadow border border-white/50 flex items-center justify-center text-[9px] font-bold text-white"
              style={{ background: 'linear-gradient(135deg, #7B2FBE 50%, #D4AF37 50%)' }}
              title="Confirmed evolved or hero'd this match -- real data can't tell which for this card">
              ?
            </div>
          </div>
        )}

        {/* Evo / Hero capability crests -- small gem badges at top-center
            (like the real in-game frame's top crest), not a plain text tag.
            Base view only; the real evolved/hero art already shows its own
            crest baked in, so this doesn't double up. */}
        {!usingRealFrame && !isAmbiguous && (hasEvolution || hasHero) && (
          <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 z-20 flex gap-1">
            {hasEvolution && (
              <div className="w-3 h-3 rotate-45 rounded-[2px] shadow border border-purple-200"
                style={{ background: 'linear-gradient(160deg, #C77DFF, #7B2FBE)' }} title="Evolution available" />
            )}
            {hasHero && (
              <div className="w-3 h-3 rotate-45 rounded-[2px] shadow border border-yellow-100"
                style={{ background: 'linear-gradient(160deg, #F5DA81, #D4AF37)' }} title="Hero available" />
            )}
          </div>
        )}

        {/* "ⓘ" detail badge -- for contexts where the card's own onClick is
            already spoken for (deck-building toggle/drag/select), this is
            the non-conflicting way to still open its full details. Small and
            semi-transparent so it doesn't compete with the card art, but
            always visible (not hover-only) so it works on touch too. */}
        {onInfoClick && (
          <button
            type="button"
            draggable={false}
            onClick={(e) => { e.stopPropagation(); onInfoClick() }}
            title="Card details"
            className="absolute top-0.5 right-0.5 z-30 w-3.5 h-3.5 rounded-full flex items-center justify-center
                       bg-black/50 hover:bg-black/80 text-white/80 hover:text-white text-[8px] font-bold leading-none
                       transition-colors">
            i
          </button>
        )}

        {/* Card art. Real Evolution/Hero art is shown uncropped (object-contain) --
            it has its own frame shape (including a badge that pokes above the
            main rectangle), and cropping it like a plain portrait clips that
            badge. Base rarity art has no such overhang, so it still fills the
            tile edge-to-edge (object-cover). */}
        {imgError || !displayUrl ? (
          <div className="w-full h-full flex items-center justify-center text-white/70 text-xs text-center px-1">
            {name.split(' ').map(w => w[0]).join('').slice(0, 3)}
          </div>
        ) : (
          <img
            src={displayUrl}
            alt={name}
            loading="lazy"
            decoding="async"
            className={`w-full h-full ${usingRealFrame ? 'object-contain' : 'object-cover'}`}
            onError={() => (usingRealFrame ? setSpecialArtFailed(true) : setImgError(true))}
          />
        )}

        {/* Level badge -- real feedback (2026-08-27): "the card level blocks
            the image of the cards, maybe smaller text and maybe add that to
            another corner of the card rather than on their faces." Used to
            be a centered pill floating right over the character art; the
            bottom-right corner is the one spot on this card with nothing
            else in it (top-left is the elixir droplet, top-center is the
            evo/hero crest, top-right is the info button), and a plain
            number (no "Level" label) reads fine that small. */}
        {level != null && (
          <div className={`absolute bottom-0.5 right-0.5 z-10 min-w-[1rem] px-1 rounded text-center text-[8px]
                           font-bold text-white shadow ${isHero ? 'bg-gold' : isEvolved ? 'bg-purple-500' : isAmbiguous ? 'bg-gradient-to-r from-purple-500 to-gold' : 'bg-accent'}`}
            title={`Level ${level}`}>
            {level}
          </div>
        )}

        {/* "Close to upgrade" warning -- real feedback (2026-09-02): "if a
            card is eight out of ten to an upgrade, then have the warning on
            the side." Bottom-left is the only corner nothing else claims. */}
        {upgradeClose && (
          <div className="absolute bottom-0.5 left-0.5 z-10 min-w-[1rem] h-4 px-1 rounded-full flex items-center
                           justify-center text-[9px] font-bold text-white shadow bg-orange-500"
            title="Close to enough copies for the next level">
            ⚠
          </div>
        )}

        {/* Name plaque, overlaid at the bottom like the in-game card -- text color signals
            rarity (Common/Rare/Epic/Legendary/Champion) at a glance, without opening the card.
            Skipped entirely when nameOnInteraction is on (see the centered overlay below instead). */}
        {showName && !nameOnInteraction && (
          <div className="absolute bottom-0 left-0 right-0 bg-black/70 backdrop-blur-[1px] px-1 py-0.5 z-10">
            <span className={`${NAME_SIZE_MAP[size]} font-bold text-center block truncate leading-tight`}
              style={{ color: rarityColor }}>
              {name}
            </span>
          </div>
        )}

        {/* nameOnInteraction: no permanent name text at all (matches the real
            in-game collection grid, which shows no name either) -- instead a
            centered overlay reveals the full name while hovered (desktop),
            pressed (touch), or dragged. Real feedback (2026-08-21): "when
            you click/touch/drag the picture, it will show the name in the
            middle of the image." pointer-events-none so it never steals the
            tap/click/drag it's reacting to. */}
        {showName && nameOnInteraction && (isDragging || pressed) && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/60 pointer-events-none px-1">
            <span className={`${NAME_SIZE_MAP[size]} font-bold text-center leading-tight`} style={{ color: rarityColor }}>
              {name}
            </span>
          </div>
        )}
      </div>

      {/* Stats */}
      {showStats && (hitpoints || dps) && (
        <div className="flex gap-2 text-xs text-text-secondary mt-1">
          {hitpoints && <span>❤️ {Math.round(hitpoints).toLocaleString()}</span>}
          {dps && <span>⚡ {Math.round(dps)}</span>}
        </div>
      )}

      {/* Owned-copies progress -- real feedback (2026-09-02): "i want
          collections to show card levels card shards and cards to the next
          level upgrade under the cards" -- folded into the card tile itself
          instead of a separate standalone grid. */}
      {ownedCount != null && (
        <div className="text-center text-[9px] text-text-muted mt-0.5 leading-tight">
          {ownedCount.toLocaleString()}{copiesNeeded != null ? `/${copiesNeeded.toLocaleString()}` : ''}
        </div>
      )}
    </div>
  )
}

// Shared rarity-colored/bold name treatment for the many places a card name
// shows up as plain text rather than inside a full CardImage tile (tables,
// chip lists, modal headers) -- keeps that styling consistent app-wide
// instead of each page inventing its own.
export function CardName({ name, rarity, className = '' }: { name: string; rarity?: string; className?: string }) {
  const color = RARITY_COLORS[rarity ?? 'Common'] ?? RARITY_COLORS.Common
  return <span className={`font-bold ${className}`} style={{ color }}>{name}</span>
}
