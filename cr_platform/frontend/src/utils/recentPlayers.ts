/**
 * Real "remembered" player tags for THIS browser -- real feedback
 * (2026-08-26): "remembering playertags and suggestions on the load, needs
 * great work done on it it is very weird right now." The old behavior had
 * nothing that actually remembered a tag between visits; every suggestion
 * came from the SERVER's global (any-player-ever-seen) index, which is
 * empty for a brand new visitor and unranked besides. This tracks the small
 * number of tags YOU'VE actually looked up recently, most-recent-first, so
 * the universal search bar can suggest them immediately on focus -- before
 * typing anything, and without depending on server data at all.
 */
const KEY = 'cr_recent_player_tags'
const MAX_RECENT = 5

export interface RecentPlayer {
  tag: string
  name: string | null
  at: string
}

export function getRecentPlayers(): RecentPlayer[] {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export function addRecentPlayer(tag: string, name: string | null = null) {
  const clean = tag.trim().toUpperCase().replace(/^#/, '')
  if (!clean) return
  const existing = getRecentPlayers().filter(p => p.tag !== clean)
  const next = [{ tag: clean, name, at: new Date().toISOString() }, ...existing].slice(0, MAX_RECENT)
  localStorage.setItem(KEY, JSON.stringify(next))
  // A fresh real lookup means the user wants a default tag remembered again
  // -- clears any earlier "forget it" choice (see forgetDefaultPlayerTag).
  localStorage.removeItem(FORGET_KEY)
}

/**
 * Real feedback (2026-08-27): "if i go back to the player page, it should
 * remember the player tag i was searching unless i remove it." The most
 * recently looked-up tag (already tracked above) doubles as "the" default --
 * no separate storage needed -- unless the user explicitly asked to forget
 * it (see forgetDefaultPlayerTag), in which case landing on a bare /player
 * should show the generic NoPlayerYet state instead of auto-redirecting.
 */
const FORGET_KEY = 'cr_player_tag_forgotten'

export function getDefaultPlayerTag(): string | null {
  if (localStorage.getItem(FORGET_KEY) === '1') return null
  return getRecentPlayers()[0]?.tag ?? null
}

export function forgetDefaultPlayerTag() {
  localStorage.setItem(FORGET_KEY, '1')
}
