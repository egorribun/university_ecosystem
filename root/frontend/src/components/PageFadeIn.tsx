import { type CSSProperties, type ReactNode, useEffect, useState } from "react"

type PageFadeInProps = {
  children: ReactNode
  delay?: number
  effect?: "default" | "soft-blur"
}

export default function PageFadeIn({
  children,
  delay = 80,
  effect = "default",
}: PageFadeInProps) {
  const [ready, setReady] = useState(false)
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false)

  useEffect(() => {
    const frame = requestAnimationFrame(() => setReady(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  useEffect(() => {
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
  }, [])

  const resolvedEffect = prefersReducedMotion ? undefined : effect === "soft-blur" ? "soft-blur" : undefined

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
