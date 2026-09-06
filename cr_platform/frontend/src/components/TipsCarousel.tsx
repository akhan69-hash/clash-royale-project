import { useRef, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import CardImage from './CardImage'

// Real feedback (2026-08-20): "make it a fun feature that player can swipe
// and look" -- the old "Quick Real-Data Tips" section was a stack of dense
// paragraphs naming cards inline ("Vines -- 61% real win rate, the softest
// link in your deck"). Same real data, but each tip is now its own swipeable
// card that SHOWS the card being talked about instead of just naming it.
//
// Built on native CSS scroll-snap rather than a carousel library -- real
// momentum/touch swipe for free on mobile, no extra dependency, matches this
// app's existing preference for native browser mechanisms (see the deck
// builder's own native HTML5 drag-and-drop) over a bespoke JS reimplementation.
export interface Tip {
  id: string
  icon: string
  label: string
  accentClass: string // tailwind text-color class for the label
  /** 0, 1, or 2 card names to feature -- most tips are about a specific card
   * (or a pair, for synergy tips); a few (elixir benchmark, level comparison)
   * are deck-level stats with no single card to show, so this can be empty. */
  cards?: string[]
  caption: string
  imageFor: (name: string) => string | null | undefined
  rarityFor: (name: string) => string | null | undefined
  onCardClick?: (name: string) => void
}

export default function TipsCarousel({ tips }: { tips: Tip[] }) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [active, setActive] = useState(0)

  const onScroll = () => {
    const el = scrollRef.current
    if (!el || tips.length === 0) return
    const cardSpan = el.scrollWidth / tips.length
    setActive(Math.min(tips.length - 1, Math.max(0, Math.round(el.scrollLeft / cardSpan))))
  }

  const scrollTo = (i: number) => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ left: (el.scrollWidth / tips.length) * i, behavior: 'smooth' })
    setActive(i)
  }

  if (tips.length === 0) return null

  return (
    <div>
      {/* w-[78%] on mobile deliberately leaves the next card peeking in at the
          edge -- a visible hint that there's more to swipe to, and matches
          "see a few on each swipe" (partial next/prev card + full current one). */}
      {/* overflow-anchor:none is defensive/cheap insurance against the
          browser's CSS Scroll Anchoring nudging scrollLeft during any future
          content reflow in this row. It is NOT what fixes the "carousel
          lands on a random tip" bug that was found here -- that turned out
          to be CSS Scroll Snap re-snapping the container when `tips` grew
          partially and then had earlier entries prepended in front of
          already-rendered ones (confirmed via a real Playwright repeat-load
          test: this property alone did not stop the jump). The actual fix
          is upstream in CoachingPage.tsx: `quickTips` is now only built/
          rendered once every query it depends on has settled, so this row
          only ever mounts once, fully-formed, in final order -- nothing to
          reorder, so scroll-snap has nothing to resnap away from. */}
      <div ref={scrollRef} onScroll={onScroll}
        className="flex gap-3 overflow-x-auto snap-x snap-mandatory pb-1 -mx-1 px-1 scrollbar-hide [overflow-anchor:none]">
        {tips.map(t => (
          <div key={t.id} className="snap-center shrink-0 w-[78%] sm:w-52 bg-bg-card border border-border rounded-xl p-3 text-center">
            <div className={`text-[10px] font-bold uppercase tracking-wide mb-2 ${t.accentClass}`}>{t.icon} {t.label}</div>
            {t.cards && t.cards.length > 0 && (
              <div className="flex items-center justify-center gap-2 mb-2">
                {t.cards.map((name, i) => (
                  <span key={name} className="flex items-center gap-2">
                    <CardImage name={name} imageUrl={t.imageFor(name)} rarity={t.rarityFor(name) ?? undefined}
                      size="sm" showName={false} onClick={t.onCardClick ? () => t.onCardClick!(name) : undefined} magnify={false} />
                    {i === 0 && t.cards!.length > 1 && <span className="text-text-muted text-xs">+</span>}
                  </span>
                ))}
              </div>
            )}
            <div className="text-xs text-text-secondary">{t.caption}</div>
          </div>
        ))}
      </div>
      {/* Dots alone assume a touchscreen -- real feedback (2026-08-21): "maybe
          use one single button so it also helps desktop version to navigate
          through it." A trackpad/mouse user has no swipe gesture at all here,
          so explicit prev/next buttons flanking the dots give desktop a real
          way to move through the tips one at a time, not just jump to one. */}
      {tips.length > 1 && (
        <div className="flex items-center justify-center gap-3 mt-2">
          <button onClick={() => scrollTo(Math.max(0, active - 1))} disabled={active === 0}
            aria-label="Previous tip"
            className="flex items-center justify-center w-6 h-6 rounded-full text-text-secondary bg-bg-card
                       hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed transition-colors shrink-0">
            <ChevronLeft size={13} />
          </button>
          <div className="flex gap-1.5">
            {tips.map((t, i) => (
              <button key={t.id} onClick={() => scrollTo(i)} aria-label={`Tip ${i + 1}`}
                className={`h-1.5 rounded-full transition-all ${i === active ? 'w-4 bg-accent' : 'w-1.5 bg-border'}`} />
            ))}
          </div>
          <button onClick={() => scrollTo(Math.min(tips.length - 1, active + 1))} disabled={active === tips.length - 1}
            aria-label="Next tip"
            className="flex items-center justify-center w-6 h-6 rounded-full text-text-secondary bg-bg-card
                       hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed transition-colors shrink-0">
            <ChevronRight size={13} />
          </button>
        </div>
      )}
    </div>
  )
}
