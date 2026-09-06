import { useMemo, useState } from 'react'
import { formatStrategy } from '../utils/formatStrategy'

/**
 * Drop-in replacement for the plain "Any strategy" <select> that used to
 * list every real strategy (there can be dozens) in one long native
 * dropdown -- real feedback (2026-08-23): "choose strategy option rather
 * than scrolling through all of those strategies, maybe a easier way using
 * bait, building hog barrel stuff like that helping to pinpoint if user
 * wants to find a very specific deck." Same combobox shape as
 * PlayerTagAutocomplete.tsx: type a keyword ("hog", "bait", "cycle", "log"),
 * see it narrow instantly, click to pick -- matched against the same
 * human-readable label formatStrategy() already produces, so typed words
 * line up with what's actually displayed.
 */
export default function StrategyPicker({ strategies, value, onChange, placeholder }: {
  strategies: { strategy: string; frequency?: number | null }[]
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)

  const filtered = useMemo(() => {
    const withLabel = strategies.map(s => ({ ...s, label: formatStrategy(s.strategy) }))
    const q = query.trim().toLowerCase()
    const matches = q
      ? withLabel.filter(s => s.label.toLowerCase().includes(q) || s.strategy.toLowerCase().includes(q))
      : withLabel
    return matches.slice(0, 40)
  }, [strategies, query])

  const selectedLabel = value ? formatStrategy(value) : ''

  return (
    <div className="relative">
      <input
        value={open ? query : selectedLabel}
        onChange={e => { setQuery(e.target.value); setOpen(true) }}
        onFocus={() => { setQuery(''); setOpen(true) }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder ?? 'Search strategy (hog, bait, cycle...)'}
        className="w-full bg-bg-card border border-border rounded-lg pl-2 pr-6 py-1.5 text-xs text-text-primary
                   placeholder:text-text-muted focus:outline-none focus:border-accent" />
      {value && !open && (
        <button onMouseDown={() => onChange('')} aria-label="Clear strategy filter"
          className="absolute right-1.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-danger text-xs leading-none">✕</button>
      )}
      {open && (
        <div className="absolute top-full mt-1 left-0 right-0 min-w-[16rem] bg-bg-surface border border-border rounded-lg
                        shadow-card overflow-hidden z-50 max-h-60 overflow-y-auto">
          <button onMouseDown={() => { onChange(''); setQuery(''); setOpen(false) }}
            className="w-full text-left px-3 py-1.5 text-xs text-text-muted hover:bg-bg-card border-b border-border">
            Any strategy
          </button>
          {filtered.length === 0 && (
            <div className="px-3 py-2 text-xs text-text-muted">No match -- try "hog", "bait", "cycle", "siege"...</div>
          )}
          {filtered.map(s => (
            <button key={s.strategy} onMouseDown={() => { onChange(s.strategy); setQuery(''); setOpen(false) }}
              className="w-full flex items-center justify-between gap-2 px-3 py-1.5 text-xs text-text-primary hover:bg-bg-card text-left">
              <span className="truncate">{s.label}</span>
              {s.frequency != null && <span className="text-text-muted shrink-0">{s.frequency.toLocaleString()}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
