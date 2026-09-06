/**
 * Every real destination in the app, reachable in one tap from anywhere via
 * the side "More" menu (components/SideMenu.tsx), visible even deep-scrolled
 * into a long page.
 *
 * REWORKED 2026-09-02 (real feedback): "make more a side swipeable menu bar,
 * remove the navigation bubble, and add every feature in the more swipeable
 * menu bar." This list used to deliberately exclude whatever already had a
 * permanent top-navbar icon (Home/Player/Coach/News) and Collection/
 * Favorites (reached as sub-links elsewhere) -- the whole point of THIS menu
 * now is to be the one single place that lists literally everything, so
 * those are back in even though a couple of them are also one tap away in
 * the top bar. Sub-tabs (Analytics' 6 tabs, etc.) still stay OUT of this
 * list -- each of those pages already has its own in-page tab bar for that,
 * unchanged reasoning from before.
 */
export const NAV_SECTIONS: { label: string; href: string; icon: string }[] = [
  { label: 'Home', href: '/', icon: '🏠' },
  { label: 'Player', href: '/player', icon: '👤' },
  { label: 'Coach', href: '/coach', icon: '🎓' },
  { label: 'News', href: '/news', icon: '📰' },
  { label: 'Build', href: '/build', icon: '🛠' },
  { label: 'Collection', href: '/collection', icon: '📦' },
  { label: 'Analytics', href: '/analytics', icon: '📊' },
  { label: 'Rankings', href: '/rankings', icon: '🏆' },
  { label: 'Clans', href: '/clans', icon: '🏰' },
  { label: 'Synergy', href: '/synergy', icon: '🕸️' },
  { label: 'Favorites', href: '/favorites', icon: '⭐' },
  { label: 'Account', href: '/account', icon: '🔐' },
]
