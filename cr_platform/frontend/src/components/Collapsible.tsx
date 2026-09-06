import { useState, ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'

/**
 * Shared expand/collapse wrapper for secondary/lower-priority content --
 * closed by default so the primary content on a page isn't buried under a
 * wall of detail. Same interaction shape CoachingPage's ConceptsGlossary
 * already used, now reusable everywhere instead of being reimplemented.
 *
 * `compact` drops the card-styled wrapper (border/padding/margin) down to a
 * single small text-only trigger line with no surrounding box -- for nesting
 * inside something that's already its own card (e.g. one deck-card's
 * "▾ More details" toggle), where the default's `bg-bg-surface border ...`
 * treatment would double-frame it.
 *
 * EXTENDED 2026-09-02 for the "visual hierarchy" pass -- real feedback:
 * "right now everything looks like its one thing... same colorway no
 * borders or certain emphasises... everything is player choosable to see."
 * Two additions, both reusing this ONE component instead of every page
 * hand-rolling its own section chrome (which is how 19 section containers
 * on Coach alone ended up using the exact same generic border color):
 *   - `accent`: which of the app's own existing brand tokens (see
 *     tailwind.config.js) this section's border/heading uses -- a real
 *     semantic category, not a decorative flourish. Pick by what KIND of
 *     information the section shows, consistently across every page:
 *       'gold'    - community/meta data (what's trending, what's winning)
 *       'royale'  - this specific player's own data (their decks, their
 *                   stats, their history) -- the app's existing blue token,
 *                   previously almost unused outside 2 spots
 *       'success' - forward-looking progress/goals (upgrade priorities,
 *                   trophy push)
 *       'crimson' - tips/guidance/advisory content
 *       'border'  - the old neutral default, for anything that's genuinely
 *                   none of the above
 *   - `persistKey`: when given, the open/closed choice is remembered in
 *     localStorage under this key and wins over `defaultOpen` on repeat
 *     visits -- a section the player closes ONCE stays closed for them,
 *     instead of defaulting back open every time (the actual "player
 *     choosable to see" part, not just "collapsible in the moment").
 */
const ACCENT_BORDER: Record<string, string> = {
  border: 'border-border',
  gold: 'border-accent/40',
  royale: 'border-royale/40',
  success: 'border-success/40',
  crimson: 'border-crimson/40',
}
const ACCENT_TEXT: Record<string, string> = {
  border: 'text-text-primary',
  gold: 'text-accent',
  royale: 'text-royale',
  success: 'text-success',
  crimson: 'text-crimson',
}

function loadPersisted(key: string, fallback: boolean): boolean {
  try {
    const stored = localStorage.getItem(`cr_section_open_${key}`)
    return stored == null ? fallback : stored === '1'
  } catch {
    return fallback
  }
}

export default function Collapsible({ title, defaultOpen = false, compact = false, accent = 'border', persistKey, children }: {
  title: ReactNode; defaultOpen?: boolean; compact?: boolean
  accent?: 'border' | 'gold' | 'royale' | 'success' | 'crimson'
  persistKey?: string; children: ReactNode
}) {
  const [open, setOpen] = useState(() => persistKey ? loadPersisted(persistKey, defaultOpen) : defaultOpen)
  const toggle = () => setOpen(o => {
    const next = !o
    if (persistKey) { try { localStorage.setItem(`cr_section_open_${persistKey}`, next ? '1' : '0') } catch { /* ignore */ } }
    return next
  })
  if (compact) {
    return (
      <div>
        <button onClick={toggle} className="flex items-center gap-1 text-[10px] text-text-muted hover:text-text-secondary transition-colors">
          <ChevronDown size={11} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
          {title}
        </button>
        {open && <div className="mt-1.5">{children}</div>}
      </div>
    )
  }
  return (
    <div className={`bg-bg-surface border ${ACCENT_BORDER[accent]} rounded-xl p-4 mb-6`}>
      <button onClick={toggle} className="flex items-center justify-between w-full text-left">
        <span className={`text-sm font-semibold ${ACCENT_TEXT[accent]}`}>{title}</span>
        <ChevronDown size={16} className={`text-text-muted transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="mt-3">{children}</div>}
    </div>
  )
}
