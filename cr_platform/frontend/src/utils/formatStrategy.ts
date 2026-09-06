const FLAVOR_LABELS: Record<string, string> = {
  cycle: 'Cycle',
  bait: 'Bait',
  spawner: 'Swarm',
  building_targeted_only: 'Building-Targeted',
}

/**
 * Reformats the real strategy label the backend's archetype_label() produces
 * (e.g. "Hog Rider (building_targeted_only, cycle)", grounded in the real
 * win-condition + flavor role tags -- see utils/counter_suggester.py) into a
 * more human-readable form ("Hog Rider · Cycle · Building-Targeted") for
 * DISPLAY ONLY. The raw value (used for filtering, <select> option values,
 * and API calls) is never touched -- pass the raw string in wherever it's
 * actually shown to a user, and pass the untouched original everywhere it's
 * compared/sent to the backend.
 */
export function formatStrategy(raw: string | null | undefined): string {
  if (!raw) return raw ?? ''
  const match = raw.match(/^(.+?)\s*\(([^)]*)\)\s*$/)
  if (!match) return raw // e.g. "No clear win condition", or a bare win-condition name with no flavor tags
  const [, primary, flavorsRaw] = match
  const flavors = flavorsRaw.split(',').map(f => f.trim()).filter(Boolean).map(f => FLAVOR_LABELS[f] ?? f)
  return flavors.length > 0 ? [primary, ...flavors].join(' · ') : primary
}
