import type { Variants, Transition } from "framer-motion"
import { motion as motionTokens } from "@/theme/tokens"

// Kinetic & Organic Easing
export const easePremium = [0.22, 1, 0.36, 1] as const
export const easeOutExpo = [0.16, 1, 0.3, 1] as const
export const easeBackOut = [0.34, 1.56, 0.64, 1] as const

// Organic Spring Physics
export const springHeavy: Transition = {
  type: "spring",
  stiffness: 200,
  damping: 30,
  mass: 1.5,
}

export const springSoft: Transition = {
  type: "spring",
  stiffness: 260,
  damping: 25,
  mass: 1,
}

export const springBouncy: Transition = {
  type: "spring",
  stiffness: 400,
  damping: 15,
  mass: 0.8,
}

// Reusable Variants

export const fadeVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: motionTokens.durationSlower, ease: easePremium },
  },
  exit: { opacity: 0, transition: { duration: motionTokens.durationMedium } },
}

export const slideUpVariants: Variants = {
  hidden: { opacity: 0, y: 30 }, // Fixed offset for specific entrance
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      type: "spring",
      ...springSoft,
    },
  },
  exit: {
    opacity: 0,
    y: -20,
    transition: { duration: motionTokens.durationBase, ease: "easeOut" },
  },
}

export const scaleInVariants: Variants = {
  hidden: { opacity: 0, scale: 0.94, filter: "blur(var(--blur-xs))" },
  visible: {
    opacity: 1,
    scale: 1,
    filter: "blur(var(--blur-none))",
    transition: springHeavy,
  },
  exit: {
    opacity: 0,
    scale: 0.98,
    transition: { duration: motionTokens.durationMedium },
  },
}

// Stagger children wrapper
export const staggerContainerVariants = (staggerChildren = 0.05, delayChildren = 0): Variants => ({
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren,
      delayChildren,
    },
  },
})

// Interactive Interactions
export const hoverScale: Variants = {
  hover: {
    scale: 1.02,
    transition: { type: "spring", stiffness: 400, damping: 20 },
  },
  tap: {
    scale: 0.97,
    transition: { type: "spring", stiffness: 400, damping: 20 },
  },
}

export const hoverLift: Variants = {
  hover: {
    y: -8,
    transition: { type: "spring", stiffness: 300, damping: 20 },
  },
  tap: {
    y: -2,
    transition: { type: "spring", stiffness: 400, damping: 20 },
  },
}

// Scroll Reveals (Organic & Kinetic)
export const revealVariants = (direction: "up" | "down" | "left" | "right" = "up"): Variants => {
  const offset = 40
  const x = direction === "left" ? offset : direction === "right" ? -offset : 0
  const y = direction === "up" ? offset : direction === "down" ? -offset : 0

  return {
    hidden: { opacity: 0, x, y, filter: "blur(var(--blur-sm))" },
    visible: {
      opacity: 1,
      x: 0,
      y: 0,
      filter: "blur(var(--blur-none))",
      transition: {
        duration: motionTokens.navTransition,
        ease: easePremium,
      },
    },
  }
}
