import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { ChevronDown } from 'lucide-react'
import { cardsApi, decksApi } from '../utils/api'
import { CardName } from '../components/CardImage'
import Backdrop from '../components/Backdrop'
import { useSlots, SlotBar, DeckSlots, CardPicker, toggleDeckCard as placeCard, PasteDeckButton, CopyDeckButton } from '../components/DeckBuilderKit'
import { useOwnedLevels } from '../utils/ownedLevels'

export default function CollectionPage() {
  const { data, isLoading: cardsLoading } = useQuery({ queryKey: ['cards'], queryFn: () => cardsApi.getAll() })
  const cards = data?.items ?? []
  const slots = useSlots()

  // Real tech debt closed 2026-08-27: this page used to carry its own
  // duplicate copy of every function useOwnedLevels already provides
  // (loadStored/loadConnected/syncFromConnected/persist/reapplyConnected/
  // setAll/setLevel/bumpLevel) -- the exact same logic Build/Synergy's Deck
  // Network/etc. already share via the hook, just copy-pasted here first
  // and never folded back in (a deliberate safety call at the time, to
  // avoid touching already-working code while adding the hook elsewhere
  // first). Needed here now anyway for real owned card COUNTS (`counts`
  // below -- see the "collections should include the number of upgrades on
  // the card" feedback), which only the hook has, so this was the natural
  // point to actually deduplicate rather than copy that too.
  const { levels, bumpLevel, setAll, connectedInfo, manualOverride, unsync, resync, reapplyConnected, counts } = useOwnedLevels(cards)
  const [deckToCheck, setDeckToCheck] = useState<string[]>([])
  const [checkResult, setCheckResult] = useState<any>(null)
  // Real feedback (2026-08-26): "you can of course minimize it. Apply that
  // logic to all buildable decks around the app." Same collapse toggle
  // Build/Counter/Win Predictor's deck panels already have.
  const [checkerOpen, setCheckerOpen] = useState(true)

  const owned = useMemo(() => Object.entries(levels).filter(([, l]) => l > 0), [levels])
  const avgLevel = owned.length ? Math.round((owned.reduce((s, [, l]) => s + l, 0) / owned.length) * 10) / 10 : 0
  const maxLevelCount = owned.filter(([, l]) => l >= 18).length

  const levelDistribution = useMemo(() => {
    const counts: Record<number, number> = {}
    for (const [, l] of owned) counts[l] = (counts[l] ?? 0) + 1
    return Object.entries(counts).map(([level, count]) => ({ level: Number(level), count })).sort((a, b) => a.level - b.level)
  }, [owned])

  // deckToCheck can be sparse (a card dropped straight into slot 7 while
  // earlier slots are empty) now that placement honors the exact slot
  // dropped on -- filledDeckToCheck is the real card list.
  const filledDeckToCheck = deckToCheck.filter(Boolean)

  const toggleCard = (name: string, targetIndex?: number, fromIndex?: number) => {
    if (targetIndex == null && !deckToCheck.includes(name) && filledDeckToCheck.length >= 8) return
    setDeckToCheck(prev => placeCard(prev, name, cards, targetIndex, fromIndex))
  }

  const pasteDeckToCheck = (names: string[]) => {
    let next: string[] = []
    for (const name of names) next = placeCard(next, name, cards)
    setDeckToCheck(next)
    setCheckResult(null)
  }

  const runDeckCheck = async () => {
    const allOwned = filledDeckToCheck.every(c => (levels[c] ?? 0) > 0)
    let analysis = null
    if (allOwned) {
      const absLevels = Object.fromEntries(filledDeckToCheck.map(name => [name, levels[name] ?? 11]))
      analysis = await decksApi.analyzeAbsolute(absLevels)
    }
    setCheckResult({ allOwned, analysis, missing: filledDeckToCheck.filter(c => (levels[c] ?? 0) === 0) })
  }

  return (
    <div className="relative z-10 max-w-6xl mx-auto px-4 py-6">
      <Backdrop density={8} />
      <h1 className="text-2xl font-bold text-accent mb-1">📦 Collection Builder</h1>
      <p className="text-text-secondary text-sm mb-4">
        Set your card levels to see what decks you can build. Saved locally in your browser.
      </p>

      {/* Real feedback (2026-08-27): "It is taking a long time to load/
          render the page, maybe add dancing skeletons as a buffer between
          rendering." This page's own card catalog fetch had no loading
          state at all -- everything below just silently rendered against
          an empty `cards` array until the real data arrived. */}
      {cardsLoading && (
        <div className="animate-pulse space-y-3 mb-6">
          <div className="grid grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-16 bg-bg-card rounded-lg" />)}
          </div>
          <div className="h-40 bg-bg-surface rounded-xl" />
        </div>
      )}

      {/* Real feedback (2026-08-22): the manual level-editing grid below and
          a connected real player's actual levels being shown side by side
          "does not make sense" -- when a player IS connected and hasn't
          asked to hand-edit on top of that, just show the real synced
          summary and get out of the way; the full manual grid/chart/set-all
          buttons collapse into an explicit "Unsync" escape hatch instead of
          always being front and center. */}
      {connectedInfo && !manualOverride ? (
        <div className="bg-bg-surface border border-cyan-400/30 rounded-xl p-4 mb-6">
          <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
            <span className="text-sm text-cyan-300">
              🌐 Using real levels from <strong>{connectedInfo.player}</strong> ({connectedInfo.tag})
            </span>
            <div className="flex gap-2">
              <button onClick={reapplyConnected}
                className="text-xs bg-cyan-400/20 text-cyan-300 px-3 py-1.5 rounded-lg hover:bg-cyan-400/30 transition-colors">
                Re-sync now
              </button>
              <button onClick={unsync}
                className="text-xs bg-bg-card text-text-secondary px-3 py-1.5 rounded-lg hover:text-text-primary transition-colors">
                Unsync (edit manually)
              </button>
            </div>
          </div>
          <div className="grid grid-cols-4 gap-3">
            <div className="bg-bg-card rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-accent">{owned.length}</div>
              <div className="text-text-muted text-xs">Cards Owned</div>
            </div>
            <div className="bg-bg-card rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-text-secondary">{cards.length - owned.length}</div>
              <div className="text-text-muted text-xs">Cards Unowned</div>
            </div>
            <div className="bg-bg-card rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-accent">{avgLevel}</div>
              <div className="text-text-muted text-xs">Average Level</div>
            </div>
            <div className="bg-bg-card rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-accent">{maxLevelCount}</div>
              <div className="text-text-muted text-xs">Max Level Cards</div>
            </div>
          </div>
        </div>
      ) : (
        <>
          {connectedInfo && manualOverride && (
            <div className="bg-bg-surface border border-border rounded-xl p-3 mb-4 flex items-center justify-between flex-wrap gap-2">
              <span className="text-sm text-text-secondary">
                ✍️ Editing manually -- {connectedInfo.player}'s real synced levels are available again anytime.
              </span>
              <button onClick={resync}
                className="text-xs bg-cyan-400/20 text-cyan-300 px-3 py-1.5 rounded-lg hover:bg-cyan-400/30 transition-colors">
                Use real synced levels
              </button>
            </div>
          )}

          <div className="flex flex-wrap gap-2 mb-5">
            <button onClick={() => setAll(11)} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-bg-card text-text-secondary hover:text-text-primary">Set All to 11</button>
            <button onClick={() => setAll(14)} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-bg-card text-text-secondary hover:text-text-primary">Set All to 14</button>
            <button onClick={() => setAll(18)} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-bg-card text-text-secondary hover:text-text-primary">Set All to Max (18)</button>
            <button onClick={() => setAll(0)} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-bg-card text-text-secondary hover:text-text-primary">Reset All (Unowned)</button>
          </div>

          {/* Overview metrics -- real feedback (2026-08-26): "add a bit
              color to different infos... more identifiable" -- these 4
              tiles used to be 3 identical text-accent + 1 muted, now each
              has its own distinct color. */}
          <div className="grid grid-cols-4 gap-3 mb-5">
            <div className="bg-bg-card rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-green-400">{owned.length}</div>
              <div className="text-text-muted text-xs">Cards Owned</div>
            </div>
            <div className="bg-bg-card rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-text-secondary">{cards.length - owned.length}</div>
              <div className="text-text-muted text-xs">Cards Unowned</div>
            </div>
            <div className="bg-bg-card rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-cyan-300">{avgLevel}</div>
              <div className="text-text-muted text-xs">Average Level</div>
            </div>
            <div className="bg-bg-card rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-gold">{maxLevelCount}</div>
              <div className="text-text-muted text-xs">Max Level Cards</div>
            </div>
          </div>

          {levelDistribution.length > 0 && (
            <div className="bg-bg-surface border border-border rounded-xl p-4 mb-6">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={levelDistribution}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#4A2E2E" vertical={false} />
                  <XAxis dataKey="level" tick={{ fill: '#8A7568', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#8A7568', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ background: '#2B1C1C', border: '1px solid #4A2E2E', borderRadius: 8 }} />
                  <Bar dataKey="count" fill="#D4AF37" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

        </>
      )}

      {/* Deck buildability checker -- shares DeckBuilderKit with Build/Counter/
          Win Predictor now (previously its own separate click-only
          implementation, the one deck-building surface in the app with no
          drag-and-drop at all), so it gets the same real slot-index-aware
          drag placement, magnetic nearest-slot snap, and click-to-detail
          info badge for free. */}
      <div className="flex items-center justify-between mb-3 gap-2">
        <button onClick={() => setCheckerOpen(o => !o)} className="flex-1 flex items-center justify-between min-w-0">
          <h2 className="text-lg font-semibold text-white">Buildable Deck Checker ({filledDeckToCheck.length}/8)</h2>
          <ChevronDown size={18} className={`text-text-muted transition-transform shrink-0 ${checkerOpen ? 'rotate-180' : ''}`} />
        </button>
        <div className="flex gap-1.5 shrink-0">
          <CopyDeckButton cards={deckToCheck.filter(Boolean)} />
          <PasteDeckButton cards={cards} onPaste={pasteDeckToCheck} />
        </div>
      </div>
      {checkerOpen && <>
      <SlotBar slots={slots} />
      <DeckSlots deck={deckToCheck} cards={cards} onToggle={toggleCard} slots={slots} levels={levels} onLevelChange={bumpLevel} />
      <CardPicker cards={cards} deck={deckToCheck} onToggle={toggleCard} levels={levels} counts={counts}
        onLevelChange={(!connectedInfo || manualOverride) ? bumpLevel : undefined} />
      <button onClick={runDeckCheck} disabled={filledDeckToCheck.length === 0}
        className="bg-accent hover:bg-accent-hover disabled:opacity-40 text-bg-primary font-bold px-5 py-2 rounded-xl mt-3 mb-8">
        Check Deck
      </button>
      </>}

      {checkResult && (
        <div className="mb-8">
          <table className="w-full text-sm bg-bg-surface border border-border rounded-xl mb-3">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 px-3 text-text-muted font-medium text-xs">Card</th>
                <th className="text-right py-2 px-3 text-text-muted font-medium text-xs">Your Level</th>
                <th className="text-right py-2 px-3 text-text-muted font-medium text-xs">Status</th>
              </tr>
            </thead>
            <tbody>
              {filledDeckToCheck.map(c => {
                const lvl = levels[c] ?? 0
                return (
                  <tr key={c} className="border-b border-border/50">
                    <td className="py-1.5 px-3"><CardName name={c} rarity={cards.find(cc => cc.name === c)?.rarity} className="text-sm" /></td>
                    <td className="py-1.5 px-3 text-right text-text-secondary">{lvl > 0 ? lvl : '❌ Unowned'}</td>
                    <td className="py-1.5 px-3 text-right text-xs">
                      {lvl >= 11 ? '✅ Ready' : lvl > 0 ? '⚠️ Underleveled' : '❌ Not owned'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {checkResult.allOwned ? (
            <div className="text-sm text-green-400 bg-green-400/10 rounded-lg p-3">
              ✅ You own all cards! Avg elixir: {checkResult.analysis?.avg_elixir}
            </div>
          ) : (
            <div className="text-sm text-red-400 bg-red-400/10 rounded-lg p-3">
              <div className="mb-1">❌ Missing cards:</div>
              <div className="flex flex-wrap gap-1.5">
                {checkResult.missing.map((c: string) => (
                  <span key={c} className="px-2 py-0.5 rounded-full bg-bg-card">
                    <CardName name={c} rarity={cards.find(cc => cc.name === c)?.rarity} className="text-xs" />
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
