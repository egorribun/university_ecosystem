interface DashboardBackdropProps {
  isNarrow: boolean
  prefersReducedMotion: boolean
}

function DashboardBackdropComponent({ isNarrow, prefersReducedMotion }: DashboardBackdropProps) {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      {/* Main hero glow — large radial centered at top, the key visual element */}
      <div
        className="absolute left-1/2 top-0 -translate-x-1/2"
        style={{
          width: isNarrow ? "120%" : "80%",
          height: isNarrow ? "300px" : "420px",
          background: "radial-gradient(ellipse at 50% 0%, var(--dash-hero-orb), transparent 70%)",
          filter: "blur(40px)",
        }}
      />

      {/* Secondary accent — right side subtle glow */}
      {!isNarrow && (
        <div
          className="absolute right-[10%] top-[5%] h-48 w-48 rounded-full opacity-soft"
          style={{
            background: "radial-gradient(circle, var(--dash-hero-highlight), transparent)",
            filter: "blur(60px)",
          }}
        />
      )}

      {/* Slow spinning conic — subtle ambient light */}
      {!prefersReducedMotion && !isNarrow && (
        <div
          className="absolute left-[10%] top-[8%] h-32 w-32 rounded-full opacity-soft will-change-transform"
          style={{
            background: "var(--grad-dash-conic)",
            filter: "blur(50px)",
            animation: "spin 40s linear infinite",
          }}
        />
      )}
    </div>
  )
}

export const DashboardBackdrop = DashboardBackdropComponent
