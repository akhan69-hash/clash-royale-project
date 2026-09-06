import { useState, useRef, useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { AnimatePresence } from 'framer-motion'
import { Users, Search, GraduationCap, Newspaper, Home as HomeIcon, Star, LogIn, LogOut } from 'lucide-react'
// Route-based code splitting: every page used to be a static top-level
// import, so the very first paint (any route) had to download and parse
// ALL 11 pages' JS in one bundle before React could render even the Home
// page -- a real, measurable chunk of "rendering not fast enough" on a
// cold load. HomePage stays eager (it's what almost every visit starts
// on, no reason to add a loading flicker for the common case); the rest
// load on demand, split into their own chunk by Vite automatically.
import HomePage from './pages/HomePage'
const DeckLabPage = lazy(() => import('./pages/DeckLabPage'))
const PlayerPage = lazy(() => import('./pages/PlayerPage'))
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'))
const CollectionPage = lazy(() => import('./pages/CollectionPage'))
const SynergyPage = lazy(() => import('./pages/SynergyPage'))
const RankingsPage = lazy(() => import('./pages/RankingsPage'))
const ClanPage = lazy(() => import('./pages/ClanPage'))
const CoachingPage = lazy(() => import('./pages/CoachingPage'))
const WhatsNextPage = lazy(() => import('./pages/WhatsNextPage'))
const FavoritesPage = lazy(() => import('./pages/FavoritesPage'))
const AuthPage = lazy(() => import('./pages/AuthPage'))
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage'))
import PageTransition from './components/PageTransition'
import MegaMenu from './components/MegaMenu'
import SideMenu from './components/SideMenu'
import { playersApi } from './utils/api'
import { useFavoriteDecks } from './utils/favorites'
import { getRecentPlayers } from './utils/recentPlayers'
import { CardDetailProvider } from './contexts/CardDetailContext'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { supabase } from './utils/supabaseClient'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5 * 60 * 1000, retry: 1 } }
})

// Game-like IA: just 4 primary destinations in the top nav. Build (Cards +
// Deck Lab merged), Analytics, Rankings, Collection, and Synergy are all
// still real pages/routes -- just reached via Home's tile menu now instead
// of cluttering the top bar.
const NAV = [
  { to: '/', icon: <HomeIcon size={18}/>, label: 'Home' },
  { to: '/player', icon: <Users size={18}/>, label: 'Player' },
  { to: '/coach', icon: <GraduationCap size={18}/>, label: 'Coach' },
  { to: '/news', icon: <Newspaper size={18}/>, label: 'News' },
]

