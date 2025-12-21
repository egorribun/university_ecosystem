import { useRef, useState, type ReactNode, type MouseEvent } from "react"
import { motion, useSpring, useMotionValue } from "framer-motion"

interface MagneticProps {
    children: ReactNode
    strength?: number
    className?: string
}

const SPRING_CONFIG = { damping: 15, stiffness: 150, mass: 0.1 }

export default function Magnetic({ children, strength = 0.5, className }: MagneticProps) {
    const ref = useRef<HTMLDivElement>(null)
    const x = useMotionValue(0)
    const y = useMotionValue(0)

    const springX = useSpring(x, SPRING_CONFIG)
    const springY = useSpring(y, SPRING_CONFIG)

    const handleMouseMove = (e: MouseEvent) => {
        if (!ref.current) return
        const { clientX, clientY } = e
        const { left, top, width, height } = ref.current.getBoundingClientRect()

        const centerX = left + width / 2
        const centerY = top + height / 2

        const distanceX = clientX - centerX
        const distanceY = clientY - centerY

        x.set(distanceX * strength)
        y.set(distanceY * strength)
    }

    const handleMouseLeave = () => {
        x.set(0)
        y.set(0)
    }

    return (
        <motion.div
            ref={ref}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
            style={{ x: springX, y: springY }}
            className={className}
        >
            {children}
        </motion.div>
    )
}
