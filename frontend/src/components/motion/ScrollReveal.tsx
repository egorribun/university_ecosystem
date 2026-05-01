import { m, Variants, TargetAndTransition } from "framer-motion"
import { ReactNode, useEffect, useRef, useMemo, useState } from "react"
import { springHeavy } from "@/utils/animations"
import { motion as motionTokens } from "@/theme/tokens"
import { EASING } from "@/utils/motion"

type Props = {
  children: ReactNode
  mode?: "fade" | "slide" | "scale" | "pop"
  direction?: "up" | "down" | "left" | "right"
  delay?: number
  duration?: number
  className?: string
  width?: "fit-content" | "100%"
  stagger?: number
  threshold?: number
  /** IntersectionObserver rootMargin string — e.g. "0px 0px -50px 0px" */
  viewportMargin?: string
}

const getVariants = (mode: string, direction: string): Variants => {
  const distance = motionTokens.slideMd

  const baseHidden: TargetAndTransition = { opacity: 0, filter: "blur(0.5rem)" }
  const baseVisible: TargetAndTransition = { opacity: 1, filter: "blur(0px)" }

  if (mode === "pop") {
    baseHidden.scale = 0.94
    baseVisible.scale = 1
  }

  if (mode === "slide" || mode === "fade") {
    switch (direction) {
      case "up":
        baseHidden.y = distance
        baseVisible.y = 0
        break
      case "down":
        baseHidden.y = `-${distance}`
        baseVisible.y = 0
        break
      case "left":
        baseHidden.x = distance
        baseVisible.x = 0
        break
      case "right":
        baseHidden.x = `-${distance}`
        baseVisible.x = 0
        break
    }
  }

  if (mode === "scale") {
    baseHidden.scale = 0.96
    baseVisible.scale = 1
  }

  return {
    hidden: baseHidden,
    visible: baseVisible,
  }
}

export const ScrollReveal = ({
  children,
  mode = "slide",
  direction = "up",
  delay = 0,
  duration = motionTokens.durationSlow,
  className,
  width = "100%",
  viewportMargin = "0px 0px -50px 0px",
}: Props) => {
  const ref = useRef<HTMLDivElement>(null)
  // Wave 124 SW1 — Refactored from framer-motion useInView/useAnimation to
  // plain IntersectionObserver + state-driven variant. useAnimation requires
  // domMax features which we excluded from LazyMotion. Equivalent UX —
  // observer fires once + state transitions hidden→visible. The motion.div
  // variants/initial/animate pattern below is in domAnimation set.
  const [isVisible, setIsVisible] = useState(false)

  const variants = useMemo(() => getVariants(mode, direction), [mode, direction])

  useEffect(() => {
    const el = ref.current
    if (!el || isVisible) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setIsVisible(true)
          observer.disconnect()
        }
      },
      { rootMargin: viewportMargin }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [isVisible, viewportMargin])

  // Determine transition based on mode
  const transition =
    mode === "pop" || mode === "scale"
      ? { ...springHeavy, delay }
      : { duration, ease: EASING.premium, delay }

  return (
    <div ref={ref} style={{ width }} className={className}>
      <m.div
        variants={variants}
        initial="hidden"
        animate={isVisible ? "visible" : "hidden"}
        transition={transition}
      >
        {children}
      </m.div>
    </div>
  )
}
