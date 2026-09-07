import { useState, useRef, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Search, Clipboard, Copy, Check, X as XIcon, ChevronLeft, ChevronRight } from 'lucide-react'
import CardImage from './CardImage'
import { useCardDetail } from '../contexts/CardDetailContext'
import { searchCardsByName } from '../utils/cardSearch'
import { parseClipboardDeck, deckToClipboardText } from '../utils/deckClipboard'
import { copiesForNextLevel } from '../utils/cardUpgradeCost'

/**
 * Shared deck-building primitives -- extracted 2026-08-07 from DeckLabPage.tsx
 * so other pages (Win Predictor, Synergy) can reuse the exact same real
 * drag-and-drop slot / Evolution-Hero-Wild slot modeling / searchable card
 * picker instead of each reinventing a thinner version. Slot rules mirror
 * the real game (see cr_platform/backend/services/card_service.py's
 * SLOT_THRESHOLDS): 1 Evolution slot (Arena 3 / 800 trophies), 1 Hero slot
 * (Arena 5 / 1,300), 1 Wild slot (Arena 10 / 3,000, flexible between the two).
 */

export type SlotCounts = { evolution_slots: number; hero_slots: number; wild_slots: number }
export type SlotType = 'evolution' | 'hero' | null
export type Role = 'evolution' | 'hero' | 'wild' | null

export const SLOT_ROLE = (index: number): Role => index === 0 ? 'evolution' : index === 1 ? 'hero' : index === 2 ? 'wild' : null

export const ROLE_META: Record<'evolution' | 'hero' | 'wild', { label: string; border: string; text: string; threshold: string }> = {
  evolution: { label: 'EVO SLOT', border: '#7B2FBE', text: '#C084FC', threshold: 'Arena 3 · 800🏆' },
  hero: { label: 'HERO SLOT', border: '#D4AF37', text: '#D4AF37', threshold: 'Arena 5 · 1,300🏆' },
  wild: { label: 'WILD SLOT', border: '#B47FE0', text: '#E8C4F5', threshold: 'Arena 10 · 3,000🏆' },
}

/**
 * CORRECTED 2026-09-07 (real feedback, backed by real evidence): "non
 * evo/hero cards can go anywhere in the deck, just check real decks from
 * real users and you will see" -- the user pointed at their own real
 * collected deck history (My Decks), where most real decks show NO
 * Evolution or Hero use at all. That's only possible if the Evolution/
 * Hero/Wild slots are real, LABELED positions in the deck editor but do
 * NOT restrict which card can occupy them -- any ordinary card can sit in
 * the "Evolution slot" position and simply plays as a normal card there;
 * the evolution/hero effect only activates for whichever card is BOTH
 * capable AND actually placed there. A prior pass here (see git history)
 * had this backwards -- treating the label as an ELIGIBILITY GATE that
 * blocked ineligible cards from the position at all, which is why the
 * in-app deck builder couldn't reproduce decks real players build every
 * day with zero Evolution/Hero cards in them.
 *
 * The rendering side already handled this correctly and needed no change:
 * `assignmentFor` below already returns null (plain card, no crest/glow)
 * for an ineligible card sitting in a special slot -- only the PLACEMENT
 * restriction was wrong.
 *
 * What's still real and unchanged: Tower Troops have their own dedicated
 * slot and are never eligible for any of the 8 real deck slots. Champions
 * are still blocked from the 5 REGULAR slots specifically (a separate,
 * independently-verified rule -- Champions have always required a
 * dedicated Hero/Wild slot since their 2021 introduction) -- but ARE now,
 * like every other card, freely placeable in the Evolution/Hero/Wild slots
 * regardless of whether they're the "right" special type for that slot.
 */
export function isCardEligibleForSlot(card: any, index: number): boolean {
  if (!card) return true
  // Tower Troops have their own dedicated slot (see TowerSlot below) and are
  // never eligible for any of the 8 real deck slots -- checked here too
  // (not just at each drop-handler call site) so this one function is the
  // single source of truth for "can this card go here" everywhere.
  if (card.type === 'Tower Troop') return false
  const role = SLOT_ROLE(index)
  if (!role) return card.rarity !== 'Champion' // regular slots: anything except Champions
  return true // Evolution/Hero/Wild: any real card -- see the correction above
}

function loadConnected(): { player: string; tag: string; levels: Record<string, number>; unlocked_slots?: SlotCounts } | null {
  try {
    const raw = localStorage.getItem('cr_connected_collection')
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

const LEVELS_STORAGE_KEY = 'cr_collection_levels'

function loadStoredLevels(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(LEVELS_STORAGE_KEY) ?? '{}')
  } catch {
    return {}
  }
}

