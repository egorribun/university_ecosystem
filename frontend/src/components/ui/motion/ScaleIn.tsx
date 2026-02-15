import { motion, HTMLMotionProps, Variants } from "framer-motion"
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
    <motion.div
      initial="hidden"
      animate="visible"
      exit="exit"
      variants={variants}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  )
}
