import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Swords, TrendingUp, BarChart2, Sparkles, Trophy, Package, Share2, Star } from 'lucide-react'
import { whatsNextApi, metaApi } from '../utils/api'
import Backdrop from '../components/Backdrop'
import Collapsible from '../components/Collapsible'
import SeasonBadge from '../components/SeasonBadge'
import Tilt3D from '../components/Tilt3D'

// Banner art is the real card icon from the CDN Supercell's own public API
// already serves throughout this app (api-assets.clashroyale.com) -- the
// same asset used on every other card tile, not a separate marketing/promo
// image. No Supercell promotional artwork is embedded anywhere here.
function WhatsNextTeaser() {
  const navigate = useNavigate()
  const { data } = useQuery({ queryKey: ['whats-next'], queryFn: () => whatsNextApi.get() })

  const top = data?.entries?.[0]
  if (!top) return null

  // Compact single-line ticker, not a full feature card -- News is a
  // secondary "here's what's new" pointer, not a primary destination, so it
  // shouldn't compete with the actual feature tiles for vertical space.
  return (
    <motion.button
      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
      onClick={() => navigate('/news')}
      className="w-full max-w-2xl mx-auto mb-3 flex items-center gap-2 rounded-full border border-gold/30
                 hover:border-gold/60 bg-bg-surface/60 px-4 py-1.5 transition-colors group text-left">
      <Sparkles size={13} className="text-gold shrink-0" />
      <span className="text-[10px] uppercase tracking-wide text-gold font-bold shrink-0">News</span>
      <span className="text-xs text-text-secondary truncate flex-1">{top.title}</span>
      <span className="shrink-0 text-[11px] text-cyan-300 group-hover:translate-x-0.5 transition-transform">See all →</span>
    </motion.button>
  )
}

// Real per-card win rate, straight from live-collected battles (same source
// as Analytics' Meta Trends tab). Real feedback (2026-08-22): this used to
// be a whole card headed by the current season's stale announcement title
// ("Season 86 'K.H.A.O.S' begins August 3" -- old news by the time anyone's
// looking at it) with a balance-change blurb and a 2-column Overperforming/
// Dominating split (10 cards total) -- "too much useless info... Top card
// right now only." Collapsed down to a single slim pill matching the News
// ticker right above it (same visual weight, not a bigger competing card) --
// just the one real #1 card by win rate, click-through to Analytics for more.
function TopCardTeaser() {
  const navigate = useNavigate()
  const { data: topWinRate } = useQuery({ queryKey: ['meta-highlight-winrate'], queryFn: () => metaApi.topCards('win_rate', 1) })
  const top = topWinRate?.cards?.[0]
  if (!top) return null

  return (
    <motion.button
      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
      onClick={() => navigate('/analytics?tab=meta')}
      className="w-full max-w-2xl mx-auto mb-3 flex items-center gap-2 rounded-full border border-cyan-400/30
                 hover:border-cyan-400/60 bg-bg-surface/60 px-4 py-1.5 transition-colors group text-left">
      <span className="text-sm shrink-0">🔥</span>
      <span className="text-[10px] uppercase tracking-wide text-cyan-300 font-bold shrink-0">Top Card</span>
      <span className="text-xs text-text-secondary truncate flex-1">{top.name} -- {top.win_rate}% real win rate</span>
      <span className="shrink-0 text-[11px] text-cyan-300 group-hover:translate-x-0.5 transition-transform">See more →</span>
    </motion.button>
  )
}

const HOW_IT_WORKS = [
  { term: '📊 Top Decks', def: 'Real decks other players have actually used, ranked by how often they were played and how often they won -- not a hand-picked "meta tier list".' },
  { term: '🔗 Synergy', def: "Which cards tend to perform better when played together, based on how those pairings have actually done in collected battles." },
  { term: '🤖 Win Predictor', def: 'A model trained on real match outcomes that estimates a deck\'s win rate from its card composition -- most useful for brand-new decks that don\'t have enough real games of their own yet.' },
]

