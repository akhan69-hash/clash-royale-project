import { useQuery } from '@tanstack/react-query'
import { whatsNextApi } from '../utils/api'

/** Small "what season am I on" indicator -- real feedback (2026-08-22):
 * "what season am i on the player lookup and home page." Real feedback also
 * asked to stop showing the full stale season-announcement HEADLINE
 * prominently (see HomePage.tsx's old SeasonHighlights), so this is
 * deliberately just the season number + name, nothing else -- a fact, not
 * a news item. */
export default function SeasonBadge({ className = '' }: { className?: string }) {
  const { data } = useQuery({ queryKey: ['whats-next'], queryFn: () => whatsNextApi.get() })
  const season = data?.current_season
  if (!season) return null

  return (
    <span className={`inline-flex items-center gap-1 text-xs text-gold ${className}`}>
      🏆 Season {season.number}{season.name ? `: ${season.name}` : ''}
    </span>
  )
}
