import { useSearchParams } from 'react-router-dom'

/**
 * Shared "which sub-tab is active" state that lives in the URL (`?tab=...`)
 * instead of only local component state -- makes every tabbed page
 * (Analytics, Synergy, Rankings, Build) deep-linkable, so the MegaMenu (and
 * anyone sharing a link) can land directly on e.g. "Top Decks" instead of
 * always landing on the first tab and requiring another click. Extracted
 * from DeckLabPage's pre-existing ad-hoc `searchParams.get('q')` check,
 * generalized to any tab set.
 */
export function useTabParam<T extends string>(defaultTab: T): [T, (t: T) => void] {
  const [searchParams, setSearchParams] = useSearchParams()
  const raw = searchParams.get('tab')
  const tab = (raw as T) || defaultTab

  const setTab = (t: T) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      next.set('tab', t)
      return next
    }, { replace: true })
  }

  return [tab, setTab]
}
