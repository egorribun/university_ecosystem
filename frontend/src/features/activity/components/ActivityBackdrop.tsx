type ActivityBackdropProps = {
  isNarrow: boolean
  prefersReducedMotion: boolean
}

export function ActivityBackdrop({ isNarrow, prefersReducedMotion }: ActivityBackdropProps) {
  return (
    <div
      className="pointer-events-none absolute inset-0 -z-1 overflow-hidden"
      aria-hidden="true"
    >
      {/* Primary hero orb — top center (emerald glow) */}
      <div
        className="absolute -top-20 left-1/2 h-[500px] w-[800px] max-w-full -translate-x-1/2"
        style={{
          background:
            "radial-gradient(ellipse at 50% 0%, var(--activity-hero-orb), transparent 72%)",
          filter: "blur(40px)",
        }}
      />

      {/* Secondary highlight — top right (teal accent) */}
      {!isNarrow && (
        <div
          className="absolute -top-10 right-0 h-[350px] w-[450px]"
          style={{
            background:
              "radial-gradient(ellipse at 80% 10%, var(--activity-hero-highlight), transparent 60%)",
            filter: "blur(50px)",
          }}
        />
      )}

      {/* Drifting conic gradient (desktop only, respect reduced motion) */}
      {!isNarrow && !prefersReducedMotion && (
        <div
          className="absolute left-1/4 top-10 h-[400px] w-[400px] opacity-60"
          style={{
            background: "var(--grad-activity-conic)",
            filter: "blur(60px)",
            animation: "orb-drift 40s ease-in-out infinite alternate",
          }}
        />
      )}

      {/* Third orb — bottom left (subtle cyan) */}
      <div
        className="absolute bottom-0 left-0 h-[300px] w-[400px]"
        style={{
          background:
            "radial-gradient(ellipse at 20% 80%, var(--activity-orb-3), transparent 65%)",
          filter: "blur(50px)",
        }}
      />
    </div>
  )
}