function HowThisWorks() {
  return (
    <div className="w-full max-w-2xl mx-auto text-left mb-4">
      <Collapsible title="ℹ️ How this app works">
        <p className="text-text-secondary text-xs mb-3">
          Everything here is built from real, live-collected Clash Royale battles -- not a static snapshot and not
          hand-curated opinions. Here's what the main tools actually mean:
        </p>
        <div className="space-y-2">
          {HOW_IT_WORKS.map(t => (
            <div key={t.term}>
              <span className="text-xs font-semibold text-accent">{t.term}: </span>
              <span className="text-xs text-text-secondary">{t.def}</span>
            </div>
          ))}
        </div>
      </Collapsible>
    </div>
  )
}

// Was p-5 with a w-14 icon and always-visible description at every size --
// fine on desktop, but with the grid forced to 1-per-row below `md:` (see
// primaryTiles below), 3 of these stacked full-width and padded generously
// was most of "why do i have to scroll so much just to go from build to
// ranking." Now compact on mobile (smaller padding/icon, description
// dropped -- the title alone is enough to navigate) and the original full
// size from `sm:` up.
// Real CSS-only 3D tilt (2026-09-07, "futuristic 3D" pass) replaces the old
// flat whileHover={{y,scale}} lift -- Tilt3D's mouse-tracked perspective
// tilt is the same proven, cheap (no 3D library) technique already used on
// CardDetailModal's focal card and the Synergy Network graph, now applied
// to the app's actual front door. whileTap kept for the press-down feel
// tilt alone doesn't give.
function MenuTile({ icon, title, desc, onClick }: { icon: React.ReactNode; title: string; desc: string; onClick: () => void }) {
  return (
    <Tilt3D maxTilt={10} scale={1.04} glare className="w-full">
      <motion.button onClick={onClick} whileTap={{ scale: 0.96 }}
        className="bg-bg-surface border border-border rounded-2xl p-3 sm:p-5 text-left
                   hover:border-gold hover:shadow-glow transition-colors group w-full overflow-hidden">
        <div className="w-9 h-9 sm:w-14 sm:h-14 rounded-xl sm:rounded-2xl mb-1.5 sm:mb-3 flex items-center justify-center
                         bg-gold/15 border border-gold/30 text-gold group-hover:scale-110 group-hover:bg-gold/25 transition-all"
          style={{ transform: 'translateZ(20px)' }}>
          {icon}
        </div>
        <div className="font-semibold text-white text-sm sm:text-lg sm:mb-1" style={{ transform: 'translateZ(12px)' }}>{title}</div>
        <div className="hidden sm:block text-text-secondary text-sm">{desc}</div>
      </motion.button>
    </Tilt3D>
  )
}

