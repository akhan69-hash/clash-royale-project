import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { rankingsApi } from '../utils/api'
import Backdrop from '../components/Backdrop'
import Pagination from '../components/Pagination'
import { useTabParam } from '../utils/useTabParam'

const PAGE_SIZE = 20

const DEFAULT_COUNTRY = 57000249 // United States -- a real, populous default (see backend note: no single worldwide player list exists anymore)

function RankBadge({ rank }: { rank: number }) {
  const color = rank === 1 ? 'text-gold' : rank === 2 ? 'text-text-secondary' : rank === 3 ? 'text-accent' : 'text-text-muted'
  return <span className={`font-bold w-8 text-right shrink-0 ${color}`}>#{rank}</span>
}

function TopPlayersTab() {
  const [locationId, setLocationId] = useState(DEFAULT_COUNTRY)
  const [page, setPage] = useState(1)
  const { data: locData } = useQuery({ queryKey: ['rank-locations'], queryFn: () => rankingsApi.locations() })
  const { data, isLoading, error } = useQuery({
    queryKey: ['top-players', locationId],
    queryFn: () => rankingsApi.topPlayers(locationId, 100),
  })

  const countries = locData?.countries ?? []
  const players = data?.players ?? []
  const pagePlayers = players.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <div>
      <p className="text-text-secondary text-sm mb-3">
        Official Path of Legends rankings by country, straight from Supercell.
      </p>
      <select value={locationId} onChange={e => { setLocationId(Number(e.target.value)); setPage(1) }}
        className="bg-bg-card border border-border rounded-xl px-4 py-2.5 text-text-primary text-sm mb-5 w-64
                   focus:outline-none focus:border-accent">
        {countries.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>

      {isLoading ? (
        <div className="h-96 bg-bg-surface rounded-xl animate-pulse" />
      ) : error ? (
        <div className="bg-bg-surface border border-border rounded-xl p-6 text-center text-danger text-sm">
          Couldn't load rankings for this location.
        </div>
      ) : (
        <>
          <Pagination page={page} pageSize={PAGE_SIZE} total={players.length} onPageChange={setPage} className="mb-3" />
          <div className="bg-bg-surface border border-border rounded-xl divide-y divide-border/50">
            {pagePlayers.map((p: any) => (
              <div key={p.tag} className="flex items-center gap-3 px-4 py-2.5">
                <RankBadge rank={p.rank} />
                <div className="flex-1 min-w-0">
                  <div className="text-text-primary font-medium truncate">{p.name}</div>
                  <div className="text-text-muted text-xs truncate">
                    {p.tag} {p.clan && `· 🏰 ${p.clan.name}`}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-gold font-bold">{p.eloRating?.toLocaleString()}</div>
                  <div className="text-text-muted text-xs">Rating</div>
                </div>
              </div>
            ))}
            {players.length === 0 && (
              <div className="p-6 text-center text-text-secondary text-sm">No ranked players found for this location yet.</div>
            )}
          </div>
          <Pagination page={page} pageSize={PAGE_SIZE} total={players.length} onPageChange={setPage} />
        </>
      )}
    </div>
  )
}

const STATUS_LABEL: Record<string, string> = {
  inPreparation: '🕐 In Preparation', inProgress: '🔴 In Progress', ended: '⬛ Ended',
}

function TournamentsTab() {
  const [query, setQuery] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const { data, isLoading, error } = useQuery({
    queryKey: ['tournament-search', searchTerm],
    queryFn: () => rankingsApi.searchTournaments(searchTerm),
    enabled: searchTerm.length >= 3,
  })

  return (
    <div>
      <p className="text-text-secondary text-sm mb-3">
        Search by tournament name -- there's no full browsable list.
      </p>
      <div className="flex gap-2 mb-5">
        <input value={query} onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && setSearchTerm(query.trim())}
          placeholder="Search tournament name (3+ characters)..."
          className="bg-bg-card border border-border rounded-xl px-4 py-2.5 text-text-primary text-sm flex-1
                     placeholder:text-text-muted focus:outline-none focus:border-accent" />
        <button onClick={() => setSearchTerm(query.trim())} disabled={query.trim().length < 3}
          className="bg-accent hover:bg-accent-hover disabled:opacity-40 text-bg-primary font-bold px-5 py-2 rounded-xl">
          Search
        </button>
      </div>

      {!searchTerm ? (
        <div className="bg-bg-surface border border-border rounded-xl p-6 text-center text-text-secondary text-sm">
          Search for a tournament by name to see live results.
        </div>
      ) : isLoading ? (
        <div className="h-64 bg-bg-surface rounded-xl animate-pulse" />
      ) : error ? (
        <div className="bg-bg-surface border border-border rounded-xl p-6 text-center text-danger text-sm">Search failed.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {(data?.tournaments ?? []).map((t: any) => (
            <div key={t.tag} className="bg-bg-surface border border-border rounded-xl p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-text-primary truncate">{t.name}</span>
                <span className="text-xs text-text-muted shrink-0 ml-2">{t.type === 'open' ? '🔓 Open' : '🔒 Password'}</span>
              </div>
              {t.description && <p className="text-xs text-text-muted mb-2 line-clamp-2">{t.description}</p>}
              <div className="flex items-center justify-between text-xs">
                <span className="text-cyan-300">{STATUS_LABEL[t.status] ?? t.status}</span>
                <span className="text-text-secondary">{t.capacity}/{t.maxCapacity} players</span>
              </div>
              <div className="text-text-muted text-xs mt-1">{t.tag} · level cap {t.levelCap}</div>
            </div>
          ))}
          {(data?.tournaments ?? []).length === 0 && (
            <div className="col-span-2 bg-bg-surface border border-border rounded-xl p-6 text-center text-text-secondary text-sm">
              No open tournaments matching "{searchTerm}" right now -- they cycle fast, try again shortly or a different keyword.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function RankingsPage() {
  const [tab, setTab] = useTabParam<'players' | 'tournaments'>('players')

  return (
    <div className="relative z-10 max-w-4xl mx-auto px-4 py-6">
      <Backdrop density={8} />
      <div className="flex items-start justify-between flex-wrap gap-2 mb-1">
        <h1 className="text-2xl font-bold text-accent">🏆 Rankings</h1>
        {/* Clan search/leaderboard moved to its own page 2026-09-02 (real
            feedback: "Make Clan a separate Feature") -- a real link here so
            anyone who remembers it living under a Rankings tab can still
            find it in one click. */}
        <Link to="/clans" className="text-sm text-cyan-300 hover:text-cyan-200 transition-colors">
          🏰 Browse Clans →
        </Link>
      </div>
      <p className="text-text-secondary text-sm mb-4">
        Official Supercell leaderboards -- top players and tournament search, live from the real API.
      </p>

      <div className="flex gap-1 mb-5">
        {([['players', '👤 Top Players'], ['tournaments', '🎪 Tournaments']] as const).map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors
              ${tab === t ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'players' && <TopPlayersTab />}
      {tab === 'tournaments' && <TournamentsTab />}
    </div>
  )
}
