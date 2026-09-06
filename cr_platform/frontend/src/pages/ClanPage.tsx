import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Search, ArrowLeft } from 'lucide-react'
import { rankingsApi } from '../utils/api'
import Backdrop from '../components/Backdrop'
import Pagination from '../components/Pagination'
import { parseCrTimestamp } from '../utils/crTime'

const PAGE_SIZE = 20
const DEFAULT_CLAN_REGION = 57000006 // International -- clan rankings DO support the broad region groupings, and this IS the real worldwide clan ranking

// The API's own region name is literally "International" -- relabeled here
// for clarity since it's functionally the real worldwide clan leaderboard,
// not just one more region alongside Europe/Asia/etc.
const regionDisplayName = (name: string) => name === 'International' ? '🌍 World' : name

// Real "last seen" for a clan member, from the API's own real lastSeen
// timestamp -- coarse buckets (not exact hours/minutes) since this is meant
// as a quick "still active?" signal, not a precise activity log.
function lastActiveLabel(lastSeen?: string | null): string | null {
  const date = parseCrTimestamp(lastSeen)
  if (!date) return null
  const hours = (Date.now() - date.getTime()) / 3_600_000
  if (hours < 1) return 'Active now'
  if (hours < 24) return `Active ${Math.round(hours)}h ago`
  const days = Math.round(hours / 24)
  return `Active ${days}d ago`
}

function RankBadge({ rank }: { rank: number }) {
  const color = rank === 1 ? 'text-gold' : rank === 2 ? 'text-text-secondary' : rank === 3 ? 'text-accent' : 'text-text-muted'
  return <span className={`font-bold w-8 text-right shrink-0 ${color}`}>#{rank}</span>
}