// Player-only universal search -- real feedback (2026-08-27): "the search
// tag should only search for players not cards." A prior round merged in
// card-name matches too (2026-08-23, itself a fix for "the search on top
// right corner does not even search player") -- pulled back out: the app
// already has a dedicated card search inside every deck builder's picker,
// and mixing the two in one small dropdown was exactly the kind of
// "repetitive/confusing" search surface this whole app has been trying to
// get away from.
//
// Real feedback, same batch: "i do not need the player coach on there...
// just search it bring the user to the player page and then we can also
// navigate to the coach tab from there." The old two-button-per-row
// (Player/Coach) layout is gone -- clicking a result just goes to /player/
// :tag (PlayerPage already has its own "Coach me" button once you're there).
//
// Real bug found 2026-08-27: "Cheeka_peeka... searched multiple times using
// the tag 9UV9VLV8V, but when i try to search it up it does not show at
// all." Root cause -- search_players() only ever indexed a player's name
// from OTHER people's battle logs (the looked-up player's own name was
// never captured, a real, honestly-documented coverage gap at the time).
// Looking someone up directly used to leave their real name unsearchable
// forever. Fixed in players.py -- see save_battles()'s new team_name
// capture -- so a name becomes searchable the FIRST time that player is
// looked up directly, not only once someone else's battle happens to
// mention them.
//
// Real bug found 2026-08-20: the full-width input (w-24 sm:w-48) was part of
// why the navbar's total content genuinely didn't fit a real 390px phone --
// the sum of every item's minimum width exceeded the viewport, and since
// nothing was set up to actually clip/scroll the overflow, later items
// (MegaMenu, Favorites) rendered UNDERNEATH the nav links' overflowing
// content instead of after it, making "Coach" literally untappable (its own
// hit area was occupied by the "More" button sitting at the same position).
// Below `sm:`, this is now a compact icon-only button -- the full live-
// search input only renders at `sm:` and up, where there's actually room.
function PlayerSearch() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const q = query.trim()
  const { data: playerData } = useQuery({
    queryKey: ['nav-player-search', q],
    queryFn: () => playersApi.search(q),
    enabled: q.length >= 2,
    staleTime: 60_000,
  })

  // Real feedback (2026-08-26): "remembering playertags... it is very weird
  // right now" -- recent tags YOU'VE looked up (see utils/recentPlayers.ts)
  // show immediately on focus, even before typing anything, and stay
  // ranked ahead of the server's any-player-ever-seen search once you do
  // type (deduped by tag so a recent player never shows twice).
  const qUpper = q.toUpperCase().replace(/^#/, '')
  const recentMatches = getRecentPlayers().filter(p =>
    q.length === 0 || p.tag.includes(qUpper) || (p.name ?? '').toLowerCase().includes(q.toLowerCase()))
  const serverMatches = (playerData?.results ?? []).filter((r: any) => !recentMatches.some(p => p.tag === r.tag))
  const playerMatches = [...recentMatches.map(p => ({ ...p, recent: true })), ...serverMatches].slice(0, 8)

  const goPlayer = (tag: string) => {
    navigate(`/player/${tag}`)
    setQuery('')
    setOpen(false)
    setMobileOpen(false)
  }

  const matchList = (
    <>
      {playerMatches.map((p: any) => (
        <button key={p.tag} onMouseDown={() => goPlayer(p.tag)}
          className="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm text-left hover:bg-bg-card transition-colors">
          <span className="text-text-primary truncate">
            {p.recent && <span className="text-text-muted mr-1" title="Recently looked up">🕐</span>}
            {p.name ?? p.tag}
          </span>
          <span className="text-text-muted text-xs shrink-0">#{p.tag}</span>
        </button>
      ))}
    </>
  )

  return (
    <>
      {/* Mobile: tapping the icon expands the same search inline below the
          navbar rather than navigating anywhere. */}
      <button onClick={() => setMobileOpen(o => !o)} title="Search for a player"
        className="sm:hidden flex items-center justify-center w-8 h-8 rounded-lg shrink-0
                   text-text-secondary hover:text-text-primary hover:bg-bg-card transition-colors">
        <Search size={17} />
      </button>
      {mobileOpen && (
        <div className="sm:hidden fixed top-14 left-0 right-0 z-50 bg-bg-surface border-b border-border p-2 shadow-card">
          <div className="relative">
            <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted"/>
            <input autoFocus value={query} onChange={e => setQuery(e.target.value)}
              placeholder="Search a player name or #tag..."
              className="w-full bg-bg-card border border-border rounded-lg pl-8 pr-3 py-2 text-sm
                         text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent"
              onKeyDown={(e) => { if (e.key === 'Enter' && playerMatches.length > 0) goPlayer(playerMatches[0].tag) }} />
          </div>
          {playerMatches.length > 0 && (
            <div className="mt-2 max-h-[60vh] overflow-y-auto rounded-lg border border-border">{matchList}</div>
          )}
        </div>
      )}
      <div className="relative shrink-0 hidden sm:block">
        <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted"/>
        <input
          value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder="Search a player name or #tag..."
          className="bg-bg-card border border-border rounded-lg pl-8 pr-3 py-1.5 text-sm
                     text-text-primary placeholder:text-text-muted focus:outline-none
                     focus:border-accent w-48"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && playerMatches.length > 0) goPlayer(playerMatches[0].tag)
          }}
        />
        {open && playerMatches.length > 0 && (
          <div className="absolute top-full mt-1 left-0 right-0 bg-bg-surface border border-border rounded-lg
                          shadow-card overflow-hidden z-50 max-h-80 overflow-y-auto">
            {matchList}
          </div>
        )}
      </div>
    </>
  )
}

