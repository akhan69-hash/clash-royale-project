import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { metaApi, rankingsApi } from '../utils/api'

// Same real default RankingsPage.tsx uses -- Supercell's API has no single
// worldwide player list anymore, only per-location, so this is a real,
// populous stand-in rather than an invented "global" number.
const DEFAULT_COUNTRY = 57000249 // United States

/**
 * Real feedback (2026-08-26): "The player and coach tab should have basic
 * infos until user adds their player tag." Previously these pages showed
 * nothing but an in-page search form when no tag was loaded yet -- now that
 * per-page player search boxes are gone entirely (real feedback, same
 * batch: "Remove player tag search bar for all features inside the app and
 * add a universal search bar for it" -- see App.tsx's CardSearch), landing
 * here with no tag needs to be a real page, not a dead end pointing at a
 * form that no longer exists.
 *
 * Shows real, generic (not personalized) data -- same real win-rate/top-
 * deck numbers HomePage's TopCardTeaser already surfaces -- plus a clear
 * pointer at the one real way to load a player now: the search bar in the
 * top navigation.
 */
export default function NoPlayerYet({ context }: { context: 'player' | 'coach' }) {
  const navigate = useNavigate()
  const { data: topCard } = useQuery({ queryKey: ['meta-highlight-winrate'], queryFn: () => metaApi.topCards('win_rate', 1) })
  const { data: topDeck } = useQuery({ queryKey: ['meta-pulse-basic'], queryFn: () => metaApi.topDecks(1, undefined, 'win_rate') })
  // Real feedback (2026-08-27): "add more details to the player before the
  // player searching begins, like stuff that players would want to know
  // about other players." Official Supercell leaderboard, same real data
  // Rankings uses -- gives a few concrete, clickable real top players to
  // explore instead of only abstract card/deck stats.
  const { data: topPlayersData } = useQuery({ queryKey: ['nplayeryet-top-players'], queryFn: () => rankingsApi.topPlayers(DEFAULT_COUNTRY, 3) })
  const card = topCard?.cards?.[0]
  const deck = topDeck?.decks?.[0]
  const topPlayers = topPlayersData?.players?.slice(0, 3) ?? []

  return (
    <div className="bg-bg-surface border border-border rounded-xl p-6 text-center">
      <p className="text-3xl mb-2">🔍</p>
      <h2 className="text-text-primary font-semibold mb-1">
        {context === 'coach' ? 'Get coached with your own real data' : 'Look up a player'}
      </h2>
      <p className="text-text-secondary text-sm mb-4 max-w-md mx-auto">
        {/* Real feedback (2026-08-27): "i do not need the player coach on
            there... just search it bring the user to the player page and
            then we can also navigate to the coach tab from there" -- the
            universal search no longer offers a Player/Coach choice, it
            always goes to the Player page; Coach is one click from there. */}
        Use the search bar at the top of the page -- type a player name or #tag to look them up.
        {context === 'coach' && ' Once you\'re on their Player page, click "Coach me" to get here with real personalized coaching.'}
      </p>
      {(card || deck) && (
        <div className="flex flex-wrap items-center justify-center gap-2 text-xs">
          {card && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-400/30 bg-bg-card px-3 py-1.5 text-text-secondary">
              🔥 <span className="text-cyan-300 font-medium">Top card right now:</span> {card.name} ({card.win_rate}% real WR)
            </span>
          )}
          {deck && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-bg-card px-3 py-1.5 text-text-secondary">
              🃏 <span className="text-accent font-medium">Top deck right now:</span> {deck.win_rate}% real WR, {deck.frequency?.toLocaleString()} games
            </span>
          )}
        </div>
      )}
      {topPlayers.length > 0 && (
        <div className="mt-4 max-w-sm mx-auto text-left">
          <p className="text-[10px] uppercase tracking-wide text-text-muted mb-1.5 text-center">🏆 Top real players right now (US)</p>
          <div className="space-y-1">
            {topPlayers.map((p: any) => (
              <button key={p.tag} onClick={() => navigate(`/player/${String(p.tag).replace('#', '')}`)}
                className="w-full flex items-center justify-between gap-2 bg-bg-card rounded-lg px-2.5 py-1.5 text-xs hover:bg-border transition-colors">
                <span className="text-text-primary truncate">#{p.rank} {p.name}</span>
                <span className="text-gold font-medium shrink-0">🏆 {p.trophies?.toLocaleString()}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
