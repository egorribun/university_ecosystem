import { FC, ReactNode, useEffect, useState } from "react"

type Props = { children: ReactNode }
type MotionModule = typeof import("framer-motion")

let didPaint = false
let motionModulePromise: Promise<MotionModule> | null = null

const loadMotionModule = async () => {
  if (!motionModulePromise) {
    motionModulePromise = import("framer-motion").then((mod) => mod)
  }
  return motionModulePromise
}

const PageTransition: FC<Props> = ({ children }) => {
  const [motionModule, setMotionModule] = useState<MotionModule | null>(null)
  const [hasPainted, setHasPainted] = useState(didPaint)
  const [reduceMotion, setReduceMotion] = useState(() => {
    if (typeof window === "undefined" || !("matchMedia" in window)) return false
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches
  })

  useEffect(() => {
    didPaint = true
    setHasPainted(true)
  }, [])

  useEffect(() => {
    if (typeof window === "undefined" || !("matchMedia" in window)) return
    const media = window.matchMedia("(prefers-reduced-motion: reduce)")
    const handleChange = (event: MediaQueryListEvent) => {
      setReduceMotion(event.matches)
    }
    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", handleChange)
      return () => media.removeEventListener("change", handleChange)
    }
    media.addListener(handleChange)
    return () => media.removeListener(handleChange)
  }, [])

  useEffect(() => {
    if (reduceMotion) return
    let active = true
    loadMotionModule()
      .then((mod) => {
        if (active) setMotionModule(mod)
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [reduceMotion])

  if (reduceMotion || !motionModule) {
    return (
      <div style={{ position: "relative", minHeight: "100%", background: "var(--page-bg)" }}>
        <div style={{ position: "relative", zIndex: 1 }}>{children}</div>
      </div>
    )
  }

  const { LazyMotion, domAnimation, motion } = motionModule
  const initial = hasPainted ? { opacity: 0.001, y: 12 } : false

  return (
    <LazyMotion features={domAnimation}>
      <div style={{ position: "relative", minHeight: "100%", background: "var(--page-bg)" }}>
        <motion.div
          initial={initial}
          animate={{ opacity: 1, y: 0, transition: { duration: 0.2, ease: [0.2, 0, 0, 1] } }}
          exit={{ opacity: 0.001, y: -10, transition: { duration: 0.16, ease: [0.4, 0, 0.2, 1] } }}
          style={{
            position: "relative",
            zIndex: 1,
            willChange: "transform, opacity",
            backfaceVisibility: "hidden",
            transform: "translateZ(0)",
          }}
        >
          {children}
        </motion.div>
      </div>
    </LazyMotion>
  )
}

export default PageTransition
