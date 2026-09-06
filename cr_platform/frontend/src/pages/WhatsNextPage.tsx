import { useQuery } from '@tanstack/react-query'
import { whatsNextApi } from '../utils/api'
import Backdrop from '../components/Backdrop'

const CATEGORY_STYLE: Record<string, { label: string; color: string }> = {
  season: { label: 'Season', color: '#D4AF37' },
  cards: { label: 'Cards', color: '#C084FC' },
  balance: { label: 'Balance', color: '#C23B3B' },
}

export default function WhatsNextPage() {
  const { data, isLoading } = useQuery({ queryKey: ['whats-next'], queryFn: () => whatsNextApi.get() })

  return (
    <div className="relative z-10 max-w-3xl mx-auto px-4 py-6">
      <Backdrop density={10} />
      <h1 className="text-2xl font-bold text-accent mb-1">📰 News</h1>
      <p className="text-text-secondary text-sm mb-1">
        Real, cited updates on what's new and coming in Clash Royale.
      </p>
      {data?.research_date && (
        <p className="text-text-muted text-xs mb-2">
          Researched {data.research_date} -- this is hand-curated, not auto-refreshed, so check the date.
        </p>
      )}
      {data?.note && <p className="text-text-muted text-xs mb-6 italic">{data.note}</p>}

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-20 bg-bg-surface rounded-xl animate-pulse" />)}
        </div>
      ) : (
        <div className="space-y-3">
          {(data?.entries ?? []).map((e: any, i: number) => {
            const cat = CATEGORY_STYLE[e.category] ?? { label: e.category, color: '#8A7568' }
            return (
              <div key={i} className="bg-bg-surface border border-border rounded-xl p-4">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-sm font-semibold text-text-primary">{e.title}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full shrink-0 ml-2"
                    style={{ backgroundColor: cat.color + '30', color: cat.color }}>
                    {cat.label}
                  </span>
                </div>
                <p className="text-xs text-text-secondary mb-2">{e.summary}</p>
                {e.source_url && (
                  <a href={e.source_url} target="_blank" rel="noopener noreferrer"
                    className="text-[11px] text-cyan-300 hover:underline">
                    Source ↗
                  </a>
                )}
              </div>
            )
          })}
          {(!data?.entries || data.entries.length === 0) && (
            <div className="bg-bg-surface border border-border rounded-xl p-6 text-center text-text-secondary text-sm">
              No updates researched yet.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
