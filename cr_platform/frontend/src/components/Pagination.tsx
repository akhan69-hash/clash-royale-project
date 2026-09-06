import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { RefObject } from 'react'

/** Shared numbered pagination -- first pagination UI in the app, so every
 * list that needs "turn through pages to find the deck you want" (Top Decks,
 * Counter tab) uses this same component instead of a bespoke one each. Styled
 * to match the existing sort/filter button-row convention (bg-accent when
 * active, bg-bg-card otherwise). `total`/`pageSize` come straight from the
 * paginated API responses (/meta/decks, /decks/counter).
 *
 * `scrollTargetRef` is optional: when given (a ref on the top of the list
 * this paginates), changing pages smooth-scrolls that element back into
 * view -- since Pagination itself renders at the BOTTOM of a list, without
 * this a user who clicks "page 2" from way down at the bottom stays
 * scrolled to that same spot, now looking at the middle of unrelated new
 * content instead of the start of it. */
export default function Pagination({ page, pageSize, total, onPageChange, scrollTargetRef, className = 'mt-4' }: {
  page: number; pageSize: number; total: number; onPageChange: (page: number) => void
  scrollTargetRef?: RefObject<HTMLElement>
  /** Margin override -- callers render this component twice per list now
   * (see below), once above and once below, so the default bottom-only
   * `mt-4` spacing needs to flip to `mb-4` for the top copy. */
  className?: string
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  if (pageCount <= 1) return null

  const goToPage = (p: number) => {
    onPageChange(p)
    scrollTargetRef?.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  // Windowed page numbers around the current page, plus first/last, so this
  // stays usable even when there are many pages (dashes for skipped ranges).
  const windowSize = 2
  const pages = new Set<number>([1, pageCount])
  for (let p = page - windowSize; p <= page + windowSize; p++) {
    if (p >= 1 && p <= pageCount) pages.add(p)
  }
  const sorted = [...pages].sort((a, b) => a - b)

  return (
    <div className={`flex items-center justify-center gap-1 flex-wrap ${className}`}>
      <button onClick={() => goToPage(Math.max(1, page - 1))} disabled={page === 1}
        className="flex items-center justify-center w-8 h-8 rounded-lg text-text-secondary bg-bg-card
          hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
        <ChevronLeft size={14} />
      </button>
      {sorted.map((p, i) => (
        <span key={p} className="flex items-center gap-1">
          {i > 0 && p - sorted[i - 1] > 1 && <span className="text-text-muted text-xs px-1">…</span>}
          <button onClick={() => goToPage(p)}
            className={`min-w-[2rem] h-8 px-2 rounded-lg text-xs font-medium transition-colors
              ${p === page ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
            {p}
          </button>
        </span>
      ))}
      <button onClick={() => goToPage(Math.min(pageCount, page + 1))} disabled={page === pageCount}
        className="flex items-center justify-center w-8 h-8 rounded-lg text-text-secondary bg-bg-card
          hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
        <ChevronRight size={14} />
      </button>
    </div>
  )
}
