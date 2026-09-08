import { useState, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Trophy, Swords, Star, Globe, GraduationCap } from 'lucide-react'
import { formatStrategy } from '../utils/formatStrategy'
import { playersApi, decksApi, cardsApi } from '../utils/api'
import CardImage, { CardName } from '../components/CardImage'
import { useCardDetail } from '../contexts/CardDetailContext'
import CounterDecksList from '../components/CounterDecksList'
import Backdrop from '../components/Backdrop'
import PageArtBackdrop from '../components/PageArtBackdrop'
import Collapsible from '../components/Collapsible'
import TowerTroopSection from '../components/TowerTroopSection'
import FavoriteButton from '../components/FavoriteButton'
import { CopyDeckButton } from '../components/DeckBuilderKit'
import DeckStatsInline from '../components/DeckStatsInline'
import Pagination from '../components/Pagination'
import { friendlyPlayerError } from '../utils/friendlyError'
import NoPlayerYet from '../components/NoPlayerYet'
import SectionSkeleton from '../components/SectionSkeleton'
import SkeletonLoader from '../components/SkeletonLoader'
import SeasonBadge from '../components/SeasonBadge'
import { addRecentPlayer, getDefaultPlayerTag, forgetDefaultPlayerTag } from '../utils/recentPlayers'

// Lowered from 10 -> 4 (2026-08-20): a full deck card is tall, so 10/page
// meant far more scrolling than intended before pagination even kicked in --
// a real complaint from mobile use. Matches the same page_size default now
// used server-side for the counter-deck lists (see backend/routers/decks.py).
const MY_DECKS_PAGE_SIZE = 4

// Player Lookup's own visual identity (2026-09-07, new-season theme +
// "every feature will have its own identity and art and font" pass) --
// royale blue, the same token Collapsible's own `accent="royale"` already
// documents as meaning "this specific player's own data" (as opposed to
// gold for community/meta data) -- and Minion Giant, the season's real new
// card, as the signature blurred background art (see PageArtBackdrop).
const PLAYER_ACCENT = '#4A6FE0'
const PLAYER_ART_CARD = 'Minion Giant'