export function useEditableLevels(connectedLevels: Record<string, number> | undefined) {
  const [levels, setLevels] = useState<Record<string, number>>(() => loadStoredLevels())
  const levelFor = (name: string) => levels[name] ?? connectedLevels?.[name] ?? 11
  const bump = (name: string, delta: number) => {
    setLevels(prev => {
      const next = { ...prev, [name]: Math.max(1, Math.min(18, levelFor(name) + delta)) }
      localStorage.setItem(LEVELS_STORAGE_KEY, JSON.stringify(next))
      return next
    })
  }
  return { levelFor, bump }
}

// Special deck slots unlock by Arena and are never lost once reached. The
// checkbox toggle lets a user explicitly say "I only have the Evolution slot
// unlocked, not Hero" (or override to test a hypothetical) rather than the
// UI just assuming everything's always available -- each slot type is real
// binary unlocked/locked, matching the actual game (there's no "how many"
// beyond 1 of each type -- Evolution/Hero/Wild are 3 distinct slot roles,
// not stackable counts of the same role).
export function useSlots() {
  const connected = loadConnected()
  const [manual, setManual] = useState<SlotCounts>(
    connected?.unlocked_slots ?? { evolution_slots: 1, hero_slots: 1, wild_slots: 1 }
  )
  const [wildAs, setWildAs] = useState<'evolution' | 'hero'>('evolution')

  const unlockedFor = (role: Role): boolean =>
    role === 'evolution' ? manual.evolution_slots > 0
    : role === 'hero' ? manual.hero_slots > 0
      : role === 'wild' ? manual.wild_slots > 0
        : false

  const assignmentFor = (index: number, card: any): SlotType => {
    const role = SLOT_ROLE(index)
    if (!role || !unlockedFor(role)) return null
    // Champions have no alternate Evolution/Hero art (they always show their
    // own permanent Champion art -- see CardImage's rarity-based styling),
    // so there's nothing to "assign" here for them even in a slot they're
    // legitimately eligible for (Hero/Wild) -- null is the correct, honest
    // answer, not a sign anything's wrong.
    if (card?.rarity === 'Champion') return null
    if (role === 'evolution') return card?.has_evolution ? 'evolution' : null
    if (role === 'hero') return card?.has_hero ? 'hero' : null
    if (wildAs === 'evolution') return card?.has_evolution ? 'evolution' : null
    return card?.has_hero ? 'hero' : null
  }

  return { connected, manual, setManual, wildAs, setWildAs, unlockedFor, assignmentFor }
}

export function SlotBar({ slots }: { slots: ReturnType<typeof useSlots> }) {
  const { connected, manual, setManual } = slots
  const chips: { key: keyof SlotCounts; label: string; threshold: string }[] = [
    { key: 'evolution_slots', label: 'Evolution', threshold: 'Arena 3 · 800🏆' },
    { key: 'hero_slots', label: 'Hero', threshold: 'Arena 5 · 1,300🏆' },
    { key: 'wild_slots', label: 'Wild', threshold: 'Arena 10 · 3,000🏆' },
  ]
  return (
    <div className="bg-bg-surface border border-border rounded-xl p-3 mb-4">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold text-text-secondary">Special Deck Slots</span>
        {connected && <span className="text-xs text-text-muted">synced from {connected.player}</span>}
      </div>
      <div className="flex flex-wrap gap-2">
        {chips.map(({ key, label, threshold }) => (
          <label key={key}
            className={`flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg cursor-pointer
              ${manual[key] > 0 ? 'bg-accent/20 text-accent' : 'bg-bg-card text-text-muted'}`}>
            <input type="checkbox" checked={manual[key] > 0}
              onChange={e => setManual({ ...manual, [key]: e.target.checked ? 1 : 0 })}
              className="accent-red-500" />
            {label} {manual[key] > 0 ? '✓' : `🔒 ${threshold}`}
          </label>
        ))}
      </div>
    </div>
  )
}

