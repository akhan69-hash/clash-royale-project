import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LayoutGrid } from 'lucide-react'
import { NAV_SECTIONS } from '../utils/navSections'

export default function MegaMenu() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const go = (href: string) => {
    setOpen(false)
    navigate(href)
  }

  return (
    <div className="relative shrink-0" ref={ref}>
      <button onClick={() => setOpen(o => !o)} title="All features"
        className={`flex items-center gap-1.5 px-2 sm:px-3 py-1.5 rounded-lg text-sm font-medium transition-colors
          ${open ? 'bg-accent/20 text-accent' : 'text-text-secondary hover:text-text-primary hover:bg-bg-card'}`}>
        <LayoutGrid size={18} />
        <span className="hidden sm:inline">More</span>
      </button>

      {open && (
        // max-h used `70vh`, which mobile browsers compute against the
        // LARGEST possible viewport (address bar hidden) -- with the address
        // bar actually visible (the normal state right after a page loads),
        // the panel could render taller than the real visible screen, and
        // since it's `position: absolute` inside the `fixed` navbar (not
        // normal page flow), there was no way to scroll down to the cut-off
        // part. `dvh` (dynamic viewport height) tracks the REAL visible
        // area as the browser chrome shows/hides, and the calc() subtracts
        // room for the navbar itself so the panel can never start off
        // already over budget.
        <div className="absolute top-full right-0 sm:left-0 mt-2 w-48
                        bg-bg-surface border border-border rounded-xl shadow-card p-2 z-50
                        max-h-[calc(100dvh-5rem)] overflow-y-auto">
          {NAV_SECTIONS.map(item => (
            <button key={item.href} onClick={() => go(item.href)}
              className="w-full flex items-center gap-2 text-left text-sm text-text-secondary hover:text-accent
                         hover:bg-bg-card rounded-lg px-2 py-2 transition-colors">
              <span>{item.icon}</span> {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
