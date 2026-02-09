import { motion, useAnimation, useInView, Variants, TargetAndTransition } from "framer-motion"
import { ReactNode, useEffect, useRef } from "react"
import { springHeavy, easePremium } from "@/utils/animations"

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
  viewportMargin?: string
}

const getVariants = (mode: string, direction: string): Variants => {
  const distance = 30

  const baseHidden: TargetAndTransition = { opacity: 0, filter: "blur(8px)" }
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
        baseHidden.y = -distance
        baseVisible.y = 0
        break
      case "left":
        baseHidden.x = distance
        baseVisible.x = 0
        break
      case "right":
        baseHidden.x = -distance
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
  duration = 0.8,
  className,
  width = "100%",
  viewportMargin = "0px 0px -100px 0px",
}: Props) => {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: viewportMargin as any })
  const controls = useAnimation()

  useEffect(() => {
    if (isInView) {
      void controls.start("visible")
    }
  }, [isInView, controls])

  // Determine transition based on mode
  const transition =
    mode === "pop" || mode === "scale"
      ? { ...springHeavy, delay }
      : { duration, ease: easePremium, delay }

  return (
    <div ref={ref} style={{ width }} className={className}>
      <motion.div
        variants={getVariants(mode, direction)}
        initial="hidden"
        animate={controls}
        transition={transition}
      >
        {children}
      </motion.div>
    </div>
  )
}