/**
 * Central place-card-in-deck logic, shared by every deck-builder consumer
 * (Build/Counter tabs, Win Predictor, Collection's checker) so drag/drop
 * placement behaves identically everywhere instead of each page
 * reimplementing its own -- previously every consumer's own toggle function
 * ignored the slot index `DeckSlots` already passed through and always did
 * `[...deck, name]` (append to the end), so a card visually always landed
 * in the first empty slot no matter which of the 8 boxes it was dropped on.
 *
 * - Clicking/dragging a card already in the deck with no target slot
 *   removes it (clears that slot in place -- does NOT shift later cards
 *   left, unlike the old filter-based removal, so other cards' positions
 *   stay stable).
 * - Clicking a card from the picker (never has a target slot) fills the
 *   first empty slot.
 * - Dragging a card onto a specific slot (`targetIndex`) places it exactly
 *   there, swapping with whatever card (if any) already occupied that slot.
 * - Dragging a card that came from one of THIS deck's own slots
 *   (`fromIndex`) is a real move: the origin slot gets whatever was
 *   displaced by the swap, or becomes empty if the target was empty --
 *   never leaves a duplicate behind.
 * - A real deck can never contain the same card twice, in any two slots
 *   (fixed here: dragging a card from the picker onto a target slot while
 *   that exact card already sits in a different slot used to silently
 *   create a duplicate, since only within-deck drags -- which pass
 *   `fromIndex` -- cleared their origin slot; a picker-drag of an
 *   already-placed card had no `fromIndex` at all). Now treated as a MOVE
 *   in both cases: if the card is already elsewhere in the deck, that
 *   slot is what gets cleared/swapped-into, regardless of where the drag
 *   technically started.
 *
 * `cards` (the full card catalog, for rarity/type lookup) is required so
 * every placement can be checked against real slot eligibility (see
 * isCardEligibleForSlot) -- e.g. a Champion dropped on a REGULAR slot, or a
 * Tower Troop dropped on any of the 8 real slots, is rejected (the deck is
 * returned unchanged, same as any other invalid drop) rather than silently
 * accepted somewhere it can't
 * actually go in the real game. A swap is only completed if BOTH cards end
 * up somewhere they're genuinely eligible for.
 */
export function toggleDeckCard(deck: string[], name: string, cards: any[], targetIndex?: number, fromIndex?: number): string[] {
  const next = [...deck]
  const cardFor = (n: string) => cards.find(c => c.name === n)

  if (targetIndex != null) {
    if (!isCardEligibleForSlot(cardFor(name), targetIndex)) return deck

    // If this exact card is already sitting in a different slot, this drop
    // is a move of that card, not a fresh placement -- resolve the real
    // origin regardless of whether the drag itself reported one (a drag
    // that started at the picker never does, even when the card it's
    // dragging happens to already be in the deck).
    const existingElsewhere = next.findIndex((n, i) => n === name && i !== targetIndex)
    const effectiveFrom = fromIndex ?? (existingElsewhere !== -1 ? existingElsewhere : undefined)

    const displaced = next[targetIndex]
    if (effectiveFrom != null && effectiveFrom !== targetIndex && displaced !== undefined
      && !isCardEligibleForSlot(cardFor(displaced), effectiveFrom)) {
      return deck // completing the move/swap would strand the displaced card somewhere it can't legally go
    }
    next[targetIndex] = name
    if (effectiveFrom != null && effectiveFrom !== targetIndex) {
      if (displaced !== undefined) next[effectiveFrom] = displaced
      else delete next[effectiveFrom]
    }
    return next
  }

  // No target slot (click, or a drag that didn't resolve to one) -- toggle
  // off if already present anywhere (defensively clears every occurrence,
  // though there should only ever be one now), else fill the first slot
  // this specific card is actually eligible for.
  if (next.includes(name)) {
    for (let i = 0; i < next.length; i++) if (next[i] === name) delete next[i]
    return next
  }
  const card = cardFor(name)
  for (let i = 0; i < 8; i++) {
    if (!next[i] && isCardEligibleForSlot(card, i)) { next[i] = name; return next }
  }
  return next // deck is full, or no eligible empty slot -- no-op rather than misplacing it
}

export function EmptyCardSlot({ role, unlocked, hovered }: { role: Role; unlocked: boolean; hovered: boolean }) {
  const meta = role ? ROLE_META[role] : null
  return (
    <div
      className={`w-16 h-20 rounded-lg border-2 border-dashed flex flex-col items-center justify-center
                 transition-all duration-150 ease-out ${hovered ? 'scale-110' : 'scale-100'}`}
      style={hovered
        ? { borderColor: '#C23B3B', backgroundColor: 'rgba(194,59,59,0.15)' }
        : meta ? { borderColor: unlocked ? meta.border : '#4A2E2E', opacity: unlocked ? 1 : 0.6 }
          : { borderColor: '#4A2E2E' }}
    >
      <span className={`text-lg transition-colors duration-150 ${hovered ? 'text-accent' : 'text-text-muted'}`}>+</span>
      {meta && (
        <span className="text-[7px] font-bold leading-tight text-center px-0.5"
          style={{ color: unlocked ? meta.text : '#8A7568' }}>
          {unlocked ? meta.label : `🔒 ${meta.threshold}`}
        </span>
      )}
    </div>
  )
}

