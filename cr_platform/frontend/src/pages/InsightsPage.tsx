import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { insightsApi } from '../utils/api'
import Backdrop from '../components/Backdrop'
import SkeletonLoader from '../components/SkeletonLoader'

// Real feedback (2026-09-08): "collect user data and where they are going
// and what features they are using." Real data was already being collected
// (services/activity_log.py logs every API call, grouped by an anonymous
// per-browser session id, since 2026-08-19) -- nothing here was previously
// surfaced anywhere, "no dashboard... on purpose... for whenever [it's
// needed]" per that file's own docstring. This is that dashboard: an
// internal/self view, not a public feature -- deliberately left out of the
// main nav (see utils/navSections.ts) and reachable only by direct URL for
// now, same "not gated behind auth yet, nothing here is a specific
// person's private data" reasoning the backend endpoint itself documents.
const DAY_OPTIONS = [7, 30, 90] as const

export default function InsightsPage() {
  const [days, setDays] = useState<(typeof DAY_OPTIONS)[number]>(30)
  const { data, isLoading } = useQuery({
    queryKey: ['insights-summary', days],
    queryFn: () => insightsApi.summary(days),
  })

  return (
    <div className="relative z-10 max-w-5xl mx-auto px-4 py-6">
      <Backdrop density={8} />
      <div className="flex items-center justify-between mb-6 flex-wrap gap-2">
        <h1 className="text-2xl font-bold text-accent">📊 Usage Insights</h1>
        <div className="flex gap-1">
          {DAY_OPTIONS.map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
                ${days === d ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
              {d}d
            </button>
          ))}
        </div>
      </div>

      {isLoading && <SkeletonLoader label="Loading real usage data..." />}

      {data && (
        <div className="space-y-5">
          <p className="text-text-muted text-xs -mt-2">
            Derived from real API requests over the last {data.days} days -- anonymous per-browser session ids only,
            no personal data. "Where they're going" is approximated from which endpoints a session's requests hit
            (a few pages, notably Home, don't have a distinctive API call of their own, so they're undercounted here).
          </p>

          <div className="grid grid-cols-2 gap-3">
            <div className="bg-bg-surface border border-border rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-accent">{data.unique_sessions.toLocaleString()}</div>
              <div className="text-text-muted text-xs mt-1">Unique visitors (sessions)</div>
            </div>
            <div className="bg-bg-surface border border-border rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-cyan-300">{data.total_requests.toLocaleString()}</div>
              <div className="text-text-muted text-xs mt-1">Real requests</div>
            </div>
          </div>

          <div className="bg-bg-surface border border-border rounded-xl p-4">
            <h3 className="font-semibold text-white mb-3">Daily Traffic</h3>
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.daily}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#4A2E2E" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#8A7568' }}
                    tickFormatter={(d: string) => d.slice(5)} />
                  <YAxis tick={{ fontSize: 10, fill: '#8A7568' }} allowDecimals={false} />
                  <Tooltip contentStyle={{ background: '#1E1414', border: '1px solid #4A2E2E', fontSize: 12 }} />
                  <Bar dataKey="unique_sessions" name="Unique visitors" fill="#4A6FE0" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-bg-surface border border-border rounded-xl p-4">
            <h3 className="font-semibold text-white mb-3">Feature Usage</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-2 text-text-muted font-medium text-xs">Feature</th>
                    <th className="text-right py-2 text-text-muted font-medium text-xs">Requests</th>
                    <th className="text-right py-2 text-text-muted font-medium text-xs">Unique Visitors</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_features.map((f: any) => (
                    <tr key={f.feature} className="border-b border-border/50">
                      <td className="py-1.5 text-text-primary">{f.feature}</td>
                      <td className="py-1.5 text-right text-text-secondary">{f.requests.toLocaleString()}</td>
                      <td className="py-1.5 text-right text-cyan-300">{f.unique_sessions.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
