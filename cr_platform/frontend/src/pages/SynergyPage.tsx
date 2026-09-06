import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { cardsApi, synergyApi } from '../utils/api'
import CardImage, { CardName } from '../components/CardImage'
import { useCardDetail } from '../contexts/CardDetailContext'
import Backdrop from '../components/Backdrop'
import { useTabParam } from '../utils/useTabParam'
import { CardPicker, PasteDeckButton, CopyDeckButton } from '../components/DeckBuilderKit'
import { useOwnedLevels } from '../utils/ownedLevels'

const TYPE_COLORS: Record<string, string> = {
  Troop: '#4A90D9', Spell: '#E07B00', Building: '#7B68EE',
  Champion: '#FFD700', 'Tower Troop': '#90EE90',
}

// The real ceiling a single pair's synergy score can reach (see backend's
// get_synergy_score: win_rate_together * 10, capped at a 100% win rate; the
// curated SYNERGY_PAIRS fallback table tops out at the same 10) -- the real
// number "Network Strength" below is normalized against, not a guess.
const MAX_PAIR_SCORE = 10

/**
 * "Science lab" re-theme + real 3D tilt (2026-09-02 feedback: "make card
 * synergy deck lab like a science lab... What is Deck Network? We want a
 * visualization or three d graphic..."). The graph itself is still the same
 * real SVG node-link layout (no 3D library) -- CSS `perspective` on the
 * wrapper plus a mouse-tracked rotateX/rotateY gives the plane a genuine
 * tilt, and each node's drop-shadow grows with its real total synergy
 * (`totals[c]`) so higher-synergy cards visually "pop" toward the viewer.
 * Answers "what is Deck Network" directly via the caption in SynergyPage
 * below, and NetworkStrength (also below) is the real "how close to max"
 * metric that was missing entirely before.
 */
function SynergyNetwork({ cards, matrix, totals, cardTypes }: {
  cards: string[]; matrix: any[]; totals: Record<string, number>; cardTypes: Record<string, string>
}) {
  const n = cards.length
  const R = 150
  const cx = 200, cy = 200
  const pos: Record<string, { x: number; y: number }> = {}
  cards.forEach((c, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2
    pos[c] = { x: cx + R * Math.cos(angle), y: cy + R * Math.sin(angle) }
  })

  const edges: { a: string; b: string; score: number }[] = []
  for (let i = 0; i < cards.length; i++) {
    for (let j = i + 1; j < cards.length; j++) {
      const row = matrix.find(r => r.card === cards[i])
      const score = row?.[cards[j]] ?? 0
      if (score > 0) edges.push({ a: cards[i], b: cards[j], score })
    }
  }

  const wrapRef = useRef<HTMLDivElement>(null)
  const [tilt, setTilt] = useState({ rx: 0, ry: 0 })
  const onMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = wrapRef.current?.getBoundingClientRect()
    if (!rect) return
    const px = (e.clientX - rect.left) / rect.width - 0.5   // -0.5..0.5
    const py = (e.clientY - rect.top) / rect.height - 0.5
    setTilt({ rx: py * -14, ry: px * 14 })
  }
  const onMouseLeave = () => setTilt({ rx: 0, ry: 0 })

  return (
    <div ref={wrapRef} onMouseMove={onMouseMove} onMouseLeave={onMouseLeave}
      className="w-full max-w-md mx-auto" style={{ perspective: 900 }}>
      <svg viewBox="0 0 400 400" className="w-full transition-transform duration-150 ease-out"
        style={{ transform: `rotateX(${tilt.rx}deg) rotateY(${tilt.ry}deg)`, transformStyle: 'preserve-3d' }}>
        {edges.map((e, i) => (
          <line key={i} x1={pos[e.a].x} y1={pos[e.a].y} x2={pos[e.b].x} y2={pos[e.b].y}
            stroke="#F5A623" strokeOpacity={0.3 + (e.score / 10) * 0.6} strokeWidth={1 + (e.score / 10) * 4} />
        ))}
        {cards.map(c => {
          // Real "pop toward the viewer" cue: a card's own real total
          // synergy (sum of its real pairwise scores with every other
          // selected card) drives both its size and how far/dark its
          // shadow throws -- higher-synergy cards read as physically closer.
          const strength = totals[c] ?? 0
          const r = 10 + strength * 0.6
          return (
          <g key={c} style={{ filter: `drop-shadow(0 ${2 + strength * 0.3}px ${2 + strength * 0.4}px rgba(0,0,0,0.6))` }}>
            <circle cx={pos[c].x} cy={pos[c].y} r={r}
              fill={TYPE_COLORS[cardTypes[c] ?? 'Troop']} stroke="white" strokeWidth={1.5} />
            <text x={pos[c].x} y={pos[c].y - 16 - strength * 0.6} textAnchor="middle"
              fill="#FFFFFF" fontSize={10} fontWeight={600}>{c}</text>
          </g>
          )
        })}
      </svg>
    </div>
  )
}

