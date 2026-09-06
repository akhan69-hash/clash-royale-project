/**
 * The real Clash Royale API's own timestamp format ("20260905T163000.000Z")
 * is NOT valid ISO 8601 -- `new Date()` silently fails to parse it (no
 * dashes/colons) -- so every real timestamp field the API returns
 * (lastSeen, battleTime, ...) needs this before it can be used. Added
 * 2026-09-02 for the Clan tab's member "last active" display -- originally
 * built for a River Race war-end countdown, but the live
 * /clans/{tag}/currentriverrace response turned out to have no
 * warEndTime/collectionEndTime field at all (confirmed against the real
 * API, not just docs), so that specific use was dropped -- see the comment
 * on ClanDetail in RankingsPage.tsx.
 */
export function parseCrTimestamp(ts?: string | null): Date | null {
  if (!ts) return null
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(?:\.(\d{3}))?Z?$/.exec(ts)
  if (!m) return null
  const [, y, mo, d, h, mi, s, ms] = m
  return new Date(Date.UTC(+y, +mo - 1, +d, +h, +mi, +s, ms ? +ms : 0))
}

/** Whole days remaining until a real CR API timestamp, or null if the
 * timestamp is missing/unparseable. Never negative -- a timestamp in the
 * past reads as "ends today" (0), not a negative countdown. */
export function daysUntil(ts?: string | null): number | null {
  const date = parseCrTimestamp(ts)
  if (!date) return null
  return Math.max(0, Math.ceil((date.getTime() - Date.now()) / 86400000))
}
