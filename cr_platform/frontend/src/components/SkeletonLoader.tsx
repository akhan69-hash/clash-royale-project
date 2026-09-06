import { useState } from 'react'

// Real feedback (2026-09-02): "dancing two skeletons as loading buffer for
// render or searches around the app." A more playful alternative to
// LoadingSpinner's elixir droplet for the app's heavier, longer waits (a
// full player lookup, not a small inline fetch) -- two plain skull glyphs
// (not Supercell's actual Skeletons-troop art, which is licensed game
// content this fan project shouldn't reproduce) bouncing out of phase with
// each other reads as a little dance, a real nod to the in-game Skeletons
// card's own idle animation without copying any real asset.
const FLAVOR_LINES = [
  'Brewing elixir...',
  'Scouting the arena...',
  'Deploying troops...',
  'Charging the King Tower...',
  'Reading the battle log...',
  'Summoning skeletons...',
]

export default function SkeletonLoader({ label }: { label?: string }) {
  const [line] = useState(() => FLAVOR_LINES[Math.floor(Math.random() * FLAVOR_LINES.length)])
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12">
      <div className="flex gap-3 text-4xl" aria-hidden>
        <span className="inline-block animate-bounce" style={{ animationDelay: '0ms' }}>💀</span>
        <span className="inline-block animate-bounce" style={{ animationDelay: '250ms' }}>💀</span>
      </div>
      <div className="text-text-secondary text-sm">{label ?? line}</div>
    </div>
  )
}
