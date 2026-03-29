import type { ComponentProps } from "react"
import { AnimatePresence, useReducedMotion } from "framer-motion"

export default function MotionPresence({
  children,
  initial = false,
  ...props
}: ComponentProps<typeof AnimatePresence>) {
  const reduce = useReducedMotion()
  return (
    <AnimatePresence initial={reduce ? false : initial} mode="wait" {...props}>
      {children}
    </AnimatePresence>
  )
}