export default function PlayerPage() {
  const { openCard } = useCardDetail()
  const { tag: urlTag } = useParams()
  const navigate = useNavigate()
  const [apiKey, setApiKey] = useState(localStorage.getItem('cr_api_key') ?? '')
  // Real bug found removing the old per-page search form (2026-08-26): this
  // used to be its own state (`searchTag`), only ever advanced by that
  // form's own search()/onSelect handlers -- meaning navigating here any
  // OTHER way (a link from another page, the universal nav search's
  // "Player" button, browser back/forward) left it stuck on whatever tag
  // was set at mount, silently never loading the new one. Deriving straight
  // from the route param instead means ANY navigation to /player/:tag
  // reacts correctly, not just the one in-page form that's now gone.
  const searchTag = (urlTag ?? '').replace('#', '')

  // Real feedback (2026-08-27): "if i go back to the player page, it should
  // remember the player tag i was searching unless i remove it." Landing on
  // a bare /player (e.g. the nav link, not a specific /player/:tag link)
  // redirects to the last real player looked up in this browser, unless
  // they explicitly asked to forget it (see the "Search a different
  // player" action below) -- `replace` so this doesn't add a dead entry to
  // browser back-history.
  useEffect(() => {
    if (!urlTag) {
      const remembered = getDefaultPlayerTag()
      if (remembered) navigate(`/player/${remembered}`, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlTag])
  const [ownCounters, setOwnCounters] = useState<any>(null)
  const [oppCounters, setOppCounters] = useState<any>(null)
  const [selectedBattle, setSelectedBattle] = useState(0)
  const [myDecksSort, setMyDecksSort] = useState<'times_played' | 'win_rate' | 'synergy_score'>('times_played')
  const [myDecksPage, setMyDecksPage] = useState(1)
  const myDecksTopRef = useRef<HTMLDivElement>(null)

  // Reset per-lookup UI state whenever the actual player being viewed
  // changes (same real trigger as above -- this used to happen inside the
  // removed search()/onSelect handlers).
  useEffect(() => {
    setOwnCounters(null)
    setOppCounters(null)
    setSelectedBattle(0)
    setMyDecksPage(1)
  }, [searchTag])

  const { data, isLoading, error } = useQuery({
    queryKey: ['player', searchTag, apiKey],
    queryFn: () => playersApi.getPlayer(searchTag, apiKey || undefined),
    enabled: !!searchTag,
  })

  const { data: battlesData } = useQuery({
    queryKey: ['battles', searchTag, apiKey],
    queryFn: () => playersApi.getBattles(searchTag, apiKey || undefined),
    enabled: !!searchTag,
  })

  // Real deck history from every battle this player's been looked up/crawled
  // for -- not just their single currently-equipped deck. Players run
  // multiple decks over time; this shows all of them with real win rates.
  const { data: deckHistoryData, isLoading: deckHistoryLoading } = useQuery({
    queryKey: ['deck-history', searchTag],
    queryFn: () => playersApi.getDeckHistory(searchTag),
    enabled: !!searchTag,
  })

  const { data: cardsData } = useQuery({ queryKey: ['cards'], queryFn: () => cardsApi.getAll() })
  const pageArtUrl = cardsData?.items?.find(c => c.name === PLAYER_ART_CARD)?.image_url
  const imageFor = (name: string) => cardsData?.items?.find(c => c.name === name)?.image_url ?? undefined
  const rarityFor = (name: string) => cardsData?.items?.find(c => c.name === name)?.rarity ?? undefined
  const evolutionImageFor = (name: string) => cardsData?.items?.find(c => c.name === name)?.evolution_image_url ?? undefined
  const heroImageFor = (name: string) => cardsData?.items?.find(c => c.name === name)?.hero_image_url ?? undefined

  const selectedBattleData = battlesData?.battles?.[selectedBattle]
  const selectedOpponentDeck: string[] = selectedBattleData?.opponent_deck ?? []
  const selectedOpponentName: string = selectedBattleData?.opponent_name ?? 'opponent'
  // Real, per-match Evolution/Hero slot usage for the selected battle (see
  // players.py's get_battles() -- confirmed real from the battlelog's
  // evolutionLevel field, unlike currentDeck which has no such signal).
  const selectedOpponentEvolved: string[] = selectedBattleData?.opponent_evolved ?? []
  const selectedOpponentHero: string[] = selectedBattleData?.opponent_hero ?? []
  const selectedOpponentAmbiguous: string[] = selectedBattleData?.opponent_ambiguous ?? []
  const cardFor = (name: string) => cardsData?.items?.find(c => c.name === name)

  const loadOwnCounters = async () => {
    const names = (data?.current_deck ?? []).map((c: any) => c.name)
    setOwnCounters(await decksApi.counter(names))
  }
  const loadOppCounters = async () => {
    setOppCounters(await decksApi.counter(selectedOpponentDeck))
  }

  // Every time you pick a different opponent from the battle list, the old
  // counters no longer describe the selected deck -- clear them until re-run.
  const selectBattle = (i: number) => {
    setSelectedBattle(i)
    setOppCounters(null)
  }

  // Persist this player's real card levels (and unlocked deck slots) so the
  // Collection and Deck Lab pages can pick them up automatically instead of
  // needing manual re-entry.
  if (data && data.cards?.length > 0) {
    const levels: Record<string, number> = {}
    // Real owned copy count per card -- real feedback (2026-08-27): "the
    // collections should include the number of upgrades on the card."
    const counts: Record<string, number> = {}
    for (const c of data.cards) {
      levels[c.name] = c.absolute_level ?? c.api_level
      if (c.count != null) counts[c.name] = c.count
    }
    localStorage.setItem('cr_connected_collection', JSON.stringify({
      player: data.name, tag: data.tag, levels, counts, unlocked_slots: data.unlocked_slots,
    }))
  }
  if (data?.tag) addRecentPlayer(data.tag, data.name ?? null)

  return (
    <div className="relative z-10 max-w-5xl mx-auto px-4 py-6">
      <Backdrop density={10} />
      <PageArtBackdrop imageUrl={pageArtUrl} accent={PLAYER_ACCENT} />
      <div className="flex items-center justify-between mb-6 flex-wrap gap-2">
        <h1 className="text-2xl flex items-baseline gap-2">
          <span className="font-display tracking-wide" style={{ color: PLAYER_ACCENT }}>Player</span>
          <span className="font-bold text-text-secondary">Lookup</span>
        </h1>
        <SeasonBadge />
      </div>

      {/* Real feedback (2026-08-26): "Remove player tag search bar for all
          features inside the app and add a universal search bar for it" --
          the tag input + Search button that used to live here are gone;
          App.tsx's CardSearch (top nav) is now the ONE place you look up a
          player. Only the optional API key setting still belongs on this
          page (it's a preference, not a search bar), tucked away closed by
          default since most visitors never need it. */}
      <Collapsible title="⚙ Using your own CR API key? (optional)" defaultOpen={false}>
        <input value={apiKey} onChange={e => { setApiKey(e.target.value); if (e.target.value) localStorage.setItem('cr_api_key', e.target.value) }}
          type="password" placeholder="CR API Key (optional)"
          className="w-full max-w-sm bg-bg-card border border-border rounded-xl px-4 py-2.5
          text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent text-sm"/>
        <p className="text-text-muted text-xs mt-2">
          Only needed if you're hitting rate limits and want to use your own (get one at developer.clashroyale.com).
        </p>
      </Collapsible>

      {!searchTag && <div className="mt-4"><NoPlayerYet context="player" /></div>}

      {isLoading && <SkeletonLoader />}
      {error && (
        <div className="text-center py-12">
          <p className="text-text-primary font-medium mb-1">{friendlyPlayerError(error)}</p>
          <p className="text-text-muted text-xs">Double-check the tag (including the #) and try again.</p>
        </div>
      )}

      {data && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-5">
          {/* Profile -- real feedback (2026-08-23): "Player name and all that
              is very big, takes the whole page till scrolling." Shrunk the
              padding, and folded King Level into the stats grid below as a
              6th tile instead of its own separate row (a nice side effect:
              grid-cols-3 x 2 rows now divides evenly at 6, where 5 always
              left an odd 3+2 split) -- one whole row of vertical space back. */}
          <div className="bg-bg-surface border border-border rounded-xl p-4">
            {/* flex-wrap + min-w-0 on the name block: at narrow widths this
                row used to hold everything (name, tag, clan, Coach button)
                on one rigid non-wrapping line, so "Name #TAG" would get
                squeezed and visually cut half onto the next line instead of
                the row just wrapping cleanly. Now the whole row wraps as a
                unit and the name/tag/clan cluster can wrap internally
                without fighting the right-side content for space. */}
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <div className="min-w-0">
                <h2 className="text-lg font-bold text-white leading-tight">{data.name}</h2>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <span className="text-text-muted text-xs">{data.tag}</span>
                  {data.clan && <span className="text-text-secondary text-xs">🏰 {data.clan}</span>}
                </div>
              </div>
              {/* Same tag, no re-typing -- Coach's own /coach/:tag route already exists.
                  Label was hidden below sm: (icon-only on mobile) -- real feedback
                  (2026-08-20): "the get coached button is not very understandable."
                  Always showing "Coach me" is worth the extra width; the header row
                  already wraps as a unit (see the comment above) so there's room. */}
              <div className="flex items-center gap-2 shrink-0">
                <button onClick={() => navigate(`/coach/${data.tag.replace('#', '')}`)}
                  title="Get coached on this player"
                  className="flex items-center gap-1.5 bg-gold hover:bg-gold-hover text-bg-primary font-bold
                             px-3 py-1.5 rounded-xl transition-colors text-sm shrink-0">
                  <GraduationCap size={16} /> Coach me
                </button>
                {/* Real feedback (2026-08-27): "it should remember the player
                    tag i was searching unless i remove it" -- this is the
                    "remove it": stop auto-redirecting a bare /player visit
                    back to this tag, and go to the generic no-tag state now. */}
                <button onClick={() => { forgetDefaultPlayerTag(); navigate('/player') }}
                  title="Stop remembering this player and search someone else"
                  className="text-text-muted hover:text-text-primary text-xs underline shrink-0">
                  Search someone else
                </button>
              </div>
            </div>
            {/* Real feedback (2026-08-26): "app coloring is kind of bland...
                add a bit color to different infos... more identifiable" --
                every tile used the same text-accent icon color regardless
                of what it actually showed, so nothing stood out at a
                glance. Each stat now gets its own color (used for BOTH the
                icon and the value, not just a tint) so the eye can jump
                straight to e.g. win rate (green) or rank (purple) instead
                of scanning every tile's label first. */}
            <div className="grid grid-cols-4 gap-2 md:gap-3">
              {[
                { icon: <Trophy size={16}/>, label: 'King Level', value: `👑 ${data.king_level}`, color: 'text-gold' },
                { icon: <Trophy size={16}/>, label: 'Trophies', value: data.trophies?.toLocaleString(), color: 'text-gold' },
                { icon: <Star size={16}/>, label: 'Best', value: data.best_trophies?.toLocaleString(), color: 'text-yellow-400' },
                // Real feedback (2026-08-26): "Add your season level on
                // Player feature." Distinct from Trophies/Best above (those
                // are lifetime, never reset) -- this is the real, current
                // SEASON's trophy count (leagueStatistics.currentSeason,
                // resets each season) plus the real seasonal-arena tier name
                // if Supercell's newer seasonal trophy road has one for this
                // player, e.g. "Seasonal Arena I".
                {
                  icon: <Trophy size={16}/>, label: 'Season',
                  value: data.season_trophies != null ? data.season_trophies.toLocaleString()
                    : data.seasonal_arena?.name ?? '—',
                  color: 'text-orange-400',
                },
                { icon: <Swords size={16}/>, label: 'Win Rate', value: `${data.win_rate}%`, color: 'text-green-400' },
                { icon: <Swords size={16}/>, label: 'W/L', value: `${data.wins}/${data.losses}`, color: 'text-text-secondary' },
                {
                  icon: <Globe size={16}/>, label: 'Global Rank',
                  value: data.global_rank != null ? `#${data.global_rank.toLocaleString()}`
                    : data.best_global_rank != null ? `Best #${data.best_global_rank.toLocaleString()}`
                    : 'Unranked',
                  color: 'text-purple-400',
                },
                {
                  icon: <Globe size={16}/>, label: 'PoL League',
                  value: data.path_of_legend_league != null ? `League ${data.path_of_legend_league}` : '—',
                  color: 'text-cyan-300',
                },
              ].map(({ icon, label, value, color }) => (
                <div key={label} className="bg-bg-card rounded-xl p-2 md:p-3 text-center">
                  <div className={`hidden sm:flex justify-center mb-1 ${color}`}>{icon}</div>
                  <div className={`font-bold text-sm sm:text-base ${color}`}>{value}</div>
                  <div className="text-text-muted text-[10px] sm:text-xs">{label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Current Deck */}
          {data.current_deck?.length > 0 && (
            <div className="bg-bg-surface border border-border rounded-xl p-5">
              <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                <h3 className="font-semibold text-white">Current Deck</h3>
                <div className="flex items-center gap-2">
                  <CopyDeckButton cards={data.current_deck.map((c: any) => c.name)} />
                  <FavoriteButton deck={{
                    cards: data.current_deck.map((c: any) => c.name), label: `${data.name}'s Current Deck`,
                    evolved_cards: data.current_deck.filter((c: any) => c.is_evolved).map((c: any) => c.name),
                    hero_cards: data.current_deck.filter((c: any) => c.is_hero).map((c: any) => c.name),
                    ambiguous_cards: data.current_deck.filter((c: any) => c.is_ambiguous).map((c: any) => c.name),
                  }} />
                  <button onClick={loadOwnCounters}
                    className="text-xs bg-accent/20 text-accent px-3 py-1.5 rounded-lg hover:bg-accent/30 transition-colors">
                    Show counters for this deck
                  </button>
                </div>
              </div>
              <div className="mb-3">
                <DeckStatsInline cards={data.current_deck.map((c: any) => c.name)} />
              </div>
              {/* Was size="md" + showStats (hitpoints/DPS printed under every
                  card) -- at 4-per-row on mobile the fixed-width md tile
                  didn't actually fit its grid cell, so cards overlapped their
                  neighbors, and the HP/DPS numbers (different digit-lengths
                  per card) made the row look ragged. Real feedback
                  (2026-08-20): "cards too big... overlapping" + "maybe show
                  [stats] when the user clicks it" -- smaller tiles fit
                  cleanly, and full stats are already one tap away via the
                  existing onClick-to-detail-modal. */}
              <div className="grid grid-cols-4 md:grid-cols-8 gap-2 mb-4">
                {data.current_deck.map((c: any) => (
                  <CardImage key={c.name} name={c.name} imageUrl={c.image_url} rarity={c.rarity} onClick={() => openCard(c.name)}
                    evolutionImageUrl={evolutionImageFor(c.name)} heroImageUrl={heroImageFor(c.name)}
                    isEvolved={c.is_evolved} isHero={c.is_hero} isAmbiguous={c.is_ambiguous}
                    elixir={c.elixir_cost} size="sm"/>
                ))}
              </div>

              {data.current_tower_troop && (
                <div className="flex items-center gap-3 pt-3 border-t border-border">
                  <CardImage name={data.current_tower_troop.name} imageUrl={data.current_tower_troop.image_url}
                    rarity={data.current_tower_troop.rarity} level={data.current_tower_troop.absolute_level} size="sm" showName={false} />
                  <div>
                    <div className="text-xs text-text-muted">King Tower Troop</div>
                    <div className="text-sm"><CardName name={data.current_tower_troop.name} rarity={data.current_tower_troop.rarity} /></div>
                    <div className="text-xs text-text-secondary">
                      Level {data.current_tower_troop.absolute_level} / {data.current_tower_troop.max_level} · {data.current_tower_troop.rarity}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          <CounterDecksList title="Counters for this player's current deck" deck={data.current_deck?.map((c: any) => c.name) ?? []} counters={ownCounters} imageFor={imageFor} rarityFor={rarityFor} evolutionImageFor={evolutionImageFor} heroImageFor={heroImageFor} />

          {/* My Decks -- every real deck this player has actually used across
              their collected battle history, not just the one they have
              equipped right now. Players run multiple decks over time. */}
          {deckHistoryLoading && (
            <div className="bg-bg-surface border border-border rounded-xl p-5">
              <SectionSkeleton rows={2} label="Loading their real deck history..." />
            </div>
          )}
          {deckHistoryData?.decks?.length > 0 && (
            <div ref={myDecksTopRef} className="bg-bg-surface border border-border rounded-xl p-5">
              <h3 className="font-semibold text-white mb-1">My Decks ({deckHistoryData.decks.length})</h3>
              <p className="text-text-muted text-xs mb-3">
                Every real deck this player has used across their collected battle history, each with its own real win rate.
              </p>
              <div className="flex flex-wrap gap-1 mb-3">
                {([
                  ['times_played', 'Most Played'],
                  ['win_rate', 'Highest Win Rate'],
                  ['synergy_score', 'Best Synergy'],
                ] as const).map(([key, label]) => (
                  <button key={key} onClick={() => { setMyDecksSort(key); setMyDecksPage(1) }}
                    className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors
                      ${myDecksSort === key ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
                    {label}
                  </button>
                ))}
              </div>
              <Pagination page={myDecksPage} pageSize={MY_DECKS_PAGE_SIZE} total={deckHistoryData.decks.length}
                onPageChange={setMyDecksPage} scrollTargetRef={myDecksTopRef} className="mb-3" />
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {[...deckHistoryData.decks].sort((a: any, b: any) => (b[myDecksSort] ?? 0) - (a[myDecksSort] ?? 0))
                  .slice((myDecksPage - 1) * MY_DECKS_PAGE_SIZE, myDecksPage * MY_DECKS_PAGE_SIZE)
                  .map((d: any, i: number) => (
                  <div key={i} className="bg-bg-card rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-text-muted">{d.wins != null ? `${d.wins}W / ${d.times_played}` : d.times_played} real games · avg {d.avg_elixir} elixir</span>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-cyan-300">{d.win_rate}% WR</span>
                        <FavoriteButton deck={{
                          cards: d.cards, label: `${data.name}'s Deck`, win_rate: d.win_rate, wins: d.wins,
                          frequency: d.times_played, avg_elixir: d.avg_elixir, cycle_cost: d.cycle_cost,
                          synergy_score: d.synergy_score, mvp_card: d.mvp_card,
                          evolved_cards: d.evolved_cards, hero_cards: d.hero_cards, ambiguous_cards: d.ambiguous_cards,
                          typical_tower_troop: d.typical_tower_troop, tower_troop_rate_pct: d.tower_troop_rate_pct,
                          tower_troop_win_rate_pct: d.tower_troop_win_rate_pct, tower_troop_image_url: d.tower_troop_image_url,
                        }} size={14} />
                      </div>
                    </div>
                    <div className="text-[10px] text-text-muted mb-2">
                      <span title="Combined elixir cost of the 4 cheapest cards in this deck -- lower means faster cycling back to your win condition">⚡ Cycle {d.cycle_cost}</span>
                      {d.synergy_score != null && <> · <span title="Average real card-pairing synergy across this deck's cards, from how those pairs have actually performed together in collected battles -- higher is better">🔗 Synergy {d.synergy_score}</span></>}
                    </div>
                    <div className="grid grid-cols-4 sm:grid-cols-8 gap-0.5 mb-1">
                      {d.cards.map((name: string) => {
                        const detail = d.cards_detail?.find((cd: any) => cd.name === name)
                        const isMvp = d.mvp_card === name
                        return (
                          <div key={name} className={isMvp ? 'rounded ring-2 ring-gold' : ''}>
                            <CardImage name={name} imageUrl={imageFor(name)} rarity={rarityFor(name)} size="xs" showName={false} onClick={() => openCard(name)}
                              evolutionImageUrl={evolutionImageFor(name)} heroImageUrl={heroImageFor(name)}
                              isEvolved={d.evolved_cards?.includes(name)} isHero={d.hero_cards?.includes(name)}
                              isAmbiguous={d.ambiguous_cards?.includes(name)} />
                            {detail?.win_rate != null && (
                              <div className={`text-center text-[9px] mt-0.5 ${isMvp ? 'text-gold font-bold' : 'text-text-muted'}`}
                                title={`${name}'s own real win rate across every real collected game it's appeared in (any deck) -- not specific to this deck.`}>
                                {detail.win_rate}%
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                    {d.mvp_card && (
                      <div className="text-[10px] text-gold mb-1">★ MVP: {d.mvp_card} (its overall real win rate is the highest of this deck's 8 cards)</div>
                    )}
                    {/* Reliability/variant-usage -- genuinely useful but
                        secondary next to the headline WR/games/cards/MVP
                        above, so collapsed by default. */}
                    <Collapsible title="More details" compact>
                      {/* Reliability: a player's own exact deck can easily have
                          fewer real games than even the app-wide meta tables --
                          shown alongside, never blended into, real win rate. */}
                      {(d.strategy_games_played != null || d.estimated_win_rate != null) && (
                        <div className="text-[10px] text-text-muted mb-1 flex flex-wrap gap-x-3 gap-y-0.5">
                          {d.strategy_games_played != null && (
                            <span title="This deck's real win rate, pooled with every other real deck (any player) sharing the same strategy (win condition + flavor)">
                              🏷 {formatStrategy(d.strategy)} overall: <span className="text-text-secondary font-medium">{d.strategy_win_rate}%</span> ({d.strategy_games_played.toLocaleString()} games)
                            </span>
                          )}
                          {d.estimated_win_rate != null && (
                            <span title="The Deck Quality Model's composition-based estimate -- learned from well-tested decks across the whole app, applied here since this exact deck has too few real games to trust on its own">
                              🤖 Model estimate: <span className="text-text-secondary font-medium">{d.estimated_win_rate}%</span>
                            </span>
                          )}
                        </div>
                      )}
                      {d.variant_known ? (
                        (d.evolved_cards?.length > 0 || d.hero_cards?.length > 0 || d.ambiguous_cards?.length > 0) && (
                          <div className="text-[10px] text-text-muted">
                            {d.evolved_cards?.length > 0 && <>⬆ {d.evolved_cards.join(', ')} evolved</>}
                            {d.evolved_cards?.length > 0 && (d.hero_cards?.length > 0 || d.ambiguous_cards?.length > 0) && ' · '}
                            {d.hero_cards?.length > 0 && <>★ {d.hero_cards.join(', ')} hero'd</>}
                            {d.hero_cards?.length > 0 && d.ambiguous_cards?.length > 0 && ' · '}
                            {d.ambiguous_cards?.length > 0 && <>? {d.ambiguous_cards.join(', ')} evolved-or-hero'd (can't tell which)</>}
                            {' '}(exactly, in all {d.times_played} of these real games)
                          </div>
                        )
                      ) : (
                        <div className="text-[10px] text-text-muted italic">Evolution/Hero data not available for these older battles</div>
                      )}
                    </Collapsible>
                    <TowerTroopSection d={d} />
                  </div>
                ))}
              </div>
              <Pagination page={myDecksPage} pageSize={MY_DECKS_PAGE_SIZE} total={deckHistoryData.decks.length}
                onPageChange={setMyDecksPage} scrollTargetRef={myDecksTopRef} />
            </div>
          )}

          {/* Evolution/Hero shards owned -- real per-card shard investment from
              this player's full collection (evolutionLevel/maxEvolutionLevel on
              the owned-cards array, distinct from currentDeck which never
              carries this field -- see players.py's get_player()). Shows every
              card they've put ANY real shards into, whether or not it's in
              their current deck. Placed after My Decks -- a collection-style
              breakdown is secondary to seeing the decks they've actually played. */}
          {data.cards?.some((c: any) => c.owns_evolution_shards || c.owns_hero_unlock) && (
            <Collapsible tempting accent="royale" icon="⬆★" persistKey="player-shards"
              title={`Evolution / Hero Shards Owned (${data.cards.filter((c: any) => c.owns_evolution_shards || c.owns_hero_unlock).length})`}
              teaser="See every card this player has invested real shards into">
              <p className="text-text-muted text-xs mb-3">
                Real shard investment from this player's full card collection. For cards capable of both systems
                (Knight, Musketeer, Wizard, Valkyrie), the API doesn't say which pool the shards apply to, so both
                are noted rather than guessed -- where this player has real tracked battles using that card, a
                "Likely" badge below shows which one they've actually played more, with the real counts.
              </p>
              <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-2">
                {data.cards.filter((c: any) => c.owns_evolution_shards || c.owns_hero_unlock).map((c: any) => (
                  <div key={c.name} className="bg-bg-card rounded-lg p-2 flex flex-col items-center text-center gap-1">
                    <CardImage name={c.name} imageUrl={c.image_url} rarity={c.rarity} size="sm" showName={false} onClick={() => openCard(c.name)}
                      evolutionImageUrl={evolutionImageFor(c.name)} heroImageUrl={heroImageFor(c.name)}
                      isEvolved={c.owns_evolution_shards} isHero={c.owns_hero_unlock} />
                    <CardName name={c.name} rarity={c.rarity} className="text-[10px]" />
                    <div className="text-[10px] text-text-muted">
                      Shards {c.shard_level}{c.shard_max ? ` / ${c.shard_max}` : ''}
                      {c.owns_evolution_shards && c.owns_hero_unlock ? ' · Evo + Hero' : c.owns_evolution_shards ? ' · Evo' : ' · Hero'}
                    </div>
                    {c.likely_variant && (
                      <div className={`text-[9px] font-semibold px-1.5 py-0.5 rounded-full ${c.likely_variant === 'hero' ? 'bg-gold/20 text-gold' : 'bg-purple-400/20 text-purple-300'}`}
                        title={`Evidence-based, from this player's own real tracked battles -- not certain, just the more common of the two in games we've actually seen (${c.likely_variant_confidence}).`}>
                        Likely: {c.likely_variant === 'hero' ? 'Hero' : 'Evolution'}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Collapsible>
          )}

          {/* Battle history -- click any row to pick which opponent to analyze below.
              Was 5 columns with long headers ("Your King Tower HP" / "Opp.
              King Tower HP") plus a 3-sentence technical explainer -- real
              feedback (2026-08-20): too much unnecessary text, and the wide
              table forced horizontal scrolling just to see the tower-HP
              columns. Result+Crowns merged into one cell, headers shortened,
              explainer cut to one line (the "why no tower level number"
              detail moved into a tooltip instead of always-visible text) --
              now fits 4 columns without needing to scroll on a real phone. */}
          {battlesData?.battles?.length > 0 && (
            <Collapsible tempting accent="royale" icon="⚔️" persistKey="player-recent-battles"
              title={`Last ${battlesData.battles.length} Real Battles`}
              teaser="Win/loss, opponents, tower HP -- pick one to find its counters below">
              <p className="text-text-muted text-xs mb-3">Click a row to pick that opponent for the counter suggester below.</p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-2 text-text-muted font-medium text-xs">Result</th>
                      <th className="text-left py-2 text-text-muted font-medium text-xs">Opponent</th>
                      <th className="text-right py-2 text-text-muted font-medium text-xs"
                        title="Real, raw tower HP from that battle -- Supercell decoupled 'tower level' from a single flat stat in the May 2026 rework, so there's no simple level number to show alongside it.">
                        Your Tower
                      </th>
                      <th className="text-right py-2 text-text-muted font-medium text-xs">Opp Tower</th>
                    </tr>
                  </thead>
                  <tbody>
                    {battlesData.battles.slice(0, 15).map((b: any, i: number) => (
                      <tr key={i} onClick={() => selectBattle(i)}
                        className={`border-b border-border/50 cursor-pointer hover:bg-bg-card/50
                          ${selectedBattle === i ? 'bg-accent/10' : ''}`}>
                        <td className={`py-1.5 font-medium whitespace-nowrap ${b.result === 'Win' ? 'text-green-400' : b.result === 'Loss' ? 'text-red-400' : 'text-text-muted'}`}>
                          {b.result} <span className="text-text-muted font-normal">{b.crowns ? `${b.crowns} 👑` : ''}</span>
                        </td>
                        {/* The full opponent name isn't essential, just which
                            row is selected (the ▸ arrow) -- real feedback
                            (2026-08-21): truncate with "..." on mobile rather
                            than letting a long name force extra table width,
                            full name still available via title on hover/long-press. */}
                        <td className="py-1.5 text-text-secondary max-w-[5.5rem] sm:max-w-none">
                          <span className="flex items-center gap-0.5">
                            {selectedBattle === i && <span className="text-accent shrink-0">▸</span>}
                            <span className="truncate" title={b.opponent_name}>{b.opponent_name}</span>
                          </span>
                        </td>
                        <td className="py-1.5 text-right text-text-muted">{b.your_king_tower_hp ?? '—'}</td>
                        <td className="py-1.5 text-right text-text-muted">{b.opponent_king_tower_hp ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {battlesData.newly_collected > 0 && (
                <p className="text-xs text-text-muted mt-3">
                  ✓ {battlesData.newly_collected} new battles saved toward the live training dataset.
                </p>
              )}
            </Collapsible>
          )}

          {/* Selected opponent's deck (from the row picked above) */}
          {selectedOpponentDeck.length > 0 && (
            <div className="bg-bg-surface border border-border rounded-xl p-5">
              <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                <h3 className="font-semibold text-white">Selected Opponent: {selectedOpponentName}</h3>
                <div className="flex items-center gap-2">
                  <CopyDeckButton cards={selectedOpponentDeck} />
                  <FavoriteButton deck={{
                    cards: selectedOpponentDeck, label: `${selectedOpponentName}'s Deck`,
                    evolved_cards: selectedOpponentEvolved, hero_cards: selectedOpponentHero, ambiguous_cards: selectedOpponentAmbiguous,
                  }} />
                  <button onClick={loadOppCounters}
                    className="text-xs bg-accent/20 text-accent px-3 py-1.5 rounded-lg hover:bg-accent/30 transition-colors">
                    Show counters for their deck
                  </button>
                </div>
              </div>
              <div className="mb-2">
                <DeckStatsInline cards={selectedOpponentDeck} />
              </div>
              <p className="text-text-muted text-[10px] mb-2">
                Real Evolution/Hero usage for this specific battle -- ⬆ evolved, ★ hero, ? evolved-or-hero'd (can't
                tell which for this card from real match data), shown exactly as played.
              </p>
              <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
                {selectedOpponentDeck.map((name: string) => {
                  const card = cardFor(name)
                  return (
                    <CardImage key={name} name={name} imageUrl={imageFor(name)} rarity={rarityFor(name)} size="sm" onClick={() => openCard(name)}
                      evolutionImageUrl={card?.evolution_image_url} heroImageUrl={card?.hero_image_url}
                      isEvolved={selectedOpponentEvolved.includes(name)} isHero={selectedOpponentHero.includes(name)}
                      isAmbiguous={selectedOpponentAmbiguous.includes(name)} />
                  )
                })}
              </div>
            </div>
          )}

          <CounterDecksList title={`Counters for ${selectedOpponentName}'s deck`} deck={selectedOpponentDeck} counters={oppCounters} imageFor={imageFor} rarityFor={rarityFor} evolutionImageFor={evolutionImageFor} heroImageFor={heroImageFor} />
        </motion.div>
      )}
    </div>
  )
}
