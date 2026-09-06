import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { BarChart, Bar, Cell, XAxis, YAxis, ResponsiveContainer } from 'recharts'
import { Search, ChevronDown, ChevronLeft } from 'lucide-react'
import { cardsApi, decksApi, mlApi, Card } from '../utils/api'
import { searchCardsByName } from '../utils/cardSearch'
import CardImage, { CardName } from '../components/CardImage'
import { useCardDetail } from '../contexts/CardDetailContext'
import CounterDecksList from '../components/CounterDecksList'
import StrategyCounterBrowser from '../components/StrategyCounterBrowser'
import Backdrop from '../components/Backdrop'
import { useSlots, SlotBar, DeckSlots, CardPicker, TowerSlot, toggleDeckCard, PasteDeckButton, CopyDeckButton } from '../components/DeckBuilderKit'
import { useOwnedLevels } from '../utils/ownedLevels'
import { useTabParam } from '../utils/useTabParam'

const WEAKNESS_LABELS: Record<string, string> = {
  no_air_defense: 'No air defense → play air troops',
  no_spell: 'No spell → swarm them',
  high_elixir: 'High elixir → cycle fast',
  no_tank_killer: 'No tank killer → push with tanks',
  no_swarm_clear: 'No swarm clear → flood with cheap troops',
  building_heavy: 'Building heavy → use spell/drill',
  low_hp_cards: 'Fragile cards → use area spells',
}