// Persistent, always-visible entry point to Favorites -- previously only
// reachable through Home's "More tools" collapsible (closed by default),
// which made saved decks hard to find again. A small badge shows how many
// are saved so the icon also doubles as quick confirmation a favorite stuck.
function FavoritesNavLink() {
  const favs = useFavoriteDecks()
  const count = Object.keys(favs).length
  return (
    <NavLink to="/favorites" title="Favorite Decks"
      className={({ isActive }) =>
        `relative flex items-center justify-center w-8 h-8 rounded-lg transition-colors shrink-0
        ${isActive ? 'bg-accent/20 text-accent' : 'text-text-secondary hover:text-gold hover:bg-bg-card'}`
      }>
      <Star size={17} fill={count > 0 ? 'currentColor' : 'none'} />
      {count > 0 && (
        <span className="absolute -top-1 -right-1 bg-gold text-bg-primary text-[9px] font-bold rounded-full min-w-[15px] h-[15px] flex items-center justify-center px-0.5">
          {count}
        </span>
      )}
    </NavLink>
  )
}

// Real account widget (2026-09-02) -- same small icon-button convention as
// FavoritesNavLink above. Logged out: a plain "Sign In" link to /account.
// Logged in: the same-sized button becomes a dropdown trigger (email +
// Log out) instead of navigating anywhere on click.
function AccountNavLink() {
  const { user, loading } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [open])

  if (loading) return <div className="w-8 h-8 shrink-0" />

  if (!user) {
    return (
      <NavLink to="/account" title="Sign In"
        className={({ isActive }) =>
          `relative flex items-center justify-center w-8 h-8 rounded-lg transition-colors shrink-0
          ${isActive ? 'bg-accent/20 text-accent' : 'text-text-secondary hover:text-accent hover:bg-bg-card'}`
        }>
        <LogIn size={17} />
      </NavLink>
    )
  }

  const initial = (user.email ?? '?')[0].toUpperCase()

  return (
    <div ref={ref} className="relative shrink-0">
      <button onClick={() => setOpen(o => !o)} title={user.email ?? 'Account'}
        className="flex items-center justify-center w-8 h-8 rounded-full bg-accent/20 text-accent text-xs font-bold
                   hover:bg-accent/30 transition-colors">
        {initial}
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-2 w-48 bg-bg-surface border border-border rounded-xl shadow-card p-2 z-50">
          <div className="px-2 py-1.5 text-xs text-text-muted truncate">{user.email}</div>
          <button onClick={async () => { setOpen(false); await supabase.auth.signOut() }}
            className="w-full flex items-center gap-2 text-left text-sm text-text-secondary hover:text-danger
                       hover:bg-bg-card rounded-lg px-2 py-2 transition-colors">
            <LogOut size={14} /> Log out
          </button>
        </div>
      )}
    </div>
  )
}

