import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { cardsApi, Card } from '../utils/api'
import { RARITY_COLORS } from './CardImage'

/**
 * Decorative, game-like background: real card icons (same CDN art used
 * everywhere else in the app -- no separate promotional/marketing image)
 * floating as soft circular "bubbles" that drift slowly and gently react to
 * cursor proximity (a small repel offset). Always pointer-events-none and
 * behind content (z-0) so it never interferes with clicking anything.
 */
interface Bubble {
  id: number
  name: string
  image: string | null
  rarityColor: string
  x: number   // vw
  y: number   // vh
  size: number // px
  driftDelay: number
  driftDuration: number
}

export default function Backdrop({ density = 14 }: { density?: number }) {
  const { data } = useQuery({ queryKey: ['cards'], queryFn: () => cardsApi.getAll() })
  const containerRef = useRef<HTMLDivElement>(null)
  const [mouse, setMouse] = useState<{ x: number; y: number } | null>(null)

  const bubbles: Bubble[] = useMemo(() => {
    const pool = (data?.items ?? []).filter((c: Card) => !!c.image_url)
    if (pool.length === 0) return []
    // Deterministic pseudo-random spread so bubbles don't reshuffle on every render.
    let seed = 42
    const rand = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280 }
    return Array.from({ length: density }).map((_, i) => {
      const card = pool[Math.floor(rand() * pool.length)]
      return {
        id: i,
        name: card.name,
        image: card.image_url,
        rarityColor: RARITY_COLORS[card.rarity] ?? '#D4AF37',
        x: rand() * 100,
        y: rand() * 100,
        size: 60 + rand() * 90,
        driftDelay: rand() * 6,
        driftDuration: 10 + rand() * 10,
      }
    })
  }, [data, density])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      setMouse({ x: ((e.clientX - rect.left) / rect.width) * 100, y: ((e.clientY - rect.top) / rect.height) * 100 })
    }
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  return (
    <div ref={containerRef} className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      {bubbles.map(b => {
        let offsetX = 0
        let offsetY = 0
        if (mouse) {
          const dx = b.x - mouse.x
          const dy = b.y - mouse.y
          const dist = Math.sqrt(dx * dx + dy * dy)
          const repelRadius = 18 // vw/vh units
          if (dist < repelRadius && dist > 0.01) {
            const strength = (1 - dist / repelRadius) * 6
            offsetX = (dx / dist) * strength
            offsetY = (dy / dist) * strength
          }
        }
        return (
          <div
            key={b.id}
            className="absolute rounded-full opacity-[0.12] transition-transform duration-500 ease-out animate-[float_10s_ease-in-out_infinite]"
            style={{
              left: `${b.x + offsetX}%`,
              top: `${b.y + offsetY}%`,
              width: b.size,
              height: b.size,
              animationDelay: `${b.driftDelay}s`,
              animationDuration: `${b.driftDuration}s`,
              filter: `drop-shadow(0 0 ${b.size * 0.15}px ${b.rarityColor}aa)`,
            }}
          >
            <img src={b.image ?? undefined} alt="" className="w-full h-full object-contain" draggable={false} />
          </div>
        )
      })}
    </div>
  )
}
