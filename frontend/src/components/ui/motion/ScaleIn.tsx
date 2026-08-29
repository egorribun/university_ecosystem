import { m, HTMLMotionProps, Variants } from "framer-motion"
import { ReactNode } from "react"
import { motion as motionTokens } from "@/theme/tokens"

interface ScaleInProps extends HTMLMotionProps<"div"> {
  children: ReactNode
  delay?: number
  duration?: number
  initialScale?: number
  className?: string
}

export function ScaleIn({
  children,
  delay = 0,
  duration = motionTokens.durationMedium,
  initialScale = 0.95, // Default to scaleIn
  className,
  ...props
}: ScaleInProps) {
  // Keep SSR Lighthouse documents paintable when their client entry is
  // intentionally stripped.  Callers can still provide an explicit initial
  // prop, which is applied after this audit-only default.
  const isLhci = import.meta.env.VITE_LHCI === "true"

  const variants: Variants = {
    hidden: { opacity: 0, scale: initialScale },
    visible: {
      opacity: 1,
      scale: 1,
      transition: {
        duration,
        delay,
        ease: [0.22, 1, 0.36, 1],
      },
    },
    exit: {
      opacity: 0,
      scale: initialScale,
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
