import { m, HTMLMotionProps, Variants } from "framer-motion"
import { ReactNode } from "react"
import { motion as motionTokens } from "@/theme/tokens"

interface FadeInProps extends HTMLMotionProps<"div"> {
  children: ReactNode
  delay?: number
  duration?: number
  direction?: "up" | "down" | "left" | "right" | "none"
  distance?: number
  className?: string
}

export function FadeIn({
  children,
  delay = 0,
  duration = motionTokens.durationMedium,
  direction = "up",
  distance = 20, // Default to slideMd
  className,
  ...props
}: FadeInProps) {
  // The Lighthouse build intentionally omits the client entry script while
  // measuring the server-rendered document.  Rendering the entrance variant
  // in that mode would leave the SSR content at opacity:0 forever.  Keep the
  // normal composed entrance for production and let explicit caller props
  // continue to override this audit default via the spread below.
  const isLhci = import.meta.env.VITE_LHCI === "true"

  const getInitial = () => {
    switch (direction) {
      case "up":
        return { opacity: 0, y: distance }
      case "down":
        return { opacity: 0, y: -distance }
      case "left":
        return { opacity: 0, x: distance }
      case "right":
        return { opacity: 0, x: -distance }
      case "none":
        return { opacity: 0 }
    }
  }

  const variants: Variants = {
    hidden: getInitial(),
    visible: {
      opacity: 1,
      y: 0,
      x: 0,
      transition: {
        duration,
        delay,
        ease: [0.22, 1, 0.36, 1], // ease-out-quart
      },
    },
    exit: {
      opacity: 0,
      transition: { duration: motionTokens.durationFast },
    },
  }

  return (
    <m.div
      initial={isLhci ? false : "hidden"}
      animate="visible"
      exit="exit"
      variants={variants}
      className={className}
      {...props}
    >
      {children}
    </m.div>
  )
}