export default function HomePage() {
  const navigate = useNavigate()

  // size={22} looks right in both the mobile-compact (w-9) and desktop
  // (w-14) icon box -- see MenuTile's comment on why the box itself now
  // scales responsively instead of these tiles stacking full-width and tall.
  const primaryTiles = [
    { icon: <Swords size={22}/>, title: 'Build', desc: 'Browse cards, build decks, find counters', href: '/build' },
    { icon: <TrendingUp size={22}/>, title: 'Analytics', desc: 'Live meta, top decks, win predictor', href: '/analytics' },
    { icon: <Trophy size={22}/>, title: 'Rankings', desc: 'Real Supercell leaderboards', href: '/rankings' },
  ]
  const secondaryTiles = [
    { icon: <Package size={22}/>, title: 'Collection', desc: 'Your real card levels', href: '/collection' },
    { icon: <Share2 size={22}/>, title: 'Synergy', desc: 'Which cards pair well, from real battles', href: '/synergy' },
    { icon: <Star size={22}/>, title: 'Favorites', desc: 'Decks you\'ve starred across the app', href: '/favorites' },
  ]

  return (
    <div className="relative z-10 min-h-[calc(100vh-56px)] flex flex-col overflow-hidden">
      <Backdrop density={18} />
      {/* Real depth cue behind the hero -- two large, softly-blurred glow
          orbs (gold + royale-blue, the app's own existing brand tokens, not
          new colors) drifting slowly at different rates. Pure CSS
          (radial-gradient + the driftSlow keyframe), so this is free
          performance-wise -- no canvas/WebGL, matching "very fast rendering". */}
      <div className="absolute inset-0 pointer-events-none" aria-hidden>
        <div className="absolute -top-24 left-1/4 w-[32rem] h-[32rem] rounded-full opacity-20 blur-[100px] animate-drift-slow"
          style={{ background: 'radial-gradient(circle, #D4AF37, transparent 70%)' }} />
        <div className="absolute top-1/3 right-1/4 w-[28rem] h-[28rem] rounded-full opacity-[0.15] blur-[100px] animate-drift-slow"
          style={{ background: 'radial-gradient(circle, #4A6FE0, transparent 70%)', animationDelay: '-7s' }} />
      </div>
      {/* Hero */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-16 text-center">
        <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="w-full">
          <div className="text-6xl mb-4">⚔️</div>
          <h1 className="flex items-baseline justify-center gap-3 mb-3 flex-wrap">
            {/* Slow gold shimmer sweep across the wordmark -- a moving
                gradient clipped to the text, not a new color, just motion
                on the existing gold. Respects reduced-motion via the plain
                gold fallback color underneath the gradient layer. */}
            <span
              className="font-display text-4xl md:text-5xl tracking-wide bg-clip-text text-transparent animate-shimmer motion-reduce:animate-none motion-reduce:text-gold"
              style={{
                WebkitTextStroke: '1px rgba(0,0,0,0.4)',
                backgroundImage: 'linear-gradient(90deg, #B8952C 0%, #D4AF37 25%, #F5DA81 50%, #D4AF37 75%, #B8952C 100%)',
                backgroundSize: '200% 100%',
              }}
            >
              Royale
            </span>
            <span className="font-pro font-medium text-3xl md:text-4xl text-text-secondary tracking-tight">IQ</span>
          </h1>
          <p className="text-text-secondary text-lg mb-2 w-full max-w-md mx-auto">
            Real-time Clash Royale stats, deck coaching, card analytics, and meta tracking.
          </p>
          <SeasonBadge className="mb-6" />

          {/* Real feedback (2026-08-26): "Remove player tag search bar for
              all features inside the app and add a universal search bar for
              it" -- the dedicated player search box that used to live here
              is gone; App.tsx's CardSearch (top nav, on every page) is now
              the one place to look up a player. */}
          <p className="text-text-muted text-sm mb-10">
            🔍 Use the search bar at the top of the page to look up a player.
          </p>

          <WhatsNextTeaser />
          <TopCardTeaser />

          {/* Primary menu tiles -- everything else in the app is reached from here.
              Was grid-cols-1 below md: (stacking Build/Analytics/Rankings into 3 tall
              full-width rows) -- real complaint: "too big why do i have to scroll so
              much just to go from build to ranking." Always 3-across now; MenuTile's
              own responsive padding/icon-size keeps each tile from feeling cramped. */}
          <div className="grid grid-cols-3 gap-2 sm:gap-4 w-full max-w-2xl mx-auto mb-4">
            {primaryTiles.map(({ icon, title, desc, href }) => (
              <MenuTile key={title} icon={icon} title={title} desc={desc} onClick={() => navigate(href)} />
            ))}
          </div>

          <HowThisWorks />

          <div className="w-full max-w-2xl mx-auto text-left">
            <Collapsible title="More tools">
              <div className="grid grid-cols-3 gap-2 sm:gap-3">
                {secondaryTiles.map(({ icon, title, desc, href }) => (
                  <MenuTile key={title} icon={icon} title={title} desc={desc} onClick={() => navigate(href)} />
                ))}
              </div>
            </Collapsible>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
