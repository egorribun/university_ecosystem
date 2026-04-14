/**
 * EventsBackdrop — decorative ambient gradient layer.
 * Warm-toned orbs (amber/rose) to differentiate from News (sky/indigo).
 * Pattern source: components/news/NewsBackdrop.tsx
 */

interface EventsBackdropProps {
  isNarrow?: boolean
  prefersReducedMotion?: boolean
}

export function EventsBackdrop({
  isNarrow = false,
  prefersReducedMotion = false,
}: EventsBackdropProps) {
  return (
    <div
      className="pointer-events-none absolute inset-0 overflow-hidden -z-1"
      aria-hidden="true"
    >
      {/* Primary hero glow — amber */}
      <div
        className="absolute rounded-full opacity-60"
        style={{
          width: isNarrow ? "100%" : "85%",
          height: isNarrow ? "45%" : "55%",
          top: "-10%",
          left: "50%",
          transform: "translateX(-50%)",
          background: "radial-gradient(ellipse at center, var(--events-hero-orb), transparent 70%)",
          filter: prefersReducedMotion ? "none" : "blur(40px)",
        }}
      />

      {/* Secondary highlight — rose */}
      <div
        className="absolute rounded-full opacity-40"
        style={{
          width: isNarrow ? "60%" : "50%",
          height: isNarrow ? "30%" : "35%",
          top: "5%",
          right: "-5%",
          background:
            "radial-gradient(ellipse at center, var(--events-hero-highlight), transparent 70%)",
          filter: prefersReducedMotion ? "none" : "blur(60px)",
        }}
      />

      {/* Tertiary accent — warm glow */}
      <div
        className="absolute rounded-full opacity-30"
        style={{
          width: "40%",
          height: "25%",
          bottom: "10%",
          left: "10%",
          background:
            "radial-gradient(ellipse at center, var(--events-orb-3), transparent 70%)",
          filter: prefersReducedMotion ? "none" : "blur(50px)",
        }}
      />
    </div>
  )
}
