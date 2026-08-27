import { useMemo } from "react"
import type { WeatherAnimationVariant } from "@/utils/weatherIcons"
import { cn } from "@/utils/cn"

interface WeatherAmbientProps {
  animation: WeatherAnimationVariant
  /** Disable all particles (e.g. reduced motion) */
  disabled?: boolean
}

/** Number of particles per variant */
const PARTICLE_COUNTS: Record<WeatherAnimationVariant, number> = {
  none: 0,
  glow: 0,
  breeze: 0,
  drizzle: 18,
  snow: 14,
  storm: 22,
}

/**
 * WeatherAmbient — CSS-only weather particles for dashboard backdrop (Wave 47)
 *
 * Renders lightweight CSS-animated particles (rain drops, snowflakes)
 * that float in the dashboard background. All animations via @keyframes,
 * zero JS animation loops. Respects prefers-reduced-motion via `disabled` prop.
 */
export function WeatherAmbient({ animation, disabled = false }: WeatherAmbientProps) {
  const count = disabled ? 0 : (PARTICLE_COUNTS[animation] ?? 0)

  const particles = useMemo(() => {
    if (count === 0) return []
    return Array.from({ length: count }, (_, i) => ({
      id: i,
      // Deterministic pseudo-random positions using golden ratio
      left: `${((i * 61.8) % 100).toFixed(1)}%`,
      delay: `${((i * 0.37) % 3).toFixed(2)}s`,
      duration: animation === "snow" ? `${3 + (i % 4) * 0.8}s` : `${0.8 + (i % 5) * 0.15}s`,
      opacity: (0.15 + (i % 3) * 0.1).toFixed(2),
      size: animation === "snow" ? `${2 + (i % 3)}px` : "1px",
    }))
  }, [count, animation])

  if (count === 0) return null

  return (
    <div
      className="weather-ambient pointer-events-none absolute inset-0 overflow-hidden z-[1]"
      aria-hidden="true"
    >
      {particles.map((p) => (
        <span
          key={p.id}
          className={cn(
            "absolute rounded-full",
            animation === "snow" && "bg-white",
            (animation === "drizzle" || animation === "storm") && "bg-sky-300/40"
          )}
          style={
            {
              left: p.left,
              top: "-5%",
              width: p.size,
              height: animation === "snow" ? p.size : `${8 + (p.id % 4) * 4}px`,
              animationName: animation === "snow" ? "weather-snow-fall" : "weather-rain-fall",
              animationDuration: p.duration,
              animationDelay: p.delay,
              animationTimingFunction: animation === "snow" ? "ease-in-out" : "linear",
              animationIterationCount: "infinite",
              "--_particle-opacity": p.opacity,
            } as React.CSSProperties
          }
        />
      ))}
    </div>
  )
}
