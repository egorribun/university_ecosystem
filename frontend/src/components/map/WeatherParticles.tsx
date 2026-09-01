/**
 * Canvas particle overlay for weather effects on the MapLibre GL campus map.
 * Renders rain, snow, storm (rain + lightning flash), and fog particles.
 * Returns null for clear/cloudy conditions and when prefers-reduced-motion is enabled.
 *
 * @module WeatherParticles
 * @since Wave 108
 */
import { useEffect, useRef } from "react"
import useMediaQuery from "@/hooks/useMediaQuery"
import { isLowPowerDevice } from "@/utils/deviceCapabilities"

import type { WeatherCondition } from "@/utils/weatherCodes"

interface Particle {
  x: number
  y: number
  speed: number
  size: number
  opacity: number
  drift: number
}

interface WeatherParticlesProps {
  condition: WeatherCondition
  isDark: boolean
}

/* ------------------------------------------------------------------ */
/*  Particle configuration per weather condition                       */
/* ------------------------------------------------------------------ */

interface ParticleConfig {
  count: number
  color: (isDark: boolean) => string
  sizeRange: [number, number]
  speedRange: [number, number]
  opacityRange: [number, number]
  driftRange: [number, number]
}

/**
 * Particle color configs. Canvas 2D fillStyle requires inline hex values —
 * CSS custom properties cannot be read at canvas paint time.
 * Token equivalents documented for design system traceability.
 */