/** Real "how close to max synergy" score -- average real pairwise score
 * across every selected pair, normalized against the real MAX_PAIR_SCORE
 * ceiling the backend's own scoring function can produce. `totals[c]` is
 * already the sum of card c's real score against every OTHER selected card
 * (see routers/synergy.py's /network), so summing every card's total and
 * dividing by the number of ORDERED pairs (n*(n-1)) recovers the real
 * average pairwise score without a second API call. */
function NetworkStrength({ totals }: { totals: Record<string, number> }) {
  const cards = Object.keys(totals)
  const n = cards.length
  if (n < 2) return null
  const avgPairScore = cards.reduce((sum, c) => sum + totals[c], 0) / (n * (n - 1))
  const pct = Math.max(0, Math.min(100, Math.round((avgPairScore / MAX_PAIR_SCORE) * 100)))
  return (
    <div className="bg-bg-surface border border-cyan-400/30 rounded-xl p-4 mb-4">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-semibold text-cyan-300">🧫 Network Strength</span>
        <span className="text-sm font-bold text-cyan-300">{pct}% of max</span>
      </div>
      <div className="w-full h-2 rounded-full bg-bg-card overflow-hidden mb-2">
        <div className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-cyan-300 transition-all duration-500"
          style={{ width: `${pct}%` }} />
      </div>
      <p className="text-text-muted text-xs">
        Average real synergy across every pair of your {n} picked cards, against the real ceiling a pair can reach
        (a 100% real win rate together). This graph -- the "Deck Network" -- visualizes those same real pairings:
        each node is a card, each line is a real pairing, thicker/brighter lines and bigger nodes mean stronger
        real synergy.
      </p>
    </div>
  )
}

type SortKey = 'score' | 'co_occurrence' | 'win_rate_together'

const SORT_LABELS: Record<SortKey, string> = {
  score: 'Best Match',
  co_occurrence: 'Most Common',
  win_rate_together: 'Best Win Rate',
}

