/**
 * NewsBackdrop — decorative ambient layer for the news page.
 * Mirrors DashboardBackdrop: radial gradient orbs + optional spinning conic.
 * All elements are aria-hidden, pointer-events-none, absolutely positioned.
 */

interface NewsBackdropProps {
  isNarrow: boolean
  prefersReducedMotion?: boolean
}

export function NewsBackdrop({ isNarrow, prefersReducedMotion = false }: NewsBackdropProps) {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      {/* Primary hero glow — large radial at top center */}
      <div
        className="absolute left-1/2 top-0 -translate-x-1/2"
        style={{
          width: isNarrow ? "100%" : "85%",
          height: isNarrow ? "260px" : "420px",
          background:
            "radial-gradient(ellipse at 50% 0%, var(--news-hero-orb), transparent 72%)",
          filter: prefersReducedMotion ? "none" : "blur(40px)",
        }}
      />

      {/* Secondary accent — right side glow */}
      {!isNarrow && !prefersReducedMotion && (
        <div
          className="absolute right-[8%] top-[4%] h-52 w-52 rounded-full opacity-soft"
          style={{
            background:
              "radial-gradient(circle, var(--news-hero-highlight), transparent)",
            filter: "blur(60px)",
          }}
        />
      )}
    </div>
  )
}
