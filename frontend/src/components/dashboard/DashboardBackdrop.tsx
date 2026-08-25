interface DashboardBackdropProps {
  isNarrow: boolean
  prefersReducedMotion: boolean
}

function DashboardBackdropComponent({ isNarrow }: DashboardBackdropProps) {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      <div
        className="absolute inset-x-0 top-0"
        style={{
          height: isNarrow ? "300px" : "420px",
          background:
            "linear-gradient(180deg, color-mix(in srgb, var(--dash-hero-orb) 32%, transparent), transparent 82%)",
        }}
      />
    </div>
  )
}

export const DashboardBackdrop = DashboardBackdropComponent