export function DeckSlots({ deck, cards, onToggle, slots, levels, onLevelChange }: {
  deck: string[]; cards: any[]; onToggle: (n: string, targetIndex?: number, fromIndex?: number) => void
  slots: ReturnType<typeof useSlots>; levels: Record<string, number>
  onLevelChange?: (name: string, delta: number) => void
}) {
  const { openCard } = useCardDetail()
  const cardFor = (n: string) => cards.find(c => c.name === n)

  // Real slot-index-aware drag targeting: the WHOLE 8-slot grid is one drop
  // zone (not 8 independent ones) so a drop anywhere inside it resolves to
  // whichever slot is nearest the pointer -- a small forgiving "magnetic"
  // radius instead of needing to land pixel-perfect on one 64x80px box.
  // Falls back to "no valid target" (drag cancelled) only when the drop
  // happens entirely outside this container.
  const slotRefs = useRef<Array<HTMLDivElement | null>>(Array(8).fill(null))
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const draggedFromIndex = useRef<number | null>(null)

  const nearestSlotIndex = (clientX: number, clientY: number): number | null => {
    let best: number | null = null
    let bestDist = Infinity
    slotRefs.current.forEach((el, i) => {
      if (!el) return
      const r = el.getBoundingClientRect()
      const cx = r.left + r.width / 2
      const cy = r.top + r.height / 2
      const dist = Math.hypot(clientX - cx, clientY - cy)
      if (dist < bestDist) { bestDist = dist; best = i }
    })
    return best
  }

  return (
    <div className="grid grid-cols-4 gap-2 mb-2"
      onDragOver={(e) => {
        e.preventDefault()
        setHoverIndex(nearestSlotIndex(e.clientX, e.clientY))
      }}
      onDragLeave={(e) => {
        // Only clear if the pointer actually left the whole grid (not just
        // moving from one slot's box into another's) -- relatedTarget is
        // null when leaving the browser window/dragging over a non-DOM area.
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setHoverIndex(null)
      }}
      onDrop={(e) => {
        e.preventDefault()
        const name = e.dataTransfer.getData('text/plain')
        const target = nearestSlotIndex(e.clientX, e.clientY)
        setHoverIndex(null)
        if (name && target != null && cardFor(name)?.type !== 'Tower Troop') {
          onToggle(name, target, draggedFromIndex.current ?? undefined)
        }
        draggedFromIndex.current = null
      }}
    >
      {Array.from({ length: 8 }).map((_, i) => {
        const name = deck[i]
        const card = name ? cardFor(name) : null
        const role = SLOT_ROLE(i)
        const unlocked = role ? slots.unlockedFor(role) : true
        const assignment = card ? slots.assignmentFor(i, card) : null
        const meta = role ? ROLE_META[role] : null
        return (
          <div key={i} ref={(el) => { slotRefs.current[i] = el }} className="rounded-lg"
            style={meta ? { boxShadow: `0 0 0 2px ${unlocked ? meta.border : '#4A2E2E'}55` } : undefined}>
            {name ? (
              <motion.div className="relative"
                initial={{ scale: 0.7, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                transition={{ type: 'spring', stiffness: 400, damping: 22 }}>
                <CardImage name={name} imageUrl={card?.image_url}
                  evolutionImageUrl={card?.evolution_image_url} heroImageUrl={card?.hero_image_url}
                  rarity={card?.rarity} size="sm"
                  level={levels[name] ?? 11}
                  isEvolved={assignment === 'evolution'} isHero={assignment === 'hero'}
                  onClick={() => onToggle(name)} onInfoClick={() => openCard(name)} selected
                  draggable
                  onDragStart={() => { draggedFromIndex.current = i }}
                  onDragEnd={(e) => { if (e.dataTransfer.dropEffect === 'none') { onToggle(name); draggedFromIndex.current = null } }} />
                {hoverIndex === i && (
                  <div className="absolute inset-0 rounded-lg ring-2 ring-accent pointer-events-none z-20" />
                )}
                {role === 'wild' && unlocked && card?.has_evolution && card?.has_hero && (
                  <button onClick={(e) => { e.stopPropagation(); slots.setWildAs(w => w === 'evolution' ? 'hero' : 'evolution') }}
                    className="absolute -bottom-1 -right-1 w-5 h-5 rounded-full bg-bg-card border border-border
                               text-[9px] flex items-center justify-center hover:bg-border z-30"
                    title="Switch Wild slot between Evolution / Hero">
                    {slots.wildAs === 'evolution' ? '⬆' : '★'}
                  </button>
                )}
                {onLevelChange && (
                  <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 flex items-center gap-0.5 z-30">
                    <button onClick={(e) => { e.stopPropagation(); onLevelChange(name, -1) }}
                      className="w-4 h-4 rounded-full bg-bg-card border border-border text-[8px] flex items-center justify-center hover:bg-border">−</button>
                    <button onClick={(e) => { e.stopPropagation(); onLevelChange(name, 1) }}
                      className="w-4 h-4 rounded-full bg-bg-card border border-border text-[8px] flex items-center justify-center hover:bg-border">+</button>
                  </div>
                )}
              </motion.div>
            ) : (
              <EmptyCardSlot role={role} unlocked={unlocked} hovered={hoverIndex === i} />
            )}
          </div>
        )
      })}
    </div>
  )
}

/** Paste side of the copy/paste deck feature (see FavoriteButton.tsx for the
 * copy side, and utils/deckClipboard.ts for the shared format) -- real
 * feedback (2026-08-22): "being able to copy and paste entire decks from
 * different pages to different pages on the site." Placing each pasted
 * card through `toggleDeckCard` (same function every click/drag placement
 * already goes through) means Evolution/Hero/Wild slot eligibility is
 * respected automatically -- no separate placement logic to get wrong. */
export function PasteDeckButton({ cards, onPaste }: { cards: any[]; onPaste: (names: string[]) => void }) {
  const [status, setStatus] = useState<'idle' | 'pasted' | 'error'>('idle')

  const paste = async () => {
    try {
      const text = await navigator.clipboard.readText()
      const validNames = new Set(cards.map(c => c.name))
      const names = parseClipboardDeck(text, validNames)
      if (names.length === 0) {
        setStatus('error')
      } else {
        onPaste(names)
        setStatus('pasted')
      }
    } catch {
      setStatus('error')
    }
    setTimeout(() => setStatus('idle'), 1500)
  }

  return (
    <button onClick={paste} title="Paste a deck copied from anywhere else on the site"
      className="flex items-center gap-1.5 text-xs bg-bg-card text-text-secondary hover:text-text-primary
                 px-2.5 py-1.5 rounded-lg transition-colors shrink-0">
      {status === 'pasted' ? <Check size={13} className="text-cyan-300" />
        : status === 'error' ? <XIcon size={13} className="text-danger" />
        : <Clipboard size={13} />}
      {status === 'pasted' ? 'Pasted!' : status === 'error' ? 'No deck found' : 'Paste Deck'}
    </button>
  )
}

/** Copy side of the same feature, for a deck still being BUILT (not yet a
 * saved favorite) -- real gap found 2026-08-23: FavoriteButton.tsx already
 * has its own copy icon, but only once a deck is favorited/completed. The
 * deck panel itself (Build/Counter tabs, Synergy's Deck Network) had paste
 * but no way to copy a work-in-progress deck back out, which "copy and
 * paste should also work with everything even the deck builders" calls for. */
export function CopyDeckButton({ cards }: { cards: string[] }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(deckToClipboardText(cards))
      setCopied(true)
    } catch {
      setCopied(false)
    }
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <button onClick={copy} disabled={cards.filter(Boolean).length === 0}
      title="Copy this deck to paste anywhere else on the site"
      className="flex items-center gap-1.5 text-xs bg-bg-card text-text-secondary hover:text-text-primary
                 disabled:opacity-40 disabled:cursor-not-allowed px-2.5 py-1.5 rounded-lg transition-colors shrink-0">
      {copied ? <Check size={13} className="text-cyan-300" /> : <Copy size={13} />}
      {copied ? 'Copied!' : 'Copy Deck'}
    </button>
  )
}

