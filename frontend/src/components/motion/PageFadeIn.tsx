import { type CSSProperties, type ReactNode, useCallback, useEffect, useRef, useState } from "react"
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
  const mediaInitializedRef = useRef(false)
  const mediaCleanupRef = useRef<(() => void) | null>(null)
  const lifecycleRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (node === null) {
        mediaCleanupRef.current?.()
        mediaCleanupRef.current = null
        mediaInitializedRef.current = false
      }
    },
    [mediaCleanupRef, mediaInitializedRef]
  )

  useEffect(() => {
    if (isTestEnvironment || ready) return

    const markReady = () => setReady(true)

    if (typeof window.requestAnimationFrame === "function") {
      const frame = window.requestAnimationFrame(markReady)
      return () => window.cancelAnimationFrame(frame)
    }

    const timeout = window.setTimeout(markReady, 16)
    return () => window.clearTimeout(timeout)
  })

  useEffect(() => {
    if (isTestEnvironment || mediaInitializedRef.current) return
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return
    }
    mediaInitializedRef.current = true

    const query = window.matchMedia("(prefers-reduced-motion: reduce)")
    const updatePreference = () => setPrefersReducedMotion(query.matches)

    updatePreference()

    if (typeof query.addEventListener === "function") {
      query.addEventListener("change", updatePreference)
      mediaCleanupRef.current = () => query.removeEventListener("change", updatePreference)
      return
    }

    if (typeof query.addListener === "function") {
      query.addListener(updatePreference)
      mediaCleanupRef.current = () => query.removeListener(updatePreference)
      return
    }

    return
  })

  const resolvedEffect = prefersReducedMotion
    ? undefined
    : effect === "soft-blur"
      ? "soft-blur"
      : undefined

  return (
    <div
      ref={lifecycleRef}
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