function BuildTab({ cards }: { cards: any[] }) {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { openCard } = useCardDetail()
  const [deck, setDeck] = useState<string[]>([])
  const [towerTroop, setTowerTroop] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<any>(null)
  const [counters, setCounters] = useState<any>(null)
  // Was Browse Cards' own job (now removed -- real feedback, 2026-08-23:
  // "do not need browse cards"). A `/build?q=CardName` link (the navbar
  // search used to make these; it now opens the shared modal directly
  // instead, but old links/bookmarks may still exist) still opens that
  // card's detail here.
  useEffect(() => {
    const q = searchParams.get('q')
    if (q && cards.length) {
      const exact = cards.find((c: Card) => c.name.toLowerCase() === q.toLowerCase())
      if (exact) openCard(exact.name)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cards, searchParams.get('q')])
  // Real feedback (2026-08-22): "the empty deck slot... maybe collapsible so
  // the user can see and search cards, and turn on off the deck they are
  // building very easy." Sticky is great for glancing at progress while
  // scrolling, but on a small screen it still eats real space the card grid
  // could use -- letting the user collapse it down to just the heading (and
  // back open again in one tap) is a cheap, real way to reclaim that.
  const [panelOpen, setPanelOpen] = useState(true)
  const slots = useSlots()
  // Real feedback (2026-08-23): "Build and collection don't have to be two
  // separate tabs... apply all the logic and features." Build used to have
  // its OWN separate, thinner level system (useEditableLevels, its own
  // localStorage key) alongside Collection's real sync/unsync/set-all
  // system -- two different, disconnected "what level are my cards" stores
  // in the same app. Now both use the exact same shared hook/storage, so
  // levels set or synced in either place are the same real data everywhere.
  const { levels: ownedLevels, setLevel, bumpLevel, setAll, connectedInfo, manualOverride, unsync, resync } = useOwnedLevels(cards)
  // deck.length isn't real card count once slots can be sparse (a card
  // dropped into slot 7 while earlier slots are empty makes .length 8 even
  // with only 1 real card) -- .filter(Boolean) is the real count everywhere.
  // Also required before any Object.fromEntries/spread/JSON.stringify of
  // deck: the array iterator protocol (used by those, unlike .map/.filter)
  // does NOT skip sparse holes, it yields `undefined` for them -- crashes
  // Object.fromEntries with "Iterator value undefined is not an entry
  // object" if given the raw sparse deck instead of this filtered version.
  const filledDeck = deck.filter(Boolean)
  const levels = Object.fromEntries(filledDeck.map(n => [n, ownedLevels[n] ?? 11]))
  const bump = bumpLevel

  const toggleCard = (name: string, targetIndex?: number, fromIndex?: number) => {
    if (targetIndex == null && !deck.includes(name) && filledDeck.length >= 8) return
    setDeck(prev => toggleDeckCard(prev, name, cards, targetIndex, fromIndex))
    setCounters(null)
  }

  // Pasted names go through the exact same toggleDeckCard placement every
  // click/drag already uses, one at a time, so Evolution/Hero/Wild slot
  // eligibility is respected automatically -- no separate placement logic.
  const pasteDeck = (names: string[]) => {
    let next: string[] = []
    for (const name of names) next = toggleDeckCard(next, name, cards)
    setDeck(next)
    setAnalysis(null)
    setCounters(null)
  }

  const analyze = async () => {
    setAnalysis(await decksApi.analyzeAbsolute(levels))
  }
  const findWhatBeatsThis = async () => setCounters(await decksApi.counter(filledDeck))
  const imageFor = (n: string) => cards.find(c => c.name === n)?.image_url
  const rarityFor = (n: string) => cards.find(c => c.name === n)?.rarity
  const evolutionImageFor = (n: string) => cards.find(c => c.name === n)?.evolution_image_url
  const heroImageFor = (n: string) => cards.find(c => c.name === n)?.hero_image_url

  return (
    <>
    {/* Was `grid grid-cols-1 lg:grid-cols-3` -- real feedback (2026-08-21):
    // "maybe the Your Deck card slot follows the user as he chooses cards?"
    // It's supposed to (sticky top-20 below), and does on desktop, but never
    // actually stuck on mobile. Real root cause, found via a real Playwright
    // repro (a first "switch to flex-col" attempt here did NOT actually fix
    // it -- flex-column items don't share height with siblings any more
    // than grid rows do): the sticky panel was wrapped in its own
    // `lg:col-span-1` DIV, whose only child was the sticky panel itself --
    // that wrapper's box is sized to just the panel, giving the panel zero
    // extra room to move within before its own containing block ends. A
    // sticky element sticks within its PARENT's box; the fix is for that
    // parent to genuinely be taller than the sticky child, which normal
    // block-flow siblings give you for free (a parent's height = the SUM of
    // its children's heights) -- exactly how an ordinary sticky page header
    // works above a long article. So: no flex/grid classes at all below
    // `lg:` (plain block stacking), and `lg:col-span-1` moved directly onto
    // the sticky panel itself instead of a separate wrapper div, so it's a
    // true sibling of the (much taller) card-picker column below/beside it
    // -- on mobile that shared plain-block parent is genuinely tall enough
    // to stick within; on desktop the same two elements become real grid
    // siblings sharing one row, which is what already made this work there.
    // One more real gotcha caught by re-verifying (2026-08-21): CSS Grid's
    // default `align-items: stretch` was stretching the sticky panel's OWN
    // box to match its taller sibling's row height, which puts the "zero
    // slack" problem right back -- if the sticky element itself is exactly
    // as tall as its containing block, position:sticky again has nowhere to
    // move before scrolling off. `lg:self-start` is the standard fix for
    // this well-known "sticky sidebar in a CSS grid" recipe: it stops this
    // one item from stretching, so it keeps its own natural (shorter)
    // height while the row itself stays tall, leaving genuine room to stick.
    //
    // Real regression found 2026-08-27: "the cards get on top of the
    // buildable deck." Below `lg:` this panel and the card reel below it
    // are plain block siblings -- a sticky element with no z-index doesn't
    // automatically paint above LATER siblings once they scroll to overlap
    // it (plain DOM order wins ties), so the reel (later in the DOM)
    // painted over the pinned deck panel during scroll. Sticky positioning
    // alone doesn't imply a stacking priority -- a real z-index (below the
    // navbar's z-50, above ordinary content) on the panel is the actual fix.
    //
    // REAL BUG (2026-09-02): the z-index fix above was solving the wrong
    // problem. "sticky top-20" makes sense in the lg: 2-COLUMN desktop
    // layout below -- the panel just stays parked in its own column next to
    // separately-scrolling content, nothing else is ever positioned where
    // it floats. Below `lg:`, this whole container isn't a grid at all
    // (`lg:grid` -- no grid, no columns, until that breakpoint), so the
    // deck panel and the card picker/reel are just stacked block siblings
    // in ONE column. Sticky still applied there too, so as the page
    // scrolled, the reel (which comes right after the panel in that same
    // single column) scrolled UP INTO the exact screen position the pinned
    // panel was floating at -- confirmed via real screenshots at 390px
    // (mobile): card art and the reel's arrow buttons visibly bleeding
    // through the deck panel's own card grid. Real feedback: "the buildable
    // deck... gets over the cards and the search for cards." Scoping
    // `sticky`/`top-20`/`z-20` to `lg:` only is the actual fix -- on mobile
    // the panel is now an ordinary block that scrolls away normally, which
    // is also what "make the buildable deck smaller" wants there anyway
    // (no reason to permanently reserve screen space for it on a phone). */}
    <div className="lg:grid lg:grid-cols-3 gap-5">
        <div className="lg:col-span-1 lg:self-start bg-bg-surface border border-border rounded-xl p-4 lg:sticky lg:top-20 lg:z-20 mb-5 lg:mb-0">
          <div className="flex items-center justify-between mb-3 gap-2">
            <button onClick={() => setPanelOpen(o => !o)} className="flex-1 flex items-center justify-between min-w-0">
              <h3 className="font-semibold text-white">Your Deck ({filledDeck.length}/8)</h3>
              <ChevronDown size={16} className={`text-text-muted transition-transform shrink-0 ${panelOpen ? 'rotate-180' : ''}`} />
            </button>
            <CopyDeckButton cards={filledDeck} />
            <PasteDeckButton cards={cards} onPaste={pasteDeck} />
          </div>
          {/* Real feedback: "Make the buildable decks smaller." The panel
              already collapses (this button), but collapsing used to hide
              the deck entirely -- leaving no way to see progress at a
              glance without reopening the full 8-slot layout. A tiny
              thumbnail strip here keeps the collapsed state genuinely small
              while still useful. */}
          {!panelOpen && filledDeck.length > 0 && (
            <div className="flex items-center gap-1 flex-wrap">
              {filledDeck.map(name => {
                const c = cards.find((x: any) => x.name === name)
                return c ? (
                  <CardImage key={name} name={c.name} imageUrl={c.image_url} rarity={c.rarity} size="xs" showName={false} />
                ) : null
              })}
            </div>
          )}
          {panelOpen && <>
          <SlotBar slots={slots} />
          {/* Real card levels, right in the builder -- real feedback
              (2026-08-23): "make it one really good deck builder with your
              own card levels and sync/unsync set all to options or manual
              per card option." Compact here on purpose (this panel is
              already collapsible/sticky and shouldn't grow huge) -- per-
              card level editing for cards already IN the deck still works
              via each slot's own +/- (onLevelChange below); this is just
              the bulk sync/set-all control. */}
          {connectedInfo && !manualOverride ? (
            <div className="flex items-center justify-between gap-2 text-[10px] text-cyan-300 bg-cyan-400/10 rounded-lg px-2 py-1.5 mb-2">
              <span className="truncate">🌐 Levels synced from {connectedInfo.player}</span>
              <button onClick={unsync} className="underline shrink-0">Edit manually</button>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
              <div className="flex gap-1">
                {[[11, '11'], [14, '14'], [18, 'Max']].map(([v, label]) => (
                  <button key={label} onClick={() => setAll(v as number)}
                    className="text-[10px] px-2 py-1 rounded bg-bg-card text-text-secondary hover:text-text-primary">
                    All {label}
                  </button>
                ))}
              </div>
              {connectedInfo && manualOverride && (
                <button onClick={resync} className="text-[10px] text-cyan-300 underline">Use synced levels</button>
              )}
            </div>
          )}
          <button onClick={() => navigate('/collection')}
            className="text-[10px] text-text-muted underline mb-2 block">
            Manage all card levels →
          </button>
          <p className="text-text-muted text-[10px] mb-2">
            Drag a card into a slot to add it, drag out (or click) to remove. First 3 slots are Evolution/Hero/Wild --
            only cards eligible for that slot will land there.
          </p>
          <DeckSlots deck={deck} cards={cards} onToggle={toggleCard} slots={slots} levels={levels} onLevelChange={bump} />
          <TowerSlot cards={cards} selected={towerTroop} onSelect={setTowerTroop} />

          {filledDeck.length === 8 && (
            <div className="flex gap-2">
              <button onClick={analyze}
                className="flex-1 bg-accent hover:bg-accent-hover text-bg-primary font-bold py-2 rounded-xl transition-colors text-sm">
                Analyze Deck
              </button>
              <button onClick={findWhatBeatsThis}
                className="flex-1 bg-bg-card hover:bg-border text-text-primary font-bold py-2 rounded-xl transition-colors text-sm">
                What Beats This?
              </button>
            </div>
          )}
          </>}
        </div>

      {/* lg:min-h-[640px] -- real bug found re-testing the fix below with
          actual getBoundingClientRect measurements (not just eyeballing a
          screenshot): even with analysis/counters results moved into THIS
          column, they're not reliably taller than the left panel once it's
          holding 8 real slots + tower slot + action buttons -- and once
          this column is the SAME height as (or shorter than) the panel,
          the grid row shrinks to match, which puts sticky's "zero slack"
          problem right back (confirmed: panel top tracked scrollY 1:1 all
          the way to a NEGATIVE offset instead of clamping at 80px, meaning
          the row had no spare height for it to move within at all). A
          guaranteed minimum height here -- independent of whatever's
          actually rendered inside it -- is what actually guarantees real
          slack exists, regardless of deck/result state. */}
      <div className="lg:col-span-2 lg:min-h-[640px]">
        <CardPicker cards={cards} deck={deck} onToggle={toggleCard} levels={ownedLevels} />

        {/* Real regression found 2026-08-27 (re-testing the sticky-panel
            fix after the card picker became a short horizontal reel): this
            analysis/counters block used to render INSIDE the sticky panel
            on the left. Two real problems with that, only caught by
            actually measuring the panel's box at different scroll
            positions (not just eyeballing a screenshot): (1) once results
            rendered there, the sticky panel could grow AS TALL AS its own
            containing block/row -- position:sticky has no room to move
            once that happens (getBoundingClientRect confirmed panel
            height === parent row height, i.e. genuinely zero slack), so it
            just scrolled normally instead of sticking; (2) it also made
            the "your 8 slots" panel balloon into a giant wall of counter-
            deck cards, not the compact summary it's supposed to be.
            Rendering it HERE instead -- in the same tall right-hand column
            as the picker, not the left panel -- fixes both: it keeps the
            left panel small and gives it real height to stick against
            (this column is reliably taller once results are showing), and
            it's a more natural home for "results about the deck you're
            building" than a bare page-width section would be. */}
        {(analysis || counters) && (
          <div className="mt-4 space-y-4">
            {analysis && (
              <div className="bg-bg-surface border border-border rounded-xl p-4 space-y-2">
                <h3 className="font-semibold text-white mb-1">Deck Analysis</h3>
                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-bg-card rounded-lg p-2 text-center">
                    <div className="text-accent font-bold">{analysis.avg_elixir}</div>
                    <div className="text-text-muted text-xs">Avg Elixir</div>
                  </div>
                  <div className="bg-bg-card rounded-lg p-2 text-center" title="Combined elixir cost of the 4 cheapest cards in this deck -- lower means faster cycling back to your win condition">
                    <div className="text-accent font-bold">{analysis.cycle_cost}</div>
                    <div className="text-text-muted text-xs">Cycle Cost</div>
                  </div>
                </div>
                {analysis.warnings?.map((w: string, i: number) => (
                  <div key={i} className="text-xs text-yellow-400 bg-yellow-400/10 rounded-lg p-2">⚠️ {w}</div>
                ))}
              </div>
            )}
            {counters && (
              <CounterDecksList title="What beats this deck" deck={filledDeck} counters={counters}
                imageFor={imageFor} rarityFor={rarityFor} weaknessLabels={WEAKNESS_LABELS}
                evolutionImageFor={evolutionImageFor} heroImageFor={heroImageFor} />
            )}
          </div>
        )}
      </div>
    </div>

    {/* Real feedback (2026-08-27): "the deck built we can get the counters
        for the deck we are building by clicking the counter button, why
        need another tab with the same functions but just says Counter
        Opponent deck." The old separate "Counter an Opponent" tab was
        exactly that -- its own deck builder just to get the SAME
        decksApi.counter() result the "What Beats This?" button above
        already gets for the deck you're building here. That whole tab is
        gone; the one real, non-duplicate thing it had -- browsing counters
        by STRATEGY instead of an exact deck -- moves down here instead. */}
    <div className="mt-8 border-t border-border pt-6">
      <StrategyCounterBrowser cards={cards} />
    </div>
    </>
  )
}

// One deck's real editor -- slots/picker/copy-paste, same shape as Build's
// own deck panel, reused here for whichever deck card is currently open.
function PredictorDeckPanel({ label, deck, setDeck, cards }: {
  label: string; deck: string[]; setDeck: (d: string[]) => void; cards: any[]
}) {
  const slots = useSlots()
  const filledDeck = deck.filter(Boolean)
  // Same "make the buildable decks smaller" fix as Build's own deck panel
  // (see DeckLabPage's top-level panelOpen) -- this one had no collapse at
  // all, and with up to MAX_COMPARE_DECKS of these stacked side by side for
  // comparison, the size problem compounds fastest right here.
  const [open, setOpen] = useState(true)

  const toggle = (name: string, targetIndex?: number, fromIndex?: number) => {
    if (targetIndex == null && !deck.includes(name) && filledDeck.length >= 8) return
    setDeck(toggleDeckCard(deck, name, cards, targetIndex, fromIndex))
  }

  return (
    <div className="bg-bg-surface border border-border rounded-xl p-4 sticky top-20 z-20 self-start">
      <div className="flex items-center justify-between gap-2 mb-2">
        <button onClick={() => setOpen(o => !o)} className="flex-1 flex items-center justify-between min-w-0">
          <h3 className="font-semibold text-white">{label} ({filledDeck.length}/8)</h3>
          <ChevronDown size={16} className={`text-text-muted transition-transform shrink-0 ${open ? 'rotate-180' : ''}`} />
        </button>
        <div className="flex gap-1.5 shrink-0">
          <CopyDeckButton cards={filledDeck} />
          {/* Pasted names go through the same toggleDeckCard placement every
              click/drag already uses, one at a time, so Evolution/Hero/Wild
              slot eligibility is respected automatically. */}
          <PasteDeckButton cards={cards} onPaste={names => {
            let next: string[] = []
            for (const name of names) next = toggleDeckCard(next, name, cards)
            setDeck(next)
          }} />
        </div>
      </div>
      {!open && filledDeck.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap">
          {filledDeck.map(name => {
            const c = cards.find((x: any) => x.name === name)
            return c ? (
              <CardImage key={name} name={c.name} imageUrl={c.image_url} rarity={c.rarity} size="xs" showName={false} />
            ) : null
          })}
        </div>
      )}
      {open && <>
        <SlotBar slots={slots} />
        <DeckSlots deck={deck} cards={cards} onToggle={toggle} slots={slots} levels={{}} />
        <p className="text-text-muted text-[10px] mb-3">
          Drag a card into a slot (or click it) to add/remove. Evolution/Hero/Wild slot assignment is shown for real,
          but the win predictor model itself was trained on card presence only (not slot/level), so it doesn't change
          the prediction below.
        </p>
        <CardPicker cards={cards} deck={deck} onToggle={toggle} />
      </>}
    </div>
  )
}