// Now has a real search box -- previously this picker (used by Build/Counter/
// Win Predictor) had no way to filter, only Browse Cards did, forcing anyone
// with a specific card in mind to scroll a ~120-card grid to find it.
export function CardPicker({ cards, deck, onToggle, levels, counts, onLevelChange }: {
  cards: any[]; deck: string[]; onToggle: (n: string) => void
  /** Real owned card levels (Collection page) -- when given, each card shows
   * its real level like every other deck slot in the app (real feedback,
   * 2026-08-22: Collection's picker showed "no level and none of the logic
   * applied from the deck builder feature in build"), and owned cards sort
   * ahead of unowned ones within each search-relevance group -- a simple,
   * honest "recommend what you can actually play" without inventing a
   * synthetic scoring system. Omitted everywhere else (Build/Counter tabs
   * have no real owned-level data to show). */
  levels?: Record<string, number>
  /** Real owned copy counts (Collection page only, from a connected
   * player) -- paired with `levels` to show a real "{owned}/{needed
   * for next level}" line under each tile plus a close-to-upgrade warning
   * badge, replacing Collection's old separate "Your Card Levels" grid
   * (2026-09-02: "remove the long page of discards and card levels and just
   * add that to the card section under the buildable deck"). */
  counts?: Record<string, number>
  /** Bump a card's SIMULATED level by delta (Collection page, manual/
   * unconnected mode only) -- lets a card's level still be hand-set here now
   * that the standalone "Your Card Levels" grid (which used to be the only
   * place with these steppers) is gone. Omitted in connected mode, where
   * levels are real synced data, not something to hand-edit. */
  onLevelChange?: (name: string, delta: number) => void
}) {
  const { openCard } = useCardDetail()
  const [search, setSearch] = useState('')
  const reelRef = useRef<HTMLDivElement>(null)
  // Prefix matches rank first -- see cardSearch.ts.
  let deckable = searchCardsByName(cards.filter(c => c.type !== 'Tower Troop'), search)
  if (levels) {
    deckable = [...deckable].sort((a, b) => {
      const ownedA = (levels[a.name] ?? 0) > 0, ownedB = (levels[b.name] ?? 0) > 0
      return ownedA === ownedB ? 0 : ownedA ? -1 : 1
    })
  }
  // REDESIGNED 2026-09-02 -- real bug found in production from the first
  // version of this (2026-09-01): it wrapped to a position (scrollLeft ~1,
  // or ~max-1) that was STILL inside its own "am I at the edge" detection
  // zone, so the very next scroll-settle check saw itself as still at an
  // edge and wrapped again -- forever ("scrolling on its own and
  // glitching," a real bug, not a one-off). Real feedback for the redesign:
  // "i just want say page 1 scrolling to 2, 3 so on then to the last page
  // and when user scrolls that goes back to the first page." Free-position
  // scrolling-with-edge-detection is gone entirely, replaced with discrete
  // PAGES (one page = one full visible width of cards): the buttons and a
  // debounced wheel gesture each advance exactly one page, wrapping from
  // the last page back to the first (and back). No continuous-position
  // edge check is left to re-trigger itself. Touch/trackpad drag uses
  // native CSS scroll-snap (scrollSnapAlign on every card below) so a real
  // finger/trackpad gesture can never overshoot past either end in the
  // first place -- the browser itself stops it at the last card, which is
  // what makes this immune to the class of bug above (nothing here decides
  // "am I at the edge" from a moving scroll position anymore).
  const pageCount = () => {
    const el = reelRef.current
    if (!el || el.clientWidth === 0) return 1
    return Math.max(1, Math.round(el.scrollWidth / el.clientWidth))
  }
  const currentPage = () => {
    const el = reelRef.current
    if (!el || el.clientWidth === 0) return 0
    return Math.round(el.scrollLeft / el.clientWidth)
  }
  const goToPage = (page: number) => {
    const el = reelRef.current
    if (!el) return
    const n = pageCount()
    const wrapped = ((page % n) + n) % n
    el.scrollTo({ left: wrapped * el.clientWidth, behavior: 'smooth' })
  }
  const scrollReel = (dir: 1 | -1) => goToPage(currentPage() + dir)
  // Real feedback (2026-08-26/28): "Make the card scroll horizontal more
  // visible make it like a Wheel circular scroll. And add indicators both
  // clickable and scrollable Make it big and visible." The reel itself
  // already existed (see the big comment block below); what was missing was
  // any visible signal of scroll position/how much more content there is,
  // and the L/R buttons were small and hidden entirely on mobile. This adds
  // a real position track (updates live as the reel scrolls, click anywhere
  // on it to jump straight there) plus bigger, always-visible buttons.
  const [reelScroll, setReelScroll] = useState({ progress: 0, thumbPct: 100, scrollable: false })
  const trackRef = useRef<HTMLDivElement>(null)
  const updateReelScroll = () => {
    const el = reelRef.current
    if (!el) return
    const max = el.scrollWidth - el.clientWidth
    const thumbPct = el.scrollWidth > 0 ? Math.min(100, (el.clientWidth / el.scrollWidth) * 100) : 100
    setReelScroll({ progress: max > 0 ? el.scrollLeft / max : 0, thumbPct, scrollable: max > 4 })
  }
  useEffect(() => { updateReelScroll() }, [deckable.length])
  const jumpToTrackPosition = (clientX: number) => {
    const track = trackRef.current, el = reelRef.current
    if (!track || !el) return
    const rect = track.getBoundingClientRect()
    const frac = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
    goToPage(Math.round(frac * (pageCount() - 1)))
  }
  // Real bug found testing this (2026-08-26): React attaches onWheel as a
  // PASSIVE listener, so e.preventDefault() inside a plain JSX onWheel prop
  // silently no-ops (confirmed via the real console warning: "Unable to
  // preventDefault inside passive event listener invocation") -- an
  // organic hardware wheel event could still fall through to scrolling the
  // page underneath in some browsers even though this component "looked"
  // like it handled it. A real, explicit non-passive native listener
  // (only possible via addEventListener, not JSX) is the only way
  // preventDefault genuinely takes effect here.
  useEffect(() => {
    const el = reelRef.current
    if (!el) return
    // One page per wheel "gesture" (not per pixel of deltaY) -- matches the
    // discrete-paging redesign above. A trackpad/mouse wheel fires many
    // small events per physical gesture, so a short cooldown after each
    // page change absorbs the rest of that same gesture instead of racing
    // through several pages from one swipe.
    let cooldown = false
    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        e.preventDefault()
        if (cooldown) return
        cooldown = true
        scrollReel(e.deltaY > 0 ? 1 : -1)
        setTimeout(() => { cooldown = false }, 450)
      }
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])
  return (
    <div>
      <div className="relative mb-2">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search cards to add..."
          className="w-full bg-bg-card border border-border rounded-lg pl-8 pr-3 py-1.5 text-xs
                     text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent" />
      </div>
      {/* Real feedback, third round on this exact box:
          2026-08-23 removed a bounded VERTICAL scrollbox ("scroll through
          searchable cards but they do not scroll over the entire page" --
          misread at the time as "let it flow with the page").
          2026-08-26 (first fix): brought back a bounded vertical box with
          overscroll-behavior:contain -- still wrong; confirmed via
          AskUserQuestion that "wheel scroll" meant a literal horizontal
          reel/carousel, not a taller vertical list.
          2026-08-26 (this fix): a real horizontal reel -- 3 fixed rows,
          columns flow sideways (grid-flow-col), scrolled on the X axis.
          This is also a strictly more robust fix for "does not scroll over
          everything on the page" than any vertical-box CSS trick: page
          scroll is a Y-axis gesture and this reel only consumes X-axis
          scroll, so the two literally cannot compete for the same gesture
          -- no overscroll-behavior/scroll-chaining edge case to get wrong.
          A native wheel listener (see the useEffect above -- has to be a
          real addEventListener, not a JSX onWheel prop, for preventDefault
          to actually take effect) converts an ordinary vertical mouse-wheel
          motion into horizontal scrolling (real feedback: "make sure it is
          also very easy to use for pc users" -- a plain wheel naturally
          sends deltaY, not deltaX, and most desktop users don't know
          shift+scroll is the native way to scroll something sideways).
          Left/right arrow buttons below give PC users a second, even more
          discoverable way to move through the reel without touching the
          scroll area at all. */}
      <div className="relative px-8">
        {/* Edge fades -- a real visual cue that this is a "wheel" with more
            content past each edge, not just a static grid. Only shown on
            the side there's actually more to scroll to. */}
        {reelScroll.scrollable && reelScroll.progress > 0.01 && (
          <div className="absolute left-8 top-0 bottom-2 w-6 bg-gradient-to-r from-bg-surface to-transparent
                           pointer-events-none z-10" />
        )}
        {reelScroll.scrollable && reelScroll.progress < 0.99 && (
          <div className="absolute right-8 top-0 bottom-2 w-6 bg-gradient-to-l from-bg-surface to-transparent
                           pointer-events-none z-10" />
        )}
        <div ref={reelRef} onScroll={updateReelScroll}
          className="grid grid-flow-col grid-rows-3 auto-cols-[4.5rem] sm:auto-cols-[5.5rem] gap-2
                     overflow-x-auto overflow-y-hidden pb-2 [overscroll-behavior-x:contain] rounded-lg scrollbar-hide
                     snap-x snap-mandatory">
          {/* snap-start on each card (not CardImage itself, which is shared
              by places that don't want scroll-snap) -- native touch/
              trackpad drag naturally stops on a card and, at either end,
              simply can't scroll further: the browser enforces that itself,
              which is what keeps this immune to the "am I at the edge"
              class of bug the old free-scroll version had. */}
          {deckable.map(card => {
            const level = levels && (levels[card.name] ?? 0) > 0 ? levels[card.name] : undefined
            const owned = counts?.[card.name]
            const needed = counts && level != null ? copiesForNextLevel(card.rarity, level) : null
            const closeToUpgrade = owned != null && needed != null && needed > 0 && owned / needed >= 0.8
            // Same "no touched level yet defaults to a sensible 11" display
            // convention the old standalone level grid used -- only for the
            // stepper's own shown number/increment base, not for whether
            // the card counts as "owned" (that's still level > 0 elsewhere).
            const stepperLevel = levels ? (levels[card.name] ?? 11) : 11
            return (
            <div key={card.name} className="snap-start">
              <CardImage name={card.name} imageUrl={card.image_url} rarity={card.rarity}
                elixir={card.elixir_cost} hasEvolution={card.has_evolution} hasHero={card.has_hero} size="sm"
                level={level}
                ownedCount={owned} copiesNeeded={needed} upgradeClose={closeToUpgrade}
                selected={deck.includes(card.name)} onClick={() => onToggle(card.name)}
                onInfoClick={() => openCard(card.name)} draggable nameOnInteraction />
              {/* Manual-mode level steppers -- real replacement for the
                  standalone "Your Card Levels" grid's −/number/+ controls,
                  now living directly under the picker tile instead of a
                  separate page section (2026-09-02). Connected mode passes
                  no onLevelChange (real synced levels aren't hand-edited). */}
              {onLevelChange && (
                <div className="flex items-center justify-center gap-0.5 mt-0.5">
                  <button onClick={() => onLevelChange(card.name, -1)} aria-label={`Lower ${card.name}'s level`}
                    className="w-4 h-4 flex items-center justify-center rounded bg-bg-surface border border-border
                               text-text-secondary hover:text-text-primary text-[10px] leading-none">
                    −
                  </button>
                  <span className="text-[9px] text-text-muted w-4 text-center">{stepperLevel}</span>
                  <button onClick={() => onLevelChange(card.name, 1)} aria-label={`Raise ${card.name}'s level`}
                    className="w-4 h-4 flex items-center justify-center rounded bg-bg-surface border border-border
                               text-text-secondary hover:text-text-primary text-[10px] leading-none">
                    +
                  </button>
                </div>
              )}
            </div>
            )
          })}
        </div>
        {deckable.length > 0 && (
          <>
            {/* Bigger and always visible now (was hidden entirely on mobile,
                and small enough on desktop to be easy to miss -- real
                feedback: "make it big and visible"). */}
            <button onClick={() => scrollReel(-1)} aria-label="Scroll cards left"
              className="flex absolute left-0 top-1/2 -translate-y-1/2 items-center justify-center
                         w-9 h-9 rounded-full bg-bg-card border-2 border-border text-text-secondary
                         hover:text-text-primary hover:border-accent active:scale-95 transition-all shadow-card z-20">
              <ChevronLeft size={20} />
            </button>
            <button onClick={() => scrollReel(1)} aria-label="Scroll cards right"
              className="flex absolute right-0 top-1/2 -translate-y-1/2 items-center justify-center
                         w-9 h-9 rounded-full bg-bg-card border-2 border-border text-text-secondary
                         hover:text-text-primary hover:border-accent active:scale-95 transition-all shadow-card z-20">
              <ChevronRight size={20} />
            </button>
          </>
        )}
        {deckable.length === 0 && <p className="text-text-muted text-xs py-4 text-center">No cards match "{search}"</p>}
      </div>
      {/* Position indicator -- both a signal of scroll progress (moves live
          as the reel scrolls, however it's scrolled -- wheel, touch, drag,
          or the buttons above) and clickable to jump straight to a spot,
          same "clickable and scrollable" ask as the reel itself. */}
      {reelScroll.scrollable && (
        <div ref={trackRef} onClick={e => jumpToTrackPosition(e.clientX)}
          role="slider" aria-label="Card reel position" aria-valuenow={Math.round(reelScroll.progress * 100)}
          aria-valuemin={0} aria-valuemax={100}
          className="relative mt-2 mx-8 h-2.5 bg-bg-card border border-border rounded-full cursor-pointer overflow-hidden">
          <div className="absolute top-0 bottom-0 bg-accent rounded-full transition-[left] duration-150 ease-out"
            style={{
              width: `${reelScroll.thumbPct}%`,
              left: `${reelScroll.progress * (100 - reelScroll.thumbPct)}%`,
            }} />
        </div>
      )}
    </div>
  )
}

