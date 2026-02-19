<<<<<<< HEAD
import { ReactNode } from "react"
import { useIntersectionObserver } from "@/hooks/ui/useIntersectionObserver"
import { cn } from "@/utils/cn"
=======
import { motion, useAnimation, useInView, Variants, TargetAndTransition } from "framer-motion"
import { ReactNode, useEffect, useRef, useMemo } from "react"
import { springHeavy } from "@/utils/animations"
import { motion as motionTokens } from "@/theme/tokens"
import { EASING } from "@/utils/motion"
>>>>>>> origin/main

type Props = {
  children: ReactNode
  mode?: "fade" | "slide" | "scale" | "pop"
  direction?: "up" | "down" | "left" | "right"
  delay?: number
  duration?: number
  className?: string
  width?: "fit-content" | "100%"
<<<<<<< HEAD
  viewportMargin?: string
}

=======
  stagger?: number
  threshold?: number
  viewportMargin?: NonNullable<Parameters<typeof useInView>[1]>["margin"]
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

>>>>>>> origin/main
export const ScrollReveal = ({
  children,
  mode = "slide",
  direction = "up",
  delay = 0,
<<<<<<< HEAD
  duration, // CSS duration handles this, but kept for API compat if needed in future inline styles
=======
  duration = motionTokens.durationSlow,
>>>>>>> origin/main
  className,
  width = "100%",
  viewportMargin = "0px 0px -50px 0px",
}: Props) => {
<<<<<<< HEAD
  const [ref, isVisible] = useIntersectionObserver({
    rootMargin: viewportMargin,
    freezeOnceVisible: true,
    threshold: 0.1,
  })

  const getHiddenClass = () => {
    if (mode === "fade") return "reveal-hidden-fade"
    if (mode === "scale" || mode === "pop") return "reveal-hidden-scale"

    // Slide direction
    switch (direction) {
      case "up": return "reveal-hidden-slide-up"
      case "down": return "reveal-hidden-slide-up" // Fallback to up for now, or add slide-down if needed
      case "left": return "reveal-hidden-slide-left"
      case "right": return "reveal-hidden-slide-right"
      default: return "reveal-hidden-slide-up"
    }
  }

  return (
    <div
      ref={ref}
      style={{
        width,
        transitionDelay: `${delay}s`,
        transitionDuration: `${duration}s`
      }}
      className={cn(
        "reveal-base",
        isVisible ? "reveal-visible" : getHiddenClass(),
        className
      )}
    >
      {children}
=======
  const ref = useRef<HTMLDivElement>(null)
  const isInView = useInView(ref, { once: true, margin: viewportMargin })
  const controls = useAnimation()

  const variants = useMemo(() => getVariants(mode, direction), [mode, direction])

  useEffect(() => {
    if (isInView) {
      void controls.start("visible")
    }
  }, [isInView, controls])

  // Determine transition based on mode
  const transition =
    mode === "pop" || mode === "scale"
      ? { ...springHeavy, delay }
      : { duration, ease: EASING.premium, delay }

  return (
    <div ref={ref} style={{ width }} className={className}>
      <motion.div
        variants={variants}
        initial="hidden"
        animate={controls}
        transition={transition}
      >
        {children}
      </motion.div>
>>>>>>> origin/main
    </div>
  )
}