// Real feedback (2026-09-02): "clan search only in 'clan' tab with top clan
// leaderboard and other stuff but all clan stuff, maybe also clan battle
// close or in this many days" -- one place holds the leaderboard, a real
// name search, and (once a clan is picked) its real member list plus real
// River Race status. PROMOTED to its own top-level page 2026-09-02 (real
// feedback: "Make Clan a separate Feature") -- was a tab buried inside
// Rankings; clan stuff is substantial enough (search + full member browsing
// + war status) to be a real destination on its own rather than one of
// three tabs sharing a page.
//
// Real gap found while building this: the live /clans/{tag}/currentriverrace
// response does NOT include a warEndTime or collectionEndTime field at all
// (confirmed against the real production API, not just docs -- only
// state/periodType/periodIndex/sectionIndex exist) -- Supercell's public
// documentation this was built from turned out wrong for the current API
// shape. Rather than fabricate a day-countdown from an assumed weekly
// schedule (Supercell has changed the River Race format before, and
// guessing wrong is worse than not showing it), this shows the real
// periodType/state honestly instead.
function ClanDetail({ tag, onBack }: { tag: string; onBack: () => void }) {
  const navigate = useNavigate()
  const { data: clan, isLoading, error } = useQuery({
    queryKey: ['clan-detail', tag],
    queryFn: () => rankingsApi.getClan(tag),
  })
  // River Race data is a separate real endpoint from clan detail -- fails
  // independently (fetched best-effort) so a real clan with no active race
  // (or a transient API hiccup on just this endpoint) still shows everything
  // else about the clan instead of failing the whole view.
  const { data: war } = useQuery({
    queryKey: ['clan-war', tag],
    queryFn: () => rankingsApi.getClanWar(tag),
    retry: false,
  })

  const members = clan?.memberList ?? []

  return (
    <div>
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-text-primary mb-4 transition-colors">
        <ArrowLeft size={15} /> Back to leaderboard
      </button>

      {isLoading ? (
        <div className="h-64 bg-bg-surface rounded-xl animate-pulse" />
      ) : error || !clan ? (
        <div className="bg-bg-surface border border-border rounded-xl p-6 text-center text-danger text-sm">
          Couldn't load this clan.
        </div>
      ) : (
        <>
          <div className="bg-bg-surface border border-border rounded-xl p-4 mb-4">
            <div className="flex items-start justify-between flex-wrap gap-2 mb-2">
              <div>
                <h2 className="text-lg font-bold text-text-primary">{clan.name}</h2>
                <span className="text-xs text-text-muted">{clan.tag} · {clan.location?.name ?? 'Unknown location'}</span>
              </div>
              <div className="text-right">
                <div className="text-gold font-bold">{clan.clanScore?.toLocaleString()}</div>
                <div className="text-text-muted text-xs">Clan Score</div>
              </div>
            </div>
            {clan.description && <p className="text-xs text-text-secondary mb-3">{clan.description}</p>}
            <div className="flex flex-wrap gap-4 text-xs text-text-muted">
              <span>👥 {clan.members}/50 members</span>
              <span>🏆 {clan.requiredTrophies?.toLocaleString()}+ required trophies</span>
              <span>🎁 {clan.donationsPerWeek?.toLocaleString()} donations/week</span>
            </div>
          </div>

          {/* Real live River Race status -- the actual API doesn't expose an
              end timestamp (see the comment above), so this shows what IS
              real (periodType/state) rather than a guessed countdown.
              periodIndex is a real day-count within the race, shown as
              honest context, not a claim about days remaining. */}
          {war && (
            <div className="bg-bg-surface border border-cyan-400/30 rounded-xl p-4 mb-4">
              <div className="text-sm text-cyan-300 font-semibold mb-1">
                {war.periodType === 'warDay' ? '⚔️ War Day in progress' : '🛠️ Training Days'}
              </div>
              <p className="text-xs text-text-secondary">
                {war.periodType === 'warDay'
                  ? 'This clan is actively battling in River Race right now.'
                  : 'Training Days -- War Day starts once these finish.'}
                {war.periodIndex != null && <> Day {war.periodIndex} of this River Race.</>}
              </p>
            </div>
          )}

          <h3 className="text-sm font-semibold text-white mb-2">Members ({members.length})</h3>
          <div className="bg-bg-surface border border-border rounded-xl divide-y divide-border/50 max-h-[28rem] overflow-y-auto">
            {members
              .slice()
              .sort((a: any, b: any) => (a.clanRank ?? 999) - (b.clanRank ?? 999))
              .map((m: any) => (
                <button key={m.tag} onClick={() => navigate(`/player/${m.tag.replace('#', '')}`)}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-bg-card transition-colors">
                  <span className="text-text-muted text-xs w-6 text-right shrink-0">#{m.clanRank}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-text-primary text-sm font-medium truncate">
                      {m.name} {m.role === 'leader' && <span className="text-gold text-xs">👑</span>}
                      {(m.role === 'coLeader' || m.role === 'elder') && <span className="text-text-muted text-xs">({m.role === 'coLeader' ? 'Co-Leader' : 'Elder'})</span>}
                    </div>
                    <div className="text-text-muted text-xs truncate">
                      {m.tag}{lastActiveLabel(m.lastSeen) && <> · {lastActiveLabel(m.lastSeen)}</>}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-accent font-semibold text-sm">{m.trophies?.toLocaleString()}</div>
                    <div className="text-text-muted text-xs">🏆</div>
                  </div>
                </button>
              ))}
            {members.length === 0 && (
              <div className="p-6 text-center text-text-secondary text-sm">No member data available.</div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default function ClanPage() {
  const [locationId, setLocationId] = useState(DEFAULT_CLAN_REGION)
  const [page, setPage] = useState(1)
  const [query, setQuery] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedClan, setSelectedClan] = useState<string | null>(null)
  const { data: locData } = useQuery({ queryKey: ['rank-locations'], queryFn: () => rankingsApi.locations() })
  const { data, isLoading, error } = useQuery({
    queryKey: ['top-clans', locationId],
    queryFn: () => rankingsApi.topClans(locationId, 100),
  })
  const { data: searchData, isLoading: searchLoading } = useQuery({
    queryKey: ['clan-search', searchTerm],
    queryFn: () => rankingsApi.searchClans(searchTerm),
    enabled: searchTerm.length >= 3,
  })

  const regions = locData?.regions ?? []
  const countries = locData?.countries ?? []
  const clans = data?.clans ?? []
  const pageClans = clans.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const searchResults = searchData?.clans ?? []

  return (
    <div className="relative z-10 max-w-4xl mx-auto px-4 py-6">
      <Backdrop density={8} />
      <h1 className="text-2xl font-bold text-accent mb-1">🏰 Clans</h1>
      <p className="text-text-secondary text-sm mb-4">
        Find a real clan by name, browse the official leaderboard, or check a clan's real member list and War
        status -- live from Supercell's API.
      </p>

      {selectedClan ? (
        <ClanDetail tag={selectedClan} onBack={() => setSelectedClan(null)} />
      ) : (
        <>
          <div className="flex gap-2 mb-5">
            <div className="relative flex-1">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input value={query} onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && setSearchTerm(query.trim())}
                placeholder="Find a clan by name (3+ characters)..."
                className="w-full bg-bg-card border border-border rounded-xl pl-9 pr-4 py-2.5 text-text-primary text-sm
                           placeholder:text-text-muted focus:outline-none focus:border-accent" />
            </div>
            <button onClick={() => setSearchTerm(query.trim())} disabled={query.trim().length < 3}
              className="bg-accent hover:bg-accent-hover disabled:opacity-40 text-bg-primary font-bold px-5 py-2 rounded-xl shrink-0">
              Search
            </button>
          </div>

          {searchTerm && (
            <div className="mb-6">
              {searchLoading ? (
                <div className="h-24 bg-bg-surface rounded-xl animate-pulse" />
              ) : (
                <div className="bg-bg-surface border border-border rounded-xl divide-y divide-border/50">
                  {searchResults.map((c: any) => (
                    <button key={c.tag} onClick={() => setSelectedClan(c.tag)}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-bg-card transition-colors">
                      <div className="flex-1 min-w-0">
                        <div className="text-text-primary font-medium truncate">{c.name}</div>
                        <div className="text-text-muted text-xs truncate">{c.tag} · {c.members}/50 members</div>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-gold font-bold">{c.clanScore?.toLocaleString()}</div>
                        <div className="text-text-muted text-xs">Clan Score</div>
                      </div>
                    </button>
                  ))}
                  {searchResults.length === 0 && (
                    <div className="p-6 text-center text-text-secondary text-sm">No clans found matching "{searchTerm}".</div>
                  )}
                </div>
              )}
            </div>
          )}

          <h3 className="text-sm font-semibold text-white mb-2">Leaderboard</h3>
          <select value={locationId} onChange={e => { setLocationId(Number(e.target.value)); setPage(1) }}
            className="bg-bg-card border border-border rounded-xl px-4 py-2.5 text-text-primary text-sm mb-5 w-64
                       focus:outline-none focus:border-accent">
            <optgroup label="Regions">
              {regions.map((r: any) => <option key={r.id} value={r.id}>{regionDisplayName(r.name)}</option>)}
            </optgroup>
            <optgroup label="Countries">
              {countries.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </optgroup>
          </select>

          {isLoading ? (
            <div className="h-96 bg-bg-surface rounded-xl animate-pulse" />
          ) : error ? (
            <div className="bg-bg-surface border border-border rounded-xl p-6 text-center text-danger text-sm">
              Couldn't load rankings for this location.
            </div>
          ) : (
            <>
              <Pagination page={page} pageSize={PAGE_SIZE} total={clans.length} onPageChange={setPage} className="mb-3" />
              <div className="bg-bg-surface border border-border rounded-xl divide-y divide-border/50">
                {pageClans.map((c: any) => (
                  <button key={c.tag} onClick={() => setSelectedClan(c.tag)}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-bg-card transition-colors">
                    <RankBadge rank={c.rank} />
                    <div className="flex-1 min-w-0">
                      <div className="text-text-primary font-medium truncate">{c.name}</div>
                      <div className="text-text-muted text-xs truncate">{c.tag} · {c.members}/50 members</div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-gold font-bold">{c.clanScore?.toLocaleString()}</div>
                      <div className="text-text-muted text-xs">Clan Score</div>
                    </div>
                  </button>
                ))}
                {clans.length === 0 && (
                  <div className="p-6 text-center text-text-secondary text-sm">No ranked clans found for this location yet.</div>
                )}
              </div>
              <Pagination page={page} pageSize={PAGE_SIZE} total={clans.length} onPageChange={setPage} />
            </>
          )}
        </>
      )}
    </div>
  )
}