function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-bg-surface/95 backdrop-blur border-b border-border">
      <div className="max-w-7xl mx-auto px-2 sm:px-4 flex items-center h-14 gap-2 sm:gap-6">
        {/* Logo -- "Royale" in the game's own bold display lettering, "IQ" in
            a light-weight system font, same two-tier styling the old "Clash
            Royale" + "Pro" wordmark used (renamed 2026-08-14: this is a fan
            project, not an official Supercell product, so the product's own
            name shouldn't spell out the trademarked game name -- see the
            footer disclaimer below). */}
        <NavLink to="/" className="flex items-center gap-1 sm:gap-2 shrink-0">
          <span className="text-lg sm:text-xl">⚔️</span>
          <span className="flex items-baseline gap-1 sm:gap-1.5 leading-none">
            <span className="font-display text-gold text-base sm:text-lg tracking-wide" style={{ WebkitTextStroke: '0.5px rgba(0,0,0,0.4)' }}>
              Royale
            </span>
            {/* "IQ" dropped below sm: -- one more small, safe bit of room
                freed up in the mobile navbar (see PlayerSearch's comment for
                the full story on why this bar was overflowing). */}
            <span className="hidden sm:inline font-pro font-medium text-text-secondary text-base tracking-tight">IQ</span>
          </span>
        </NavLink>

        {/* Nav links -- icon-only below sm: (labels hidden, not removed) so
            the full bar (logo + 4 links + favorites + search) actually fits
            a real phone's 375px viewport instead of forcing horizontal
            scroll (confirmed via a real mobile-viewport Playwright sweep). */}
        <div className="flex items-center gap-0.5 sm:gap-1 flex-1 min-w-0">
          {NAV.map(({ to, icon, label }) => (
            <NavLink key={to} to={to} end={to === '/'} title={label}
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-2 sm:px-3 py-1.5 rounded-lg text-sm font-medium transition-colors
                ${isActive
                  ? 'bg-accent/20 text-accent'
                  : 'text-text-secondary hover:text-text-primary hover:bg-bg-card'}`
              }>
              {icon}<span className="hidden sm:inline">{label}</span>
            </NavLink>
          ))}
        </div>

        {/* MegaMenu retired 2026-08-20 (real feedback: "the megamenu is
            still cutting off... maybe get rid of this since we already have
            a megamenu wizard that helps user navigate"). It had two separate
            real overflow bugs on mobile: vertical (fixed earlier that
            session) and, it turns out, a second unrelated horizontal one --
            `right-0` + `w-[90vw]` anchored to this narrow mid-navbar button
            (not a screen corner) meant the panel's left edge could land well
            past the viewport's left edge whenever the button itself wasn't
            near the left side, cutting off every section label. The
            fixed-position replacement (originally FloatingNavBubble, now
            SideMenu -- see its own docstring, 2026-09-02) anchors to an
            actual screen edge instead of mid-bar, which is structurally why
            it never had this class of bug -- rather than patch a second
            brittle CSS position fix for a duplicated feature, retiring the
            redundant one. Component + import kept (not deleted) in case a
            future redesign wants a top-bar entry point again. */}
        {/* <MegaMenu /> */}
        <FavoritesNavLink />
        <AccountNavLink />
        <PlayerSearch />
      </div>
    </nav>
  )
}

// Minimal, deliberately quiet fallback -- lazy chunks are small and load
// fast on a real connection, so a full spinner/skeleton would mostly just
// flash annoyingly. This only shows at all on a slow connection or the
// very first navigation to a given route this session (Vite/React cache
// the chunk after that).
function RouteLoadingFallback() {
  return <div className="min-h-[40vh]" />
}

function AnimatedRoutes() {
  const location = useLocation()
  return (
    <AnimatePresence mode="wait">
      <Suspense fallback={<RouteLoadingFallback />}>
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<PageTransition><HomePage /></PageTransition>} />
        <Route path="/build" element={<PageTransition><DeckLabPage /></PageTransition>} />
        <Route path="/collection" element={<PageTransition><CollectionPage /></PageTransition>} />
        <Route path="/synergy" element={<PageTransition><SynergyPage /></PageTransition>} />
        <Route path="/player" element={<PageTransition><PlayerPage /></PageTransition>} />
        <Route path="/player/:tag" element={<PageTransition><PlayerPage /></PageTransition>} />
        <Route path="/analytics" element={<PageTransition><AnalyticsPage /></PageTransition>} />
        <Route path="/rankings" element={<PageTransition><RankingsPage /></PageTransition>} />
        <Route path="/clans" element={<PageTransition><ClanPage /></PageTransition>} />
        <Route path="/coach" element={<PageTransition><CoachingPage /></PageTransition>} />
        <Route path="/coach/:tag" element={<PageTransition><CoachingPage /></PageTransition>} />
        <Route path="/news" element={<PageTransition><WhatsNextPage /></PageTransition>} />
        <Route path="/favorites" element={<PageTransition><FavoritesPage /></PageTransition>} />
        <Route path="/account" element={<PageTransition><AuthPage /></PageTransition>} />
        <Route path="/reset-password" element={<PageTransition><ResetPasswordPage /></PageTransition>} />
        {/* Old routes redirect so existing bookmarks/links still work */}
        <Route path="/cards" element={<Navigate to="/build" replace />} />
        <Route path="/deck-lab" element={<Navigate to="/build" replace />} />
        <Route path="/deck-builder" element={<Navigate to="/build" replace />} />
        <Route path="/counters" element={<Navigate to="/build" replace />} />
        <Route path="/ml-lab" element={<Navigate to="/analytics" replace />} />
        <Route path="/meta" element={<Navigate to="/analytics" replace />} />
        <Route path="/whats-next" element={<Navigate to="/news" replace />} />
      </Routes>
      </Suspense>
    </AnimatePresence>
  )
}

// Required by Supercell's Fan Content Policy for a public fan site: a clear
// not-affiliated disclaimer + a link to the policy itself, on every page.
function Footer() {
  return (
    <footer className="relative z-10 border-t border-border mt-10 py-5 px-4 text-center">
      <p className="text-text-muted text-xs max-w-2xl mx-auto">
        Royale IQ is an unofficial fan-made project and is not affiliated with, endorsed, sponsored, or
        specifically approved by Supercell. Supercell is not responsible for this content. For more
        information see Supercell's{' '}
        <a href="https://supercell.com/en/fan-content-policy/" target="_blank" rel="noopener noreferrer"
          className="underline hover:text-text-secondary">
          Fan Content Policy
        </a>.
      </p>
    </footer>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {/* Real bug found 2026-08-21 via Playwright, affecting EVERY sticky
            element app-wide, not just one page: `overflow-x-hidden` here
            (added 2026-08-14 as a horizontal-scroll guard, see below) made
            the browser auto-compute `overflow-y: auto` on this div too --
            CSS spec forces the "visible" axis to behave as "auto" once the
            OTHER axis is anything but visible. That silently turned this
            shell div into a scroll container, and `position: sticky`
            resolves against the NEAREST scroll-container ancestor -- since
            this one never actually scrolls internally (the real page/
            document does), every sticky element in the app degraded to
            plain static-like flow instead of ever freezing in place.
            `overflow-x-clip` clips the same horizontal overflow (keeping
            the original 2026-08-14 guarantee intact) WITHOUT establishing a
            scroll container or forcing the other axis to auto -- confirmed
            via a live runtime override that switching this one property
            alone restored genuine sticky behavior instantly. */}
        <AuthProvider>
        <CardDetailProvider>
          <div className="min-h-screen bg-bg-primary text-text-primary font-sans flex flex-col overflow-x-clip">
            <Navbar />
            <main className="pt-14 relative z-10 flex-1">
              <AnimatedRoutes />
            </main>
            <Footer />
            {/* Mounted outside <AnimatedRoutes>/<Routes> so it never
                unmounts/remounts on client-side navigation -- stays put and
                keeps working across page changes, same reasoning as
                CardDetailProvider above. Replaced FloatingNavBubble
                2026-09-02 -- see SideMenu.tsx's own docstring. */}
            <SideMenu />
          </div>
        </CardDetailProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
