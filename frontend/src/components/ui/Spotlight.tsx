import { motion, useMotionTemplate, useMotionValue, MotionValue } from "framer-motion"
import { MouseEvent, PropsWithChildren, useCallback } from "react"
import { cn } from "@/utils/cn"

export function useSpotlight() {
  const mouseX = useMotionValue(0)
  const mouseY = useMotionValue(0)

  const onMouseMove = useCallback(
    ({ currentTarget, clientX, clientY }: MouseEvent) => {
      const { left, top } = currentTarget.getBoundingClientRect()
      mouseX.set(clientX - left)
      mouseY.set(clientY - top)
    },
    [mouseX, mouseY]
  )

  return { mouseX, mouseY, onMouseMove }
}

type SpotlightOverlayProps = {
  mouseX: MotionValue<number>
  mouseY: MotionValue<number>
  color?: string
  className?: string
}

export function SpotlightOverlay({
  mouseX,
  mouseY,
  color = "rgba(var(--primary-main-rgb), 0.15)",
  className,
}: SpotlightOverlayProps) {
  return (
    <motion.div
      className={cn(
        "pointer-events-none absolute -inset-px rounded-[inherit] opacity-0 transition duration-300 group-hover:opacity-100",
        className
      )}
      style={{
        background: `
            radial-gradient(
              var(--overlay-blur) circle at ${mouseX}px ${mouseY}px,
              var(--primary-main) 0%,
              transparent 80%
            )
          `,
      }}
    />
  )
}

type SpotlightProps = PropsWithChildren<{
  className?: string
  spotlightColor?: string
}>

export function Spotlight({ children, className = "", spotlightColor }: SpotlightProps) {
  const { mouseX, mouseY, onMouseMove } = useSpotlight()

  return (
    <div className={cn("group relative overflow-hidden", className)} onMouseMove={onMouseMove}>
      <SpotlightOverlay mouseX={mouseX} mouseY={mouseY} color={spotlightColor} />
      {children}
    </div>
  )
}




