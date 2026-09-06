import { useQuery } from '@tanstack/react-query'

interface DataHealthResponse {
  summary: string
  data: {
    total_collected_battles: number
    unique_players_seen: number
    unique_decks_seen: number
    csv_freshness: Record<string, any>
    timestamp: string
  }
}

async function fetchDataHealth(): Promise<DataHealthResponse> {
  const res = await fetch('/api/health/data-health')
  if (!res.ok) throw new Error('Failed to fetch data health')
  return res.json()
}

// Real feedback (2026-08-23): this used to show "✓ Live Data" right next to
// "Updated 9.1 days ago" -- claiming "live" while admitting a real 9-day gap
// reads as a contradiction, not a win, and the staleness age was printed
// TWICE (once inside the backend's own summary sentence, once again here).
// Root cause of the actual staleness was a real gap (nothing was ever
// scheduled to refresh this data -- fixed with a nightly retrain cron, see
// deploy/retrain.sh) -- this component's fix is just honest framing: the
// "Live" badge only shows when the data is genuinely recent, a plain
// "Updated X ago" otherwise, and the age is printed once.
const FRESH_THRESHOLD_HOURS = 30 // a bit over the nightly cron's own cadence

function formatAge(ageSeconds: number): string {
  if (ageSeconds < 3600) return 'moments ago'
  if (ageSeconds < 86400) return `${Math.floor(ageSeconds / 3600)}h ago`
  return `${Math.floor(ageSeconds / 86400)}d ago`
}

export default function DataHealthBanner() {
  const { data, isLoading } = useQuery({
    queryKey: ['data-health'],
    queryFn: fetchDataHealth,
    staleTime: 60 * 1000,
  })

  if (isLoading) {
    return (
      <div className="bg-bg-surface border border-cyan-400/20 rounded-lg p-3 mb-4 animate-pulse">
        <p className="text-text-muted text-xs">Loading data health...</p>
      </div>
    )
  }

  if (!data) return null

  const stats = data.data
  const ageSeconds = stats.csv_freshness?.card_stats?.age_seconds
  const isFresh = ageSeconds != null && ageSeconds < FRESH_THRESHOLD_HOURS * 3600

  return (
    <div className="bg-bg-surface border border-cyan-400/30 rounded-lg p-4 mb-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <p className="text-text-primary text-sm font-medium mb-2">
            📊 {stats.total_collected_battles > 1_000_000
              ? `${(stats.total_collected_battles / 1_000_000).toFixed(1)}M`
              : stats.total_collected_battles?.toLocaleString()} real battles analyzed
          </p>
          <div className="flex gap-3 text-xs text-text-muted flex-wrap">
            <span>🎮 {stats.unique_players_seen?.toLocaleString() || '—'} players</span>
            <span>🃏 {stats.unique_decks_seen?.toLocaleString() || '—'} decks</span>
          </div>
        </div>
        <div className="text-right text-xs text-text-muted shrink-0">
          {isFresh
            ? <div className="text-green-400 font-medium">✓ Fresh data</div>
            : ageSeconds != null && <div className="text-yellow-400 font-medium">Updated {formatAge(ageSeconds)}</div>}
          {isFresh && ageSeconds != null && <div>Updated {formatAge(ageSeconds)}</div>}
        </div>
      </div>
    </div>
  )
}
