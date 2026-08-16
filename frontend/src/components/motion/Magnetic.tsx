import { useRef, useState, type ReactNode, type MouseEvent } from "react"

interface MagneticProps {
  children: ReactNode
  strength?: number
  className?: string
}

// Wave 124 SW1 — Refactored from framer-motion useMotionValue/useSpring
// (require domMax) to plain CSS transform + CSS transition. The cubic-bezier
// approximates the original underdamped spring (stiffness 150, damping 15,
// mass 0.1) — smooth ease-out with subtle overshoot. UX is comparable;
// magnetic pull-back on mouse-leave still feels organic. Plain <div> since
// no framer features are needed here.
const TRANSITION = "transform 320ms cubic-bezier(0.34, 1.56, 0.64, 1)"

export default function Magnetic({ children, strength = 0.5, className }: MagneticProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ x: 0, y: 0 })

  const handleMouseMove = (e: MouseEvent) => {
    const { clientX, clientY } = e
    const { left, top, width, height } = ref.current!.getBoundingClientRect()

    const centerX = left + width / 2
    const centerY = top + height / 2

    setPos({
      x: (clientX - centerX) * strength,
      y: (clientY - centerY) * strength,
    })
  }

  const handleMouseLeave = () => {
    setPos({ x: 0, y: 0 })
  }

  return (
    <div
      ref={ref}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{
        transform: `translate3d(${pos.x}px, ${pos.y}px, 0)`,
        transition: TRANSITION,
        willChange: "transform",
      }}
      className={className}
    >
      {children}
    </div>
  )
}
