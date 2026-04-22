/**
 * EventsBackdrop — decorative ambient gradient layer.
 * Warm-toned orbs (amber/rose) to differentiate from News (sky/indigo).
 * Pattern source: components/news/NewsBackdrop.tsx
 *
 * Wave 118 SW3 (CLS-118-03): switched orb sizing from % → px. Container
 * (`div.events-theme`) grows as events content streams in; %-based orb
 * heights (55%, 35%, 25%) + %-anchored top/bottom values shifted with
 * container height, causing the primary orb to register as a 0.566 CLS
 * shift (LHCI Phase 0 selector: `div.w-full > div.events-theme >
 * div.pointer-events-none > div.absolute`). Fixed-pixel dimensions +
 * fixed-pixel top/bottom anchors stay stable under container growth,
 * eliminating the shift — same pattern NewsBackdrop has always used.
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
          height: isNarrow ? "300px" : "460px",
          top: "-80px",
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
          height: isNarrow ? "200px" : "280px",
          top: "40px",
          right: "-5%",
          background:
            "radial-gradient(ellipse at center, var(--events-hero-highlight), transparent 70%)",
          filter: prefersReducedMotion ? "none" : "blur(60px)",
        }}
      />

      {/* Tertiary accent — warm glow. Anchored from top (not bottom) so it
          stays stable when events-theme container grows — bottom-anchored
          % values shifted with container height, contributing to CLS. */}
      <div
        className="absolute rounded-full opacity-30"
        style={{
          width: "40%",
          height: isNarrow ? "160px" : "220px",
          top: isNarrow ? "520px" : "760px",
          left: "10%",
          background:
            "radial-gradient(ellipse at center, var(--events-orb-3), transparent 70%)",
          filter: prefersReducedMotion ? "none" : "blur(50px)",
        }}
      />
    </div>
  )
}