export function TowerSlot({ cards, selected, onSelect }: { cards: any[]; selected: string | null; onSelect: (name: string | null) => void }) {
  const [dragOver, setDragOver] = useState(false)
  const towerTroops = cards.filter(c => c.type === 'Tower Troop')
  const card = towerTroops.find(t => t.name === selected)
  if (towerTroops.length === 0) return null

  return (
    <div className="mb-4">
      <div className="text-xs font-semibold text-text-secondary mb-1.5">King Tower Troop</div>
      <div className="flex items-center gap-3">
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragOver(false)
            const name = e.dataTransfer.getData('text/plain')
            const dropped = cards.find(c => c.name === name)
            if (dropped?.type === 'Tower Troop') onSelect(name)
          }}
          className={`w-16 h-20 rounded-lg border-2 border-dashed flex flex-col items-center justify-center
                     transition-all duration-150 ease-out shrink-0 ${dragOver ? 'scale-110' : 'scale-100'}`}
          style={dragOver
            ? { borderColor: '#D4AF37', backgroundColor: 'rgba(212,175,55,0.15)' }
            : { borderColor: '#4A2E2E' }}
        >
          {card ? (
            <CardImage name={card.name} imageUrl={card.image_url} rarity={card.rarity} size="sm" showName={false}
              draggable onDragEnd={(e) => { if (e.dataTransfer.dropEffect === 'none') onSelect(null) }} />
          ) : (
            <>
              <span className={`text-lg transition-colors duration-150 ${dragOver ? 'text-gold' : 'text-text-muted'}`}>🏰</span>
              <span className="text-[7px] font-bold leading-tight text-center px-0.5 text-text-muted">TOWER</span>
            </>
          )}
        </div>
        <div className="flex gap-2 flex-wrap">
          {towerTroops.map(t => (
            <CardImage key={t.name} name={t.name} imageUrl={t.image_url} rarity={t.rarity} size="xs"
              selected={selected === t.name} onClick={() => onSelect(t.name)} draggable />
          ))}
        </div>
      </div>
    </div>
  )
}
