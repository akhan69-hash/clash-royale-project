/**
 * A stable per-browser session id, generated once and persisted to
 * localStorage -- survives client-side page navigation AND full page
 * reloads within the same browser (deliberately not reset per-page or per-
 * tab-close, per the "don't stop the session once the user changes pages"
 * requirement). Attached to every API request (see utils/api.ts's request
 * interceptor) so the backend's activity log (main.py's logging middleware
 * -> data/activity_log.jsonl) can group a visitor's requests together
 * across their whole visit, not just per-request. Foundation only -- no
 * behavior reads this yet beyond the log itself; a future AI-assisted
 * navigation feature is the intended consumer, not built yet.
 */
const SESSION_ID_KEY = 'cr_session_id'
const CONNECTED_KEY = 'cr_connected_collection'

export function getSessionId(): string {
  let id = localStorage.getItem(SESSION_ID_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(SESSION_ID_KEY, id)
  }
  return id
}

/** The player tag most recently connected via Player Lookup, if any --
 * reuses the same localStorage record PlayerPage already writes
 * (cr_connected_collection) rather than tracking a second copy of it. */
export function getKnownPlayerTag(): string | null {
  try {
    const raw = localStorage.getItem(CONNECTED_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed?.tag ?? null
  } catch {
    return null
  }
}
