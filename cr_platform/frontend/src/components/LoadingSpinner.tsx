import { useState } from 'react'

// Real feedback (2026-08-21): "A clash royale related loading rather than a
// hang between loading stuff" -- plain "Loading player data..." text with no
// animation reads as a stall, not progress. A small spinning elixir droplet
// (same teardrop shape/gradient already used for the elixir-cost badge on
// every CardImage, so it's a consistent motif, not a new asset) plus a
// rotating flavor line reads as "something's happening" instead.
const FLAVOR_LINES = [
  'Brewing elixir...',
  'Scouting the arena...',
  'Deploying troops...',
  'Charging the King Tower...',
  'Reading the battle log...',
]

export default function LoadingSpinner({ label }: { label?: string }) {
  const [line] = useState(() => FLAVOR_LINES[Math.floor(Math.random() * FLAVOR_LINES.length)])
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12">
      <div className="w-8 h-8 rounded-[50%_50%_50%_0] rotate-45 shadow animate-spin"
        style={{ background: 'radial-gradient(circle at 35% 30%, #C77DFF, #7B2FBE 60%, #5A1F94)', animationDuration: '1s' }} />
      <div className="text-text-secondary text-sm">{label ?? line}</div>
    </div>
  )
}
