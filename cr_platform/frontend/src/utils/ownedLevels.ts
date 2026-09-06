import { useEffect, useState } from 'react'

/**
 * Real owned card levels + connected-player sync, extracted out of
 * CollectionPage so the SAME real levels/sync/manual-edit system can back
 * every deck builder in the app (Build, Synergy's Deck Network, ...)
 * instead of Build using its own thinner, disconnected `useEditableLevels`.
 * Real feedback (2026-08-23): "Build and collection don't have to be two
 * separate tabs... apply all the logic and features and make it one really
 * good deck builder with your own card levels and sync/unsync."
 */
const STORAGE_KEY = 'cr_collection_levels'
const CONNECTED_KEY = 'cr_connected_collection'
const APPLIED_TAG_KEY = 'cr_collection_applied_tag'
const MANUAL_OVERRIDE_KEY = 'cr_collection_manual_override'

function loadStored(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')
  } catch {
    return {}
  }
}

function loadConnected(): { player: string; tag: string; levels: Record<string, number>; counts?: Record<string, number> } | null {
  try {
    const raw = localStorage.getItem(CONNECTED_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function useOwnedLevels(cards: { name: string }[]) {
  const [levels, setLevels] = useState<Record<string, number>>({})
  const [connectedInfo, setConnectedInfo] = useState<{ player: string; tag: string } | null>(null)
  const [manualOverride, setManualOverride] = useState(() => localStorage.getItem(MANUAL_OVERRIDE_KEY) === '1')
  // Real owned copy count per card -- real feedback (2026-08-27): "the
  // collections should include the number of upgrades on the card like
  // 100/1000." Unlike levels, this is read-only real data (no manual-edit
  // concept makes sense for "how many copies do you own") -- just mirrors
  // whatever the connected player's real collection reports, empty when
  // nothing is connected.
  const [counts, setCounts] = useState<Record<string, number>>({})

  const syncFromConnected = () => {
    const connected = loadConnected()
    const alreadyApplied = localStorage.getItem(APPLIED_TAG_KEY)
    if (connected && connected.tag !== alreadyApplied) {
      setLevels(prev => {
        const merged = { ...prev, ...connected.levels }
        localStorage.setItem(STORAGE_KEY, JSON.stringify(merged))
        return merged
      })
      localStorage.setItem(APPLIED_TAG_KEY, connected.tag)
    }
    setConnectedInfo(connected ? { player: connected.player, tag: connected.tag } : null)
    setCounts(connected?.counts ?? {})
  }

  useEffect(() => {
    setLevels(prev => {
      const stored = loadStored()
      const merged = { ...prev }
      for (const c of cards) if (!(c.name in merged)) merged[c.name] = stored[c.name] ?? 11
      return merged
    })
    syncFromConnected()
    window.addEventListener('focus', syncFromConnected)
    window.addEventListener('storage', syncFromConnected)
    return () => {
      window.removeEventListener('focus', syncFromConnected)
      window.removeEventListener('storage', syncFromConnected)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cards.length])

  const persist = (next: Record<string, number>) => {
    setLevels(next)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  }

  const reapplyConnected = () => {
    const connected = loadConnected()
    if (!connected) return
    persist({ ...levels, ...connected.levels })
    localStorage.setItem(APPLIED_TAG_KEY, connected.tag)
    setConnectedInfo({ player: connected.player, tag: connected.tag })
    setCounts(connected.counts ?? {})
  }

  const unsync = () => { localStorage.setItem(MANUAL_OVERRIDE_KEY, '1'); setManualOverride(true) }
  const resync = () => {
    localStorage.removeItem(MANUAL_OVERRIDE_KEY)
    setManualOverride(false)
    reapplyConnected()
  }

  const setAll = (value: number) => persist(Object.fromEntries(cards.map(c => [c.name, value])))
  const setLevel = (name: string, value: number) => persist({ ...levels, [name]: value })
  const bumpLevel = (name: string, delta: number) =>
    setLevel(name, Math.max(0, Math.min(18, (levels[name] ?? 11) + delta)))

  return { levels, setLevel, bumpLevel, setAll, connectedInfo, manualOverride, unsync, resync, reapplyConnected, counts }
}
