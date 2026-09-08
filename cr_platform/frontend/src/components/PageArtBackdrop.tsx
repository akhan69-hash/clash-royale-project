/**
 * Per-page "own identity and art" backdrop (2026-09-07, new-season theme
 * integration + "every feature will have its own identity and art and font"
 * pass) -- large, heavily blurred real card art glowing at the two page
 * edges, tinted with a distinct accent color THIS page owns. Real CDN art
 * (the same image_url every card tile in the app already renders, e.g. a
 * new-season card like Minion Giant) is what's blurred here -- no separate
 * custom illustration, matching Backdrop.tsx's existing "real card art, not
 * marketing art" convention. Every page that mounts one picks its own
 * imageUrl + accent so Player/Coach/etc. each read as their own identity
 * instead of one uniform look. Same fixed/z-0/pointer-events-none contract
 * as Backdrop.tsx -- the two compose (Backdrop's small drifting bubbles plus
 * this page's two big signature art pieces), never affects layout or
 * interaction.
 */
export default function PageArtBackdrop({ imageUrl, accent }: { imageUrl?: string | null; accent: string }) {
  if (!imageUrl) return null
  return (
    <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden" aria-hidden>
      <div className="absolute -left-16 top-[15%] w-64 h-64 sm:w-[26rem] sm:h-[26rem] opacity-[0.16] animate-drift-slow"
        style={{ filter: `blur(36px) drop-shadow(0 0 70px ${accent})` }}>
        <img src={imageUrl} alt="" className="w-full h-full object-contain" draggable={false} />
      </div>
      <div className="absolute -right-16 bottom-[10%] w-64 h-64 sm:w-[26rem] sm:h-[26rem] opacity-[0.14] animate-drift-slow"
        style={{ filter: `blur(36px) drop-shadow(0 0 70px ${accent})`, animationDelay: '-7s' }}>
        <img src={imageUrl} alt="" className="w-full h-full object-contain scale-x-[-1]" draggable={false} />
      </div>
    </div>
  )
}
