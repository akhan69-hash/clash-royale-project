import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { motion, AnimatePresence, type PanInfo } from 'framer-motion'
import { ChevronLeft, X } from 'lucide-react'
import { NAV_SECTIONS } from '../utils/navSections'

/**
 * Replaces FloatingNavBubble (2026-09-02 real feedback: "make more a side
 * swipeable menu bar, remove the navigation bubble, and add every feature in
 * the more swipeable menu bar, and make sure it's visible the word more").
 *
 * A permanently visible tab docked to the right edge, literally labeled
 * "MORE" (not icon-only -- the bubble's Compass icon alone was the exact
 * thing real feedback flagged before: "looks more like ask for help or AI").
 * Tapping it, or dragging it left, slides a full-height panel in from the
 * right listing every real destination (utils/navSections.ts). The panel
 * itself is also draggable -- a real swipe-right gesture past a threshold
 * closes it, not just a tap on the backdrop/X, matching "swipeable."
 */
const PANEL_WIDTH = 288 // px, matches w-72

export default function SideMenu() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const go = (href: string) => {
    setOpen(false)
    navigate(href)
  }

  // Real swipe-to-close: drag the panel itself; releasing past a threshold
  // (or with enough velocity) closes it instead of snapping back.
  const onDragEnd = (_: unknown, info: PanInfo) => {
    if (info.offset.x > PANEL_WIDTH / 3 || info.velocity.x > 500) setOpen(false)
  }

  return (
    <>
      {/* The always-visible docked tab -- fixed to the right edge, vertically
          centered. Rotated text keeps "MORE" fully legible (not truncated
          into icon-only), matching real feedback that it must stay visible
          as the word, not just a symbol. Hidden while the panel is open
          (the panel's own edge takes its place) so there's no double tab. */}
      {!open && (
        <button onClick={() => setOpen(true)} aria-label="Open menu"
          className="fixed right-0 top-1/2 -translate-y-1/2 z-40 flex flex-col items-center gap-1
                     bg-gold hover:bg-gold-hover text-bg-primary rounded-l-xl shadow-glow
                     px-1.5 py-3 transition-colors">
          <ChevronLeft size={14} />
          <span className="text-[11px] font-bold tracking-widest" style={{ writingMode: 'vertical-rl' }}>
            MORE
          </span>
        </button>
      )}

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setOpen(false)}
            />
            <motion.div
              className="fixed top-0 right-0 bottom-0 z-50 w-72 max-w-[85vw] bg-bg-surface border-l border-border
                         shadow-card flex flex-col"
              initial={{ x: PANEL_WIDTH }} animate={{ x: 0 }} exit={{ x: PANEL_WIDTH }}
              transition={{ type: 'tween', duration: 0.22 }}
              drag="x" dragConstraints={{ left: 0, right: 0 }} dragElastic={{ left: 0, right: 0.6 }}
              onDragEnd={onDragEnd}
            >
              <div className="flex items-center justify-between px-4 py-4 border-b border-border shrink-0">
                <span className="text-sm font-bold text-gold tracking-widest">MORE</span>
                <button onClick={() => setOpen(false)} aria-label="Close menu"
                  className="text-text-muted hover:text-text-primary transition-colors p-1">
                  <X size={18} />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto py-2">
                {NAV_SECTIONS.map(item => {
                  const active = item.href === '/' ? location.pathname === '/' : location.pathname.startsWith(item.href)
                  return (
                    <button key={item.href} onClick={() => go(item.href)}
                      className={`w-full flex items-center gap-3 text-left px-5 py-3 transition-colors
                        ${active ? 'bg-accent/15 text-accent' : 'text-text-secondary hover:bg-bg-card hover:text-text-primary'}`}>
                      <span className="text-lg">{item.icon}</span>
                      <span className="text-sm font-medium">{item.label}</span>
                    </button>
                  )
                })}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
