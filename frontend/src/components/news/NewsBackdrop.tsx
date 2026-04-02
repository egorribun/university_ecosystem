/**
 * NewsBackdrop — decorative ambient layer for the news page.
 * Mirrors DashboardBackdrop: radial gradient orbs + optional spinning conic.
 * All elements are aria-hidden, pointer-events-none, absolutely positioned.
 */

interface NewsBackdropProps {
  isNarrow: boolean
  prefersReducedMotion: boolean
}

export function NewsBackdrop({ isNarrow, prefersReducedMotion }: NewsBackdropProps) {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      {/* Primary hero glow — large radial at top center */}
      <div
        className="absolute left-1/2 top-0 -translate-x-1/2"
        style={{
          width: isNarrow ? "130%" : "85%",
          height: isNarrow ? "260px" : "420px",
          background:
            "radial-gradient(ellipse at 50% 0%, var(--news-hero-orb), transparent 72%)",
          filter: "blur(40px)",
        }}
      />

      {/* Secondary accent — right side glow */}
      {!isNarrow && (
        <div
          className="absolute right-[8%] top-[4%] h-52 w-52 rounded-full opacity-soft"
          style={{
            background:
              "radial-gradient(circle, var(--news-hero-highlight), transparent)",
            filter: "blur(60px)",
          }}
        />
      )}

      {/* Drifting orb — left side */}
      {!prefersReducedMotion && !isNarrow && (
        <div
          className="absolute left-[6%] top-[12%] h-32 w-32 rounded-full opacity-soft will-change-transform"
          style={{
            background:
              "radial-gradient(circle, var(--news-orb-1), transparent)",
            filter: "blur(50px)",
            animation: "orb-drift 32s ease-in-out infinite",
          }}
        />
      )}

      {/* Breathing orb — lower right */}
      {!prefersReducedMotion && (
        <div
          className="absolute right-[12%] top-[35%] h-24 w-24 rounded-full opacity-subtle will-change-transform"
          style={{
            background:
              "radial-gradient(circle, var(--news-orb-2), transparent)",
            filter: "blur(45px)",
            animation: "orb-breathe 9s ease-in-out infinite",
          }}
        />
      )}

      {/* Slow spinning conic — subtle ambient */}
      {!prefersReducedMotion && !isNarrow && (
        <div
          className="absolute left-[15%] top-[50%] h-28 w-28 rounded-full opacity-subtle will-change-transform"
          style={{
            background: "var(--grad-news-conic)",
            filter: "blur(50px)",
            animation: "spin 45s linear infinite",
          }}
        />
      )}
    </div>
  )
}
