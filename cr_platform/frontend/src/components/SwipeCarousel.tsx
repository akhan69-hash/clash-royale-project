import { useRef, useState, ReactNode } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

/**
 * Generic one-item-at-a-time swipeable carousel, extracted from
 * TipsCarousel.tsx's proven scroll-snap + dots + prev/next shell so
 * anything else that needs "swipe through a list one at a time" (real
 * feedback, 2026-08-23: "whats winning in your arena make it swipeable one
 * deck at a time") doesn't reimplement it. TipsCarousel itself is left
 * as-is (already tested/working, and its cards deliberately peek the next
 * one at 78% width rather than going full-width) -- this is for callers
 * that want a full-width, strictly-one-visible item instead.
 */
export default function SwipeCarousel<T>({ items, keyFor, children }: {
  items: T[]
  keyFor: (item: T, i: number) => string | number
  children: (item: T, i: number) => ReactNode
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [active, setActive] = useState(0)

  const onScroll = () => {
    const el = scrollRef.current
    if (!el || items.length === 0) return
    const cardSpan = el.scrollWidth / items.length
    setActive(Math.min(items.length - 1, Math.max(0, Math.round(el.scrollLeft / cardSpan))))
  }

  const scrollTo = (i: number) => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ left: (el.scrollWidth / items.length) * i, behavior: 'smooth' })
    setActive(i)
  }

  if (items.length === 0) return null

  return (
    <div>
      <div ref={scrollRef} onScroll={onScroll}
        className="flex overflow-x-auto snap-x snap-mandatory scrollbar-hide [overflow-anchor:none]">
        {items.map((item, i) => (
          <div key={keyFor(item, i)} className="snap-center shrink-0 w-full">
            {children(item, i)}
          </div>
        ))}
      </div>
      {items.length > 1 && (
        <div className="flex items-center justify-center gap-3 mt-2">
          <button onClick={() => scrollTo(Math.max(0, active - 1))} disabled={active === 0} aria-label="Previous"
            className="flex items-center justify-center w-6 h-6 rounded-full text-text-secondary bg-bg-card
                       hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed transition-colors shrink-0">
            <ChevronLeft size={13} />
          </button>
          <div className="flex gap-1.5 flex-wrap justify-center max-w-[60%]">
            {items.map((item, i) => (
              <button key={keyFor(item, i)} onClick={() => scrollTo(i)} aria-label={`Item ${i + 1}`}
                className={`h-1.5 rounded-full transition-all ${i === active ? 'w-4 bg-accent' : 'w-1.5 bg-border'}`} />
            ))}
          </div>
          <button onClick={() => scrollTo(Math.min(items.length - 1, active + 1))} disabled={active === items.length - 1} aria-label="Next"
            className="flex items-center justify-center w-6 h-6 rounded-full text-text-secondary bg-bg-card
                       hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed transition-colors shrink-0">
            <ChevronRight size={13} />
          </button>
        </div>
      )}
      <div className="text-center text-[10px] text-text-muted mt-1">{active + 1} / {items.length}</div>
    </div>
  )
}