const CONFIGS: Record<string, ParticleConfig> = {
  rain: {
    count: 200,
    color: (dark) => (dark ? "#93c5fd" : "#60a5fa"), // --color-blue-300 / --color-blue-400
    sizeRange: [2, 4],
    speedRange: [6, 12],
    opacityRange: [0.3, 0.7],
    driftRange: [-0.5, 0.5],
  },
  snow: {
    count: 100,
    color: (dark) => (dark ? "#e2e8f0" : "#f8fafc"), // --color-slate-200 / --color-slate-50
    sizeRange: [1, 3],
    speedRange: [0.5, 1.5],
    opacityRange: [0.4, 0.8],
    driftRange: [-0.8, 0.8],
  },
  storm: {
    count: 250,
    color: (dark) => (dark ? "#93c5fd" : "#60a5fa"), // --color-blue-300 / --color-blue-400
    sizeRange: [2, 4],
    speedRange: [8, 16],
    opacityRange: [0.35, 0.75],
    driftRange: [-1, 1],
  },
  fog: {
    count: 50,
    color: (dark) => (dark ? "#94a3b8" : "#cbd5e1"), // --color-slate-400 / --color-slate-300
    sizeRange: [10, 20],
    speedRange: [0.2, 0.6],
    opacityRange: [0.04, 0.12],
    driftRange: [-0.4, 0.4],
  },
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function rand(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

function createParticle(config: ParticleConfig, width: number, height: number): Particle {
  return {
    x: Math.random() * width,
    y: Math.random() * height,
    speed: rand(config.speedRange[0], config.speedRange[1]),
    size: rand(config.sizeRange[0], config.sizeRange[1]),
    opacity: rand(config.opacityRange[0], config.opacityRange[1]),
    drift: rand(config.driftRange[0], config.driftRange[1]),
  }
}

function recycleParticle(p: Particle, config: ParticleConfig, width: number): void {
  p.x = Math.random() * width
  p.y = -p.size - Math.random() * 20
  p.speed = rand(config.speedRange[0], config.speedRange[1])
  p.size = rand(config.sizeRange[0], config.sizeRange[1])
  p.opacity = rand(config.opacityRange[0], config.opacityRange[1])
  p.drift = rand(config.driftRange[0], config.driftRange[1])
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function WeatherParticles({ condition, isDark }: WeatherParticlesProps) {
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const lowPowerDevice = isLowPowerDevice()

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const particlesRef = useRef<Particle[]>([])
  const frameRef = useRef<number>(0)
  const pausedRef = useRef(false)

  // Storm flash state
  const flashRef = useRef({ active: false, opacity: 0, nextFlash: 0 })

  useEffect(() => {
    if (prefersReducedMotion || lowPowerDevice) return
    const config = CONFIGS[condition]
    if (!config) return

    const canvas = canvasRef.current!
    const container = containerRef.current!

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    let width = 0
    let height = 0
    const isStorm = condition === "storm"
    const isFog = condition === "fog"
    const isSnow = condition === "snow"
    const color = config.color(isDark)

    /* ---------- resize ---------- */

    const resize = () => {
      width = container.clientWidth || window.innerWidth
      height = container.clientHeight || window.innerHeight
      canvas.width = width
      canvas.height = height

      // Re-initialize particles to fill new dimensions
      const particles: Particle[] = []
      for (let i = 0; i < config.count; i++) {
        particles.push(createParticle(config, width, height))
      }
      particlesRef.current = particles
    }

    const resizeObserver = new ResizeObserver(() => {
      resize()
    })
    resizeObserver.observe(container)

    /* ---------- visibility ---------- */

    const onVisibilityChange = () => {
      pausedRef.current = document.hidden
      if (pausedRef.current) {
        // Do not keep a requestAnimationFrame loop alive in a hidden tab. The
        // browser throttles background frames, but cancelling explicitly
        // avoids needless callbacks and lets the effect resume on demand.
        cancelAnimationFrame(frameRef.current)
        frameRef.current = 0
      } else {
        // The render loop caps delta at 50ms, so resuming cannot create a
        // large position jump even when no frame ran while the tab was hidden.
        frameRef.current = requestAnimationFrame(render)
      }
    }
    /* ---------- storm flash scheduling ---------- */

    if (isStorm) {
      flashRef.current = { active: false, opacity: 0, nextFlash: rand(3000, 8000) }
    }

    /* ---------- render loop ---------- */

    let lastTime = performance.now()

    const render = (now: number) => {
      if (pausedRef.current) {
        lastTime = now
        return
      }

      const dt = Math.min(now - lastTime, 50) // Cap delta to prevent jumps after tab switch
      lastTime = now
      const dtFactor = dt / 16.667 // Normalize to ~60fps

      ctx.clearRect(0, 0, width, height)

      const particles = particlesRef.current

      /* -- storm flash -- */
      if (isStorm) {
        const flash = flashRef.current
        flash.nextFlash -= dt
        if (flash.nextFlash <= 0 && !flash.active) {
          flash.active = true
          flash.opacity = 0.08
          flash.nextFlash = rand(3000, 8000)
        }
        if (flash.active) {
          ctx.fillStyle = `rgba(255, 255, 255, ${flash.opacity})`
          ctx.fillRect(0, 0, width, height)
          flash.opacity -= 0.001 * dt // Fade over ~100ms
          if (flash.opacity <= 0) {
            flash.active = false
            flash.opacity = 0
          }
        }
      }

      /* -- update & draw particles -- */
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i]!

        if (isSnow) {
          // Sinusoidal horizontal drift for snow
          p.x += Math.sin(now * 0.001 + i) * 0.3 * dtFactor + p.drift * dtFactor
        } else {
          p.x += p.drift * dtFactor
        }
        p.y += p.speed * dtFactor

        // Recycle when out of bounds
        if (p.y > height + p.size || p.x < -p.size || p.x > width + p.size) {
          if (isFog) {
            // Fog drifts horizontally — recycle on either side
            p.x = p.drift > 0 ? -p.size : width + p.size
            p.y = Math.random() * height
            p.speed = rand(config.speedRange[0], config.speedRange[1])
          } else {
            recycleParticle(p, config, width)
          }
        }

        // Draw
        ctx.globalAlpha = p.opacity

        if (isFog) {
          // Large semi-transparent circles
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
          ctx.fill()
        } else if (isSnow) {
          // Small circles
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
          ctx.fill()
        } else {
          // Rain / storm — short vertical lines
          ctx.strokeStyle = color
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.moveTo(p.x, p.y)
          ctx.lineTo(p.x + p.drift * 0.5, p.y + p.size)
          ctx.stroke()
        }
      }

      ctx.globalAlpha = 1
      frameRef.current = requestAnimationFrame(render)
    }

    document.addEventListener("visibilitychange", onVisibilityChange)

    /* ---------- init ---------- */

    resize()
    frameRef.current = requestAnimationFrame(render)

    /* ---------- cleanup ---------- */

    return () => {
      cancelAnimationFrame(frameRef.current)
      resizeObserver.disconnect()
      document.removeEventListener("visibilitychange", onVisibilityChange)
    }
  }, [condition, isDark, lowPowerDevice, prefersReducedMotion])

  // No particles for clear/cloudy, or when user prefers reduced motion
  if (prefersReducedMotion || lowPowerDevice || condition === "clear" || condition === "cloudy") {
    return null
  }

  // Early return if no config (defensive)
  if (!CONFIGS[condition]) {
    return null
  }

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 pointer-events-none"
      style={{ zIndex: 1 }}
      aria-hidden="true"
    >
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
    </div>
  )
}
