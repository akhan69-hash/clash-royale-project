/**
 * Real feedback (2026-08-26): "If a part of the page is loading or
 * reloading, show its loading or give it a loading emoji rather than sudden
 * renders and re renders, make the app really smooth." Several sections
 * (Coach's arena decks, Your Decks, Meta Pulse, etc.) fetched their own
 * `isLoading` flag but never actually rendered it -- while loading, the
 * section just showed nothing at all, then popped in abruptly once data
 * arrived. This is a plain, reusable pulsing placeholder shaped like a
 * section (title bar + a few card-shaped blocks) to show in that gap
 * instead of a sudden appear/disappear.
 */
export default function SectionSkeleton({ rows = 2, label }: { rows?: number; label?: string }) {
  return (
    <div className="animate-pulse">
      {label && <div className="h-3 w-40 bg-bg-card rounded mb-3" />}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="h-28 bg-bg-card rounded-lg" />
        ))}
      </div>
    </div>
  )
}
