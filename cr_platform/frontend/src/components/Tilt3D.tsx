import { useRef, useState, ReactNode } from 'react'

/**
 * Shared CSS-only 3D tilt wrapper (2026-09-07) -- the same real
 * mouse-tracked perspective tilt already proven on CardDetailModal's focal
 * card and the Synergy Network graph, now factored out into one component
 * instead of a third copy-pasted implementation, so it can be applied
 * consistently across the app (real feedback: "build a very futuristic 3d
 * esk frontend... very fast rendering and loading" -- CSS transforms are
 * effectively free performance-wise, no 3D engine/library needed).
 *
 * `maxTilt` controls intensity (degrees); `scale` is how much it grows on
 * hover-tilt (1 = no scale change); `glare` adds a moving specular
 * highlight like a glossy card catching light.
 */
export default function Tilt3D({
  children, maxTilt = 12, scale = 1.02, glare = false, className = '',
}: {
  children: ReactNode
  maxTilt?: number
  scale?: number
  glare?: boolean
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [tilt, setTilt] = useState({ rx: 0, ry: 0 })
  const [active, setActive] = useState(false)

  const onMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = ref.current?.getBoundingClientRect()
    if (!rect) return
    const px = (e.clientX - rect.left) / rect.width - 0.5
    const py = (e.clientY - rect.top) / rect.height - 0.5
    setTilt({ rx: py * -maxTilt, ry: px * maxTilt })
  }
  const onLeave = () => { setTilt({ rx: 0, ry: 0 }); setActive(false) }

  return (
    <div style={{ perspective: 700 }} className={className}>
      <div
        ref={ref}
        onMouseMove={onMove}
        onMouseEnter={() => setActive(true)}
        onMouseLeave={onLeave}
        className="relative transition-transform duration-150 ease-out"
        style={{
          transform: `rotateX(${tilt.rx}deg) rotateY(${tilt.ry}deg) scale(${active ? scale : 1})`,
          transformStyle: 'preserve-3d',
        }}
      >
        {children}
        {glare && (
          <div className="absolute inset-0 pointer-events-none rounded-[inherit]"
            style={{
              background: `radial-gradient(circle at ${50 - tilt.ry * 2}% ${50 + tilt.rx * 2}%, rgba(255,255,255,0.14), transparent 55%)`,
            }} />
        )}
      </div>
    </div>
  )
}
