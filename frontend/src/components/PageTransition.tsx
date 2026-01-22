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
  const initial = hasPainted ? { opacity: 0, scale: 0.98, y: 12, filter: "blur(4px)" } : false

  return (
    <LazyMotion features={domAnimation}>
      <div style={{ position: "relative", minHeight: "100%", background: "var(--page-bg)" }}>
        <motion.div
          initial={initial}
          animate={{
            opacity: 1,
            y: 0,
            scale: 1,
            filter: "blur(0px)",
            transition: {
              type: "spring",
              stiffness: 200,
              damping: 28,
              mass: 1.2,
              restDelta: 0.001,
            },
          }}
          exit={{
            opacity: 0,
            scale: 0.99,
            y: -12,
            filter: "blur(2px)",
            transition: {
              duration: 0.4,
              ease: [0.22, 1, 0.36, 1],
            },
          }}
          style={{
            position: "relative",
            zIndex: 1,
            willChange: "transform, opacity, filter",
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
