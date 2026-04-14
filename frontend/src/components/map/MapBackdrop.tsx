/* ── Orb dimensions (px) ─────────────────────── */
const HERO_W = 800
const HERO_H = 500
const HIGHLIGHT_W = 450
const HIGHLIGHT_H = 350
const CONIC_SIZE = 400
const BOTTOM_W = 400
const BOTTOM_H = 300

interface MapBackdropProps {
  isNarrow: boolean
  prefersReducedMotion: boolean
}

/**
 * Decorative ambient orbs for the map page.
 * Teal/cyan palette — mirrors ActivityBackdrop pattern.
 */
export function MapBackdrop({ isNarrow, prefersReducedMotion }: MapBackdropProps) {
  return (
    <div
      className="pointer-events-none absolute inset-0 -z-1 overflow-hidden"
      aria-hidden="true"
    >
      {/* Primary hero orb — top center (teal glow) */}
      <div
        className="absolute -top-20 left-1/2 max-w-full -translate-x-1/2"
        style={{
          width: HERO_W,
          height: HERO_H,
          background:
            "radial-gradient(ellipse at 50% 0%, var(--map-hero-orb), transparent 72%)",
          filter: "blur(40px)",
        }}
      />

      {/* Secondary highlight — top right (cyan accent) */}
      {!isNarrow && (
        <div
          className="absolute -top-10 right-0"
          style={{
            width: HIGHLIGHT_W,
            height: HIGHLIGHT_H,
            background:
              "radial-gradient(ellipse at 80% 10%, var(--map-hero-highlight), transparent 60%)",
            filter: "blur(50px)",
          }}
        />
      )}

      {/* Drifting conic gradient (desktop only, respect reduced motion) */}
      {!isNarrow && !prefersReducedMotion && (
        <div
          className="absolute left-1/4 top-10 opacity-60"
          style={{
            width: CONIC_SIZE,
            height: CONIC_SIZE,
            background: "var(--grad-map-conic)",
            filter: "blur(60px)",
            animation: "orb-drift 40s ease-in-out infinite alternate",
          }}
        />
      )}

      {/* Third orb — bottom left (subtle teal) */}
      <div
        className="absolute bottom-0 left-0"
        style={{
          width: BOTTOM_W,
          height: BOTTOM_H,
          background:
            "radial-gradient(ellipse at 20% 80%, var(--map-orb-3), transparent 65%)",
          filter: "blur(50px)",
        }}
      />
    </div>
  )
}