const MAX_COMPARE_DECKS = 4

// Real feedback (2026-08-27): "Make the Win predictor Deck A Deck B like a
// card... initially ask the user to put number of decks to compare upto
// give it a reasonable number because we do not want the app to crash,
// then give the user decks as cards, deck 1, deck 2, deck 3, user clicks on
// the card labelled 'deck 1' to make changes on the deck 1, then exits
// from that and then chooses the card labelled 'Deck 2'." Replaces the old
// fixed Deck-A/Deck-B side-by-side layout -- up to MAX_COMPARE_DECKS real
// decks, each its own clickable card; tapping one opens its real deck
// editor (PredictorDeckPanel above) full-screen-in-place, with a "back to
// all decks" exit. The actual prediction model is pairwise (see mlApi.
// predict), so once 2+ decks are built you pick which two of them to
// actually run head-to-head, rather than the model trying to rank N at once.
function PredictorTab({ cards }: { cards: any[] }) {
  const [numDecks, setNumDecks] = useState(2)
  const [decks, setDecks] = useState<string[][]>([[], []])
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [compareA, setCompareA] = useState(0)
  const [compareB, setCompareB] = useState(1)
  const [result, setResult] = useState<any>(null)
  const [suggestions, setSuggestions] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const imageFor = (n: string) => cards.find(c => c.name === n)?.image_url
  const rarityFor = (n: string) => cards.find(c => c.name === n)?.rarity
  const evolutionImageFor = (n: string) => cards.find(c => c.name === n)?.evolution_image_url
  const heroImageFor = (n: string) => cards.find(c => c.name === n)?.hero_image_url

  // Capped at MAX_COMPARE_DECKS -- "give it a reasonable number because we
  // do not want the app to crash." Each deck card renders a live 8-icon
  // mini-grid, so an unbounded count would genuinely get heavy fast.
  const setNumDecksClamped = (raw: number) => {
    const clamped = Math.max(2, Math.min(MAX_COMPARE_DECKS, Number.isFinite(raw) ? raw : 2))
    setNumDecks(clamped)
    setDecks(prev => {
      const next = prev.slice(0, clamped)
      while (next.length < clamped) next.push([])
      return next
    })
    setCompareA(a => Math.min(a, clamped - 1))
    setCompareB(b => Math.min(b, clamped - 1))
    setResult(null)
    setSuggestions(null)
  }

  const setDeckAt = (i: number, d: string[]) => {
    setDecks(prev => prev.map((dd, idx) => (idx === i ? d : dd)))
    setResult(null)
    setSuggestions(null)
  }

  const filledA = (decks[compareA] ?? []).filter(Boolean)
  const filledB = (decks[compareB] ?? []).filter(Boolean)

  const predict = async () => {
    setLoading(true)
    setSuggestions(null)
    try {
      setResult(await mlApi.predict(filledA, filledB))
    } finally {
      setLoading(false)
    }
  }

  const loadSuggestions = async () => {
    if (!result) return
    const winningDeck = result.deck_a_win_probability >= result.deck_b_win_probability ? filledA : filledB
    setSuggestions(await decksApi.counter(winningDeck))
  }
  const losingIsA = result && result.deck_a_win_probability < result.deck_b_win_probability
  const winningLabel = losingIsA ? `Deck ${compareB + 1}` : `Deck ${compareA + 1}`

  if (editingIndex !== null) {
    return (
      <div>
        <button onClick={() => setEditingIndex(null)}
          className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-text-primary mb-3">
          <ChevronLeft size={16} /> Back to all decks
        </button>
        <PredictorDeckPanel label={`Deck ${editingIndex + 1}`} deck={decks[editingIndex]}
          setDeck={d => setDeckAt(editingIndex, d)} cards={cards} />
      </div>
    )
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-5">
        <span className="text-sm text-text-secondary">Compare</span>
        <input type="number" min={2} max={MAX_COMPARE_DECKS} value={numDecks}
          onChange={e => setNumDecksClamped(Number(e.target.value))}
          className="w-14 bg-bg-card border border-border rounded-lg px-2 py-1.5 text-sm text-center
                     text-text-primary focus:outline-none focus:border-accent" />
        <span className="text-sm text-text-secondary">real decks (up to {MAX_COMPARE_DECKS}, to keep predictions fast)</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {decks.map((d, i) => {
          const filled = d.filter(Boolean)
          return (
            <button key={i} onClick={() => setEditingIndex(i)}
              className="bg-bg-surface border border-border hover:border-accent rounded-xl p-3 text-left transition-colors">
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-white text-sm">Deck {i + 1}</span>
                <span className="text-text-muted text-xs">{filled.length}/8</span>
              </div>
              {filled.length > 0 ? (
                <div className="grid grid-cols-4 gap-0.5">
                  {Array.from({ length: 8 }).map((_, slot) => filled[slot] ? (
                    <CardImage key={slot} name={filled[slot]} imageUrl={imageFor(filled[slot])}
                      rarity={rarityFor(filled[slot])} size="xs" showName={false} magnify={false} />
                  ) : (
                    <div key={slot} className="aspect-[4/5] rounded bg-bg-card border border-dashed border-border" />
                  ))}
                </div>
              ) : (
                <p className="text-text-muted text-xs py-6 text-center">Tap to build this deck</p>
              )}
            </button>
          )
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-5">
        <select value={compareA} onChange={e => { setCompareA(Number(e.target.value)); setResult(null); setSuggestions(null) }}
          className="bg-bg-card border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent">
          {decks.map((_, i) => <option key={i} value={i}>Deck {i + 1}</option>)}
        </select>
        <span className="text-text-muted text-sm">vs</span>
        <select value={compareB} onChange={e => { setCompareB(Number(e.target.value)); setResult(null); setSuggestions(null) }}
          className="bg-bg-card border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent">
          {decks.map((_, i) => <option key={i} value={i}>Deck {i + 1}</option>)}
        </select>
        <button onClick={predict} disabled={filledA.length !== 8 || filledB.length !== 8 || compareA === compareB || loading}
          className="bg-accent hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed text-bg-primary font-bold px-5 py-2 rounded-xl text-sm">
          {loading ? 'Predicting...' : 'Predict Winner'}
        </button>
        {compareA === compareB && (
          <span className="text-yellow-400 text-xs">Pick two different decks to compare.</span>
        )}
      </div>

      {result && (
        <div className="bg-bg-surface border border-border rounded-xl p-5 mb-5">
          {result.unknown_cards?.length > 0 && (
            <div className="text-xs text-yellow-400 bg-yellow-400/10 rounded-lg p-2 mb-4">
              No match data for: {result.unknown_cards.join(', ')} (treated as neutral)
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="bg-bg-card rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-accent">{(result.deck_a_win_probability * 100).toFixed(1)}%</div>
              <div className="text-text-muted text-xs">Deck {compareA + 1} Win Probability</div>
            </div>
            <div className="bg-bg-card rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-gold">{(result.deck_b_win_probability * 100).toFixed(1)}%</div>
              <div className="text-text-muted text-xs">Deck {compareB + 1} Win Probability</div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={60}>
            <BarChart layout="vertical" data={[
              { name: 'A', value: result.deck_a_win_probability },
              { name: 'B', value: result.deck_b_win_probability },
            ]}>
              <XAxis type="number" domain={[0, 1]} hide />
              <YAxis type="category" dataKey="name" hide />
              <Bar dataKey="value" radius={4}>
                <Cell fill="#C23B3B" />
                <Cell fill="#D4AF37" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="text-text-muted text-xs mt-2">
            Model accuracy: {(result.model_accuracy * 100).toFixed(1)}%
            {result.model_auc != null && ` (AUC ${result.model_auc.toFixed(3)})`} — baseline is 50%.
            {result.caveat && <span className="block mt-1 text-yellow-400">{result.caveat}</span>}
          </p>
          {result.top_influential_cards?.length > 0 && (
            <div className="mt-4">
              <div className="text-xs font-medium text-text-secondary mb-2">Most influential cards in this matchup:</div>
              <table className="w-full text-sm">
                <tbody>
                  {result.top_influential_cards.map((c: any) => (
                    <tr key={c.card} className="border-b border-border/50">
                      <td className="py-1"><CardName name={c.card} rarity={cards.find(cc => cc.name === c.card)?.rarity} className="text-sm" /></td>
                      <td className="py-1 text-xs text-text-muted">{c.side === 'A' ? `Deck ${compareA + 1}` : `Deck ${compareB + 1}`}</td>
                      <td className="py-1 text-right text-accent text-xs">{c.importance.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <button onClick={loadSuggestions}
            className="mt-4 bg-bg-card hover:bg-border text-text-primary font-bold px-4 py-2 rounded-xl text-sm">
            Suggest a real deck to beat {winningLabel}
          </button>
        </div>
      )}

      {suggestions && (
        <CounterDecksList title={`Real decks that have actually beaten ${winningLabel}'s archetype`}
          deck={result.deck_a_win_probability >= result.deck_b_win_probability ? filledA : filledB}
          counters={suggestions} imageFor={imageFor} rarityFor={rarityFor}
          evolutionImageFor={evolutionImageFor} heroImageFor={heroImageFor} hideWeaknesses />
      )}
    </div>
  )
}

export default function DeckLabPage() {
  const [searchParams] = useSearchParams()
  // Real feedback (2026-08-23): "do not need browse cards" -- Browse Cards
  // was a separate tab whose only real job (look up/search a card) is now
  // fully covered by Build's own card picker (which shows every card, with
  // real owned levels, and click-to-detail) -- so it's gone, not just
  // hidden. ?tab= still wins when present for any old shared link.
  //
  // Real feedback (2026-08-27): "why need another tab with the same
  // functions but just says Counter Opponent deck" -- the old "Counter an
  // Opponent" tab is gone (its exact-deck counter lookup was already
  // covered by Build's own "What Beats This?" button; its one non-
  // duplicate piece, browsing counters by strategy, moved into Build
  // itself -- see BuildTab). "win predictor should not be part of
  // analytics right? maybe part of build and analyze" -- Win Predictor
  // moved here from Analytics as the second tab instead, redesigned into a
  // real multi-deck comparison (see PredictorTab).
  const [tab, setTab] = useTabParam<'build' | 'predictor'>('build')
  const { data } = useQuery({ queryKey: ['cards'], queryFn: () => cardsApi.getAll() })
  const cards = data?.items ?? []

  return (
    <div className="relative z-10 max-w-7xl mx-auto px-4 py-6">
      <Backdrop density={8} />
      <h1 className="text-2xl font-bold text-accent mb-1">🛠 Build</h1>
      <p className="text-text-secondary text-sm mb-4">Build a deck with your real card levels, find its counters, or compare decks in the Win Predictor.</p>

      <div className="flex gap-1 mb-5">
        {([['build', '🛠 Build & Analyze'], ['predictor', '🔮 Win Predictor']] as const).map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors
              ${tab === t ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'build' && <BuildTab cards={cards} />}
      {tab === 'predictor' && <PredictorTab cards={cards} />}
    </div>
  )
}
