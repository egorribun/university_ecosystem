import { useMemo, memo } from "react"

interface DashboardBackdropProps {
  isNarrow: boolean
  prefersReducedMotion: boolean
}

function DashboardBackdropComponent({ isNarrow, prefersReducedMotion }: DashboardBackdropProps) {
  // Memoized for stability, though much cheaper now as a pure component
  const layers = useMemo(() => {
    // Base gradients using extracted CSS variables in dashboard-theme.css
    const baseLayers = [
      "absolute inset-0 z-hide bg-(--grad-dash-radial-top) mix-blend-soft-light",
      "absolute inset-0 z-hide bg-(--grad-dash-radial-bottom)",
    ]

    const orbSize = isNarrow ? "h-40 w-40" : "h-80 w-80"
    baseLayers.push(
      `absolute -top-56 left-1 ${orbSize} -translate-x-1/2 rounded-full bg-(--grad-dash-orb) blur-(--glow-blur-3xl)`
    )

    if (!isNarrow) {
      baseLayers.push(
        prefersReducedMotion
          ? "absolute bottom-[-16rem] right-[10%] h-[10rem] w-[10rem] rounded-full bg-(--grad-dash-pulse) opacity-strong blur-(--glow-blur-xl)"
          : "absolute bottom-[-18rem] right-[8%] h-[13rem] w-[13rem] animate-[pulse_14s_ease-in-out_infinite] rounded-full bg-(--grad-dash-pulse) blur-(--glow-blur-3xl)"
      )
    }

    if (!prefersReducedMotion && !isNarrow) {
      baseLayers.push(
        "absolute -left-28 top-1 h-48 w-48 -translate-y-1/2 animate-[spin_26s_linear_infinite] rounded-full bg-(--grad-dash-conic) opacity-hover blur-(--glow-blur-mega)"
      )
    } else if (!isNarrow) {
      baseLayers.push(
        "absolute -left-24 top-1 h-40 w-40 -translate-y-1/2 rounded-full bg-(--grad-dash-conic-simple) opacity-strong blur-(--glow-blur-2xl)"
      )
    }

    return baseLayers
  }, [isNarrow, prefersReducedMotion])

  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      {layers.map((layer, index) => (
        <div key={`backdrop-layer-${index}`} className={layer} />
      ))}
    </div>
  )
}

export const DashboardBackdrop = memo(DashboardBackdropComponent)
