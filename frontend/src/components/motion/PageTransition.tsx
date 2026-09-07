import { FC, ReactNode, useEffect, useRef, useState } from "react"
import { DURATIONS, EASING } from "@/utils/motion"

type Props = { children: ReactNode }
type MotionModule = typeof import("framer-motion")

let didPaint = false
let motionModulePromise: Promise<MotionModule> | null = null
export const getInitialReduceMotion = (): boolean => {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

export const shouldLoadMotionModule = (reduceMotion: boolean): boolean => !reduceMotion

export function commitMotionModuleIfActive<T>(
  active: boolean,
  setMotionModule: (module: T) => void,
  module: T
): void {
  if (active) setMotionModule(module)
}

export const deactivateMotionLoad = (state: { active: boolean }): void => {
  state.active = false
}

export const shouldLogMotionImportFailure = (isDevelopment: boolean): boolean => isDevelopment

export const loadMotionModule = (): Promise<MotionModule> => {
  if (!motionModulePromise) {
    motionModulePromise = import("framer-motion")
  }
  return motionModulePromise
}

const PageTransition: FC<Props> = ({ children }) => {
  const [motionModule, setMotionModule] = useState<MotionModule | null>(null)
  const [isInitialPaint] = useState(() => !didPaint)
  const [reduceMotion, setReduceMotion] = useState(getInitialReduceMotion)
  const mediaCleanupRef = useRef<(() => void) | null>(null)
  const lifecycleRef = useRef<(node: HTMLDivElement | null) => void>((node) => {
    if (node === null) {
      mediaCleanupRef.current?.()
      mediaCleanupRef.current = null
      return
    }

    didPaint = true
  }).current

  useEffect(() => {
    // The callback ref owns cleanup because this listener is intentionally
    // installed once for the component lifetime. Keeping the effect guarded
    // makes rerenders (including reduced-motion changes) allocation-free while
    // still allowing the media query to be installed after the root commits.
    if (mediaCleanupRef.current) return
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return
    const media = window.matchMedia("(prefers-reduced-motion: reduce)")
    const handleChange = (event: MediaQueryListEvent) => {
      setReduceMotion(event.matches)
    }
    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", handleChange)
      mediaCleanupRef.current = () => media.removeEventListener("change", handleChange)
      return
    }
    media.addListener(handleChange)
    mediaCleanupRef.current = () => media.removeListener(handleChange)
  })

  useEffect(() => {
    if (!shouldLoadMotionModule(reduceMotion)) return
    const activity = { active: true }
    loadMotionModule()
      .then((mod) => {
        commitMotionModuleIfActive(activity.active, setMotionModule, mod)
      })
      .catch((err: unknown) => {
        if (shouldLogMotionImportFailure(import.meta.env.DEV)) {
          console.warn("[PageTransition] framer-motion load failed:", err)
        }
      })
    return () => {
      deactivateMotionLoad(activity)
    }
  }, [reduceMotion])

  const animatedContent =
    !reduceMotion && motionModule
      ? (() => {
          // Wave 124 SW1 — destructure `m` (minimal Motion component) instead
          // of `motion` so this branch stays on the domAnimation surface.
          const { LazyMotion, domAnimation, m } = motionModule
          const initial = isInitialPaint
            ? false
            : { opacity: 0, scale: 0.98, y: "0.75rem", filter: "blur(0.25rem)" }
          return (
            <LazyMotion features={domAnimation}>
              <m.div
                initial={initial}
                animate={{
                  opacity: 1,
                  y: 0,
                  scale: 1,
                  filter: "blur(0rem)",
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
                  filter: "blur(0.125rem)",
                  transition: {
                    duration: DURATIONS.medium,
                    ease: EASING.premium,
                  },
                }}
                className="relative z-base [backface-visibility:hidden] [transform:translateZ(0)] will-change-[transform,opacity,filter]"
              >
                {children}
              </m.div>
            </LazyMotion>
          )
        })()
      : null

  return (
    <div ref={lifecycleRef} className="relative min-h-full bg-page">
      {animatedContent ?? <div className="relative z-base">{children}</div>}
    </div>
  )
}

export default PageTransition