export default function SynergyPage() {
  const { openCard } = useCardDetail()
  const [tab, setTab] = useTabParam<'lookup' | 'network'>('lookup')
  const [selectedCard, setSelectedCard] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('score')
  const [netCards, setNetCards] = useState<string[]>([])
  const [netResult, setNetResult] = useState<any>(null)
  const { data: suggestData, refetch: refetchSuggestions, isFetching: suggestLoading } = useQuery({
    queryKey: ['synergy-suggest', netCards.join(',')],
    queryFn: () => synergyApi.suggest(netCards, 12),
    enabled: false,
  })

  const { data } = useQuery({ queryKey: ['cards'], queryFn: () => cardsApi.getAll() })
  const cards = data?.items ?? []
  const cardTypes: Record<string, string> = Object.fromEntries(cards.map(c => [c.name, c.type]))
  const cardRarities: Record<string, string> = Object.fromEntries(cards.map(c => [c.name, c.rarity]))
  // Same real owned-level system as Build/Collection (2026-08-23: "apply same
  // logic to deck network deck builder") -- shows real levels on cards you
  // own, sorts owned-first in the picker below.
  const { levels: ownedLevels } = useOwnedLevels(cards)

  const { data: partnersData, isLoading: partnersLoading } = useQuery({
    queryKey: ['synergy', selectedCard],
    queryFn: () => synergyApi.topPartners(selectedCard, 200),
    enabled: !!selectedCard,
  })

  // Re-sort client-side so switching sort doesn't need a re-fetch. Rows with
  // no real data for the chosen sort field (curated-rule fallback partners
  // have no co_occurrence/win_rate_together) sink to the bottom either way.
  const sortedPartners = [...(partnersData?.partners ?? [])].sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    return bv - av
  })

  const toggleNetCard = (name: string) => {
    if (netCards.includes(name)) setNetCards(netCards.filter(c => c !== name))
    else if (netCards.length < 8) setNetCards([...netCards, name])
  }

  const runNetwork = async () => {
    const res = await synergyApi.network(netCards)
    setNetResult(res)
  }

  return (
    <div className="relative z-10 max-w-6xl mx-auto px-4 py-6">
      <Backdrop density={8} />
      <h1 className="text-2xl font-bold text-cyan-300 mb-1">🧪 Synergy Lab</h1>
      <p className="text-text-secondary text-sm mb-4">
        Which cards pair well together, based on real battles -- run a compatibility test on one card, or build a
        real network out of a whole deck.
      </p>

      <div className="flex gap-1 mb-5">
        {(['lookup', 'network'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors
              ${tab === t ? 'bg-cyan-500 text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
            {t === 'lookup' ? '🧪 Card Lookup' : '🧫 Deck Network'}
          </button>
        ))}
      </div>

      {tab === 'lookup' && (
        <div>
          <div className="flex flex-wrap items-center gap-3 mb-5">
            <select value={selectedCard} onChange={e => setSelectedCard(e.target.value)}
              className="bg-bg-card border border-border rounded-xl px-4 py-2.5 text-text-primary text-sm w-64
                         focus:outline-none focus:border-accent">
              <option value="">Select a card...</option>
              {cards.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>

            {selectedCard && (
              <div className="flex gap-1">
                {(Object.keys(SORT_LABELS) as SortKey[]).map(k => (
                  <button key={k} onClick={() => setSortKey(k)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
                      ${sortKey === k ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
                    {SORT_LABELS[k]}
                  </button>
                ))}
              </div>
            )}
          </div>

          {selectedCard && !partnersLoading && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <div className="bg-bg-surface border border-cyan-400/20 rounded-xl p-4">
                <p className="text-text-muted text-xs mb-2">
                  Showing all {sortedPartners.length} partners{partnersData?.total_partners > sortedPartners.length
                    ? ` of ${partnersData.total_partners}` : ''} -- scroll for more.
                </p>
                <div className="overflow-x-auto max-h-[28rem] overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-bg-surface">
                      <tr className="border-b border-border">
                        <th className="text-left py-2 text-text-muted font-medium text-xs">Partner</th>
                        <th className="text-right py-2 text-text-muted font-medium text-xs">Score</th>
                        <th className="text-right py-2 text-text-muted font-medium text-xs">Together</th>
                        <th className="text-right py-2 text-text-muted font-medium text-xs">Win Rate</th>
                        <th className="text-right py-2 text-text-muted font-medium text-xs">Source</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedPartners.map((p: any) => (
                        <tr key={p.partner} className="border-b border-border/50">
                          <td className="py-1.5 flex items-center gap-2">
                            {p.image_url && <img src={p.image_url} alt="" className="w-6 h-6 object-contain" />}
                            <CardName name={p.partner} rarity={cardRarities[p.partner]} className="text-sm" />
                          </td>
                          <td className="py-1.5 text-right text-accent font-semibold">{p.score}</td>
                          <td className="py-1.5 text-right text-text-secondary text-xs">
                            {p.co_occurrence != null ? p.co_occurrence.toLocaleString() : '—'}
                          </td>
                          <td className="py-1.5 text-right text-text-secondary text-xs">
                            {p.win_rate_together != null ? `${p.win_rate_together}%` : '—'}
                          </td>
                          <td className="py-1.5 text-right text-text-muted text-xs capitalize">{p.source}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="bg-bg-surface border border-cyan-400/20 rounded-xl p-4">
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={sortedPartners.slice(0, 20)}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#4A2E2E" vertical={false} />
                    <XAxis dataKey="partner" tick={{ fill: '#8A7568', fontSize: 9 }} angle={-40} textAnchor="end"
                      interval={0} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: '#8A7568', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ background: '#2B1C1C', border: '1px solid #4A2E2E', borderRadius: 8 }} />
                    <Bar dataKey={sortKey} fill="#F5A623" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'network' && (
        <div>
          <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
            <p className="text-text-secondary text-sm">Select up to 8 cards to see how they connect.</p>
            <div className="flex gap-1.5 shrink-0">
              <CopyDeckButton cards={netCards} />
              <PasteDeckButton cards={cards} onPaste={names => setNetCards(names.slice(0, 8))} />
            </div>
          </div>
          <div className="flex flex-wrap gap-2 mb-3">
            {netCards.map(c => (
              <span key={c} className="text-xs px-2 py-1 rounded-full bg-accent/20 text-accent">{c}</span>
            ))}
          </div>
          {/* Same real searchable CardPicker every other deck builder in the
              app uses (real feedback, 2026-08-23: "do not need browse cards"
              -- this used to be its own always-visible, unsearchable 8-col
              grid) -- shows real owned levels and lets you search instead of
              scrolling ~120 cards to find one. */}
          <div className="mb-4">
            <CardPicker cards={cards} deck={netCards} onToggle={toggleNetCard} levels={ownedLevels} />
          </div>
          <div className="flex flex-wrap gap-2 mb-5">
            <button onClick={runNetwork} disabled={netCards.length < 2}
              className="bg-accent hover:bg-accent-hover disabled:opacity-40 text-bg-primary font-bold px-5 py-2 rounded-xl">
              Build Network
            </button>
            <button onClick={() => refetchSuggestions()} disabled={netCards.length >= 8}
              className="bg-bg-card hover:bg-border disabled:opacity-40 text-text-primary font-bold px-5 py-2 rounded-xl text-sm">
              {suggestLoading ? 'Thinking...' : '💡 Suggest cards to add'}
            </button>
          </div>

          {suggestData?.suggestions?.length > 0 && (
            <div className="bg-bg-surface border border-cyan-400/30 rounded-xl p-4 mb-5">
              <h3 className="text-sm font-semibold text-white mb-1">
                {netCards.length > 0 ? 'Best real cards to add' : 'Best real cards overall'}
              </h3>
              <p className="text-text-muted text-xs mb-3">
                {netCards.length > 0
                  ? 'Ranked by average real synergy score against your currently selected cards. Click one to add it.'
                  : 'Select cards above first to rank by synergy with them -- for now, ranked by real overall win rate.'}
              </p>
              <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-2">
                {suggestData.suggestions.map((s: any) => (
                  <div key={s.name} onClick={() => netCards.length < 8 && toggleNetCard(s.name)} className="cursor-pointer text-center">
                    <CardImage name={s.name} imageUrl={s.image_url} elixir={s.elixir} size="sm" showName={false}
                      onInfoClick={() => openCard(s.name)} />
                    {s.avg_synergy != null && <div className="text-[10px] text-cyan-300 font-medium mt-1.5">🔗 {s.avg_synergy}</div>}
                    {s.win_rate_pct != null && <div className="text-[9px] text-text-muted mt-0.5">{s.win_rate_pct}% WR</div>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {netResult && (
            <>
            <NetworkStrength totals={netResult.totals} />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <div className="bg-bg-surface border border-cyan-400/20 rounded-xl p-4">
                <SynergyNetwork cards={netResult.cards} matrix={netResult.matrix} totals={netResult.totals} cardTypes={cardTypes} />
              </div>
              <div className="bg-bg-surface border border-cyan-400/20 rounded-xl p-4">
                <h3 className="text-sm font-semibold text-white mb-3">Most Synergistic Cards</h3>
                <table className="w-full text-sm">
                  <tbody>
                    {Object.entries(netResult.totals as Record<string, number>)
                      .sort((a, b) => b[1] - a[1])
                      .map(([card, total]) => (
                        <tr key={card} className="border-b border-border/50">
                          <td className="py-1.5 text-text-primary">{card}</td>
                          <td className="py-1.5 text-right text-accent font-semibold">{total}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
