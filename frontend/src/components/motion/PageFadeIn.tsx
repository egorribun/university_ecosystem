import { type CSSProperties, type ReactNode, useEffect, useState } from "react"
import { motion as motionTokens } from "@/theme/tokens"

type PageFadeInProps = {
  children: ReactNode
  delay?: number
  effect?: "default" | "soft-blur"
}

export default function PageFadeIn({
  children,
  delay = motionTokens.delayShort * 1000,
  effect,
}: PageFadeInProps) {
  const isTestEnvironment = import.meta.env.MODE === "test"

  const [ready, setReady] = useState(() => isTestEnvironment)
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false)

  useEffect(() => {
    if (isTestEnvironment) return

    const markReady = () => setReady(true)

    if (typeof window.requestAnimationFrame === "function") {
      const frame = window.requestAnimationFrame(markReady)
      return () => window.cancelAnimationFrame(frame)
    }

    const timeout = window.setTimeout(markReady, 16)
    return () => window.clearTimeout(timeout)
  }, [isTestEnvironment])

  useEffect(() => {
    if (isTestEnvironment) return
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return
    }

    const query = window.matchMedia("(prefers-reduced-motion: reduce)")
    const updatePreference = () => setPrefersReducedMotion(query.matches)

    updatePreference()

    if (typeof query.addEventListener === "function") {
      query.addEventListener("change", updatePreference)
      return () => query.removeEventListener("change", updatePreference)
    }

    if (typeof query.addListener === "function") {
      query.addListener(updatePreference)
      return () => query.removeListener(updatePreference)
    }

    return
  }, [isTestEnvironment])

  const resolvedEffect = prefersReducedMotion
    ? undefined
    : effect === "soft-blur"
      ? "soft-blur"
      : undefined

  return (
    <div
      data-page-fade
      data-ready={ready ? "true" : "false"}
      data-effect={resolvedEffect}
      style={
        {
          "--page-fade-delay": `${delay}ms`,
        } as CSSProperties
      }
      className="page-fade relative min-h-full"
    >
      {children}
    </div>
  )
}
