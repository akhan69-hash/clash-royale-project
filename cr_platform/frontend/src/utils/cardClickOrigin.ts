/**
 * Tiny module-level "what did the user just click" relay so CardDetailModal
 * can animate open/close from the actual clicked card thumbnail's on-screen
 * position ("takes the 3d card back into where i clicked it from" -- real
 * feedback 2026-09-07) without every one of CardDetailContext's ~20 call
 * sites (CoachingPage/PlayerPage/FavoritesPage/CounterDecksList/
 * StrategyCounterBrowser/DeckBuilderKit/SynergyPage/AnalyticsPage) needing to
 * thread a click event through openCard(name).
 *
 * CardImage's own click handler (the shared component nearly every call site
 * renders through) captures its own bounding rect here immediately before
 * calling the passed-in onClick, and CardDetailContext consumes it the
 * instant openCard() runs -- both happen synchronously inside the same React
 * click event, so this never leaks a stale value into an unrelated later
 * click. The setTimeout(0) clears it right after in case a click never went
 * through CardImage at all (a handful of AnalyticsPage rows call openCard
 * straight from a raw <div>/<tr>) -- those just fall back to the modal's
 * default centered fade-in instead of a wrong origin point.
 */
interface ClickOrigin {
  centerX: number
  centerY: number
}

let pending: ClickOrigin | null = null

export function setLastCardClickOrigin(rect: DOMRect) {
  pending = { centerX: rect.left + rect.width / 2, centerY: rect.top + rect.height / 2 }
  setTimeout(() => { pending = null }, 0)
}

export function consumeLastCardClickOrigin(): ClickOrigin | null {
  const origin = pending
  pending = null
  return origin
}
